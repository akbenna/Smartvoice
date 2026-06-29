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
