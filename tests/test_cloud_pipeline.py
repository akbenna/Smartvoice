"""
Tests voor de geoptimaliseerde cloud_api Claude-route.

Dekt:
  - JSON-prefill in de Anthropic-call (geldige JSON zonder markdown-fences)
  - Per-call max_tokens doorgifte
  - Samengevoegde nazorg-stap (decisief + detectie in EEN LLM-call)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.cloud_api import llm_service, pipeline


# ── Anthropic JSON-prefill ──

@pytest.mark.asyncio
async def test_anthropic_json_prefill_prepends_brace():
    """Bij json_mode stuurt de prefill een '{' mee en plakt die terug."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status = MagicMock()
    fake_response.json = MagicMock(
        return_value={
            "content": [{"text": '"s": "klacht"}'}],  # zonder leidende '{'
            "usage": {"input_tokens": 100, "output_tokens": 20},
        }
    )

    client = AsyncMock()
    client.post = AsyncMock(return_value=fake_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    cfg = MagicMock()
    cfg.llm.anthropic_api_key = "test-key"
    cfg.llm.anthropic_model = "claude-haiku-4-5-20251001"
    cfg.llm.temperature = 0.1
    cfg.llm.max_tokens = 2048

    with patch.object(llm_service, "get_config", return_value=cfg), \
         patch.object(llm_service.httpx, "AsyncClient", return_value=client):
        out = await llm_service.complete(
            system_prompt="sys",
            user_prompt="usr",
            provider="anthropic",
            json_mode=True,
            max_tokens=300,
        )

    # Resultaat is geldige JSON dankzij teruggeplakte '{'
    assert json.loads(out) == {"s": "klacht"}

    # max_tokens en assistant-prefill correct meegestuurd
    body = client.post.call_args.kwargs["json"]
    assert body["max_tokens"] == 300
    assert body["messages"][-1] == {"role": "assistant", "content": "{"}
    assert isinstance(body["system"], list)


# ── Samengevoegde nazorg-stap ──

@pytest.mark.asyncio
async def test_pipeline_merges_decisief_and_detection_into_one_call():
    """SOEP = 1 call, nazorg (decisief+detectie) = 1 call: totaal 2 LLM-calls."""
    soep_json = json.dumps({
        "s": "3d keelpijn", "o": "geen LO", "e": "virale faryngitis",
        "p": "expectatief", "icpc_code": "R74.01", "icpc_titel": "Acute infectie bovenste luchtwegen",
    })
    nazorg_json = json.dumps({
        "decisief": "Mw. 3d keelpijn → virale faryngitis (R74.01), expectatief",
        "rode_vlaggen": [],
        "ontbrekende_info": [{"veld": "allergieen", "beschrijving": "x", "prioriteit": "laag"}],
    })

    transcript = MagicMock()
    transcript.raw_text = "Goedemorgen, ik heb al drie dagen keelpijn."
    transcript.duration_secs = 42.0
    transcript.provider = "deepgram"

    complete_mock = AsyncMock(side_effect=[soep_json, nazorg_json])

    with patch.object(pipeline.stt_service, "transcribe",
                      new=AsyncMock(return_value=transcript)), \
         patch.object(pipeline.llm_service, "complete", new=complete_mock), \
         patch.object(pipeline, "correct_transcript_full",
                      return_value=(transcript.raw_text, MagicMock(total_corrections=0))):
        result = await pipeline.process_consultation(Path("/fake/audio.wav"))

    # Precies 2 LLM-calls (geen aparte decisief + detection meer)
    assert complete_mock.await_count == 2

    # Decisief en detectie komen uit de gecombineerde nazorg-call
    assert result.soep.icpc_code == "R74.01"
    assert "virale faryngitis" in result.decisief
    assert result.detection.rode_vlaggen == []
    assert result.detection.ontbrekende_info[0]["veld"] == "allergieen"

    # Per-call max_tokens correct doorgegeven
    soep_call, nazorg_call = complete_mock.await_args_list
    assert soep_call.kwargs["max_tokens"] == pipeline.SOEP_MAX_TOKENS
    assert nazorg_call.kwargs["max_tokens"] == pipeline.NAZORG_MAX_TOKENS


# ── Sprekers: wie zegt wat ──

from services.cloud_api import stt_service  # noqa: E402
from services.cloud_api.medical_vocabulary import correct_transcript_full  # noqa: E402


def _uiting(spreker, tekst):
    return stt_service.TranscriptSegment(text=tekst, start=0.0, end=1.0, speaker=spreker)


def _gesprek(*uitingen):
    tekst = " ".join(t for _, t in uitingen)
    return stt_service.TranscriptResult(
        raw_text=tekst, segments=[_uiting(s, t) for s, t in uitingen], provider="deepgram")


def test_met_sprekers_zet_elke_beurt_op_een_eigen_regel():
    t = _gesprek(("spreker_0", "Wat kan ik voor u doen?"),
                 ("spreker_1", "Ik heb al drie dagen keelpijn."),
                 ("spreker_1", "En koorts."),
                 ("spreker_0", "Ik kijk even in uw keel."))
    assert stt_service.met_sprekers(t) == (
        "Spreker 1: Wat kan ik voor u doen?\n"
        "Spreker 2: Ik heb al drie dagen keelpijn. En koorts.\n"
        "Spreker 1: Ik kijk even in uw keel.")


def test_met_sprekers_nummert_op_volgorde_van_binnenkomst():
    """Deepgram kan met spreker 3 beginnen; het model ziet gewoon Spreker 1."""
    t = _gesprek(("spreker_3", "Goedemorgen."), ("spreker_0", "Goedemorgen dokter."))
    assert stt_service.met_sprekers(t).startswith("Spreker 1: Goedemorgen.\nSpreker 2:")


def test_met_sprekers_laat_een_enkele_stem_ongemoeid():
    t = _gesprek(("spreker_0", "Pt drie dagen keelpijn."), ("spreker_0", "Geen koorts."))
    assert stt_service.met_sprekers(t) == t.raw_text


def test_met_sprekers_zonder_sprekers_of_segmenten():
    zonder = stt_service.TranscriptResult(
        raw_text="tekst", segments=[stt_service.TranscriptSegment(text="tekst", start=0, end=1)])
    assert stt_service.met_sprekers(zonder) == "tekst"
    assert stt_service.met_sprekers(stt_service.TranscriptResult(raw_text="los")) == "los"


def test_woordcorrectie_laat_de_sprekerlabels_staan():
    tekst = "Spreker 1: Hoe gaat het?\nSpreker 2: Ik gebruik metformine."
    uit, _ = correct_transcript_full(tekst)
    assert uit.splitlines()[0].startswith("Spreker 1:")
    assert uit.splitlines()[1].startswith("Spreker 2:")


@pytest.mark.asyncio
async def test_pipeline_geeft_het_gesprek_per_spreker_aan_het_taalmodel():
    soep_json = json.dumps({"s": "3d keelpijn", "o": "", "e": "", "p": "",
                            "icpc_code": "R74", "icpc_titel": "x"})
    nazorg_json = json.dumps({"decisief": "x", "rode_vlaggen": [], "ontbrekende_info": []})
    t = _gesprek(("spreker_0", "Wat kan ik voor u doen?"),
                 ("spreker_1", "Ik heb al drie dagen keelpijn."))
    complete_mock = AsyncMock(side_effect=[soep_json, nazorg_json])

    with patch.object(pipeline.stt_service, "transcribe", new=AsyncMock(return_value=t)), \
         patch.object(pipeline.llm_service, "complete", new=complete_mock):
        result = await pipeline.process_consultation(Path("/fake/audio.wav"))

    prompt = complete_mock.await_args_list[0].kwargs["user_prompt"]
    assert "Spreker 1: Wat kan ik voor u doen?\nSpreker 2: Ik heb al drie dagen keelpijn." in prompt
    assert result.transcript.startswith("Spreker 1:")
    assert result.transcript_raw == t.raw_text


def test_soep_prompt_kent_de_sprekerlabels():
    assert "Spreker 1" in pipeline.SOEP_SYSTEM_PROMPT
    assert "heteroanamnese" in pipeline.SOEP_SYSTEM_PROMPT
