"""
Vocabulary Learner (Fase 2, niveau 1)
=====================================

De eerste echte zelflerende lus:

    arts corrigeert transcript  (consultation_feedback)
        -> diff-miner haalt (fout -> goed)-paren eruit
        -> aggregatie telt bevestigingen over consulten heen
        -> promotie bij voldoende, consistente bevestiging
        -> upsert in vocabulary_corrections (is_active)
        -> export naar custom_vocabulary.json
        -> volgende transcriptie verstaat de term al (hotwords)
           en corrigeert hem alsnog (naberekening)

Ontwerpprincipes:
- Veiligheid boven snelheid: een bevestigingsdrempel én een dominantie-eis
  voorkomen dat een eenmalige typefout of dialectincident de lijst vervuilt.
- Idempotent: de job mag onbeperkt herdraaien. We tellen bevestigingen over
  ALLE feedback en zetten (niet: increment) times_confirmed = waargenomen
  aantal, zodat herhaald draaien hetzelfde resultaat geeft.
- Hand-gemaakte (source='manual') correcties worden nooit overschreven.

De pure functies (mine/aggregate/select) bevatten geen DB en zijn los
unit-testbaar; de DB/IO zit in VocabularyLearner.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog

from services.learning.diff_miner import mine_corrections

logger = structlog.get_logger()

# SQLAlchemy is optioneel op importmoment: zo blijven de pure functies en de
# job (met een injecteerbare sessie) testbaar zonder de DB-stack.
try:
    from sqlalchemy import text as _sa_text
except Exception:  # pragma: no cover
    _sa_text = None


def _sql(query: str):
    """Wikkel ruwe SQL in een SQLAlchemy text()-clause indien beschikbaar."""
    return _sa_text(query) if _sa_text is not None else query


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

@dataclass
class LearnerConfig:
    # Aantal onafhankelijke bevestigingen (feedbackrijen) voor activatie
    min_confirmations: int = int(os.getenv("VOCAB_LEARN_MIN_CONFIRMATIONS", "3"))
    # Aandeel dat de dominante 'goed'-variant minimaal moet hebben (consistentie)
    min_dominance: float = float(os.getenv("VOCAB_LEARN_MIN_DOMINANCE", "0.6"))
    # Vanaf hoeveel bevestigingen bewaren we een kandidaat al (zichtbaarheid)
    persist_floor: int = int(os.getenv("VOCAB_LEARN_PERSIST_FLOOR", "2"))
    # Doelbestand voor de geleerde woordenlijst (gelezen door transcriptieservice)
    custom_vocab_path: str = os.getenv(
        "WHISPER_CUSTOM_VOCAB_PATH", "/data/vocabulary/custom_vocabulary.json"
    )


# ──────────────────────────────────────────────────────────────────────
# Pure kern: aggregatie + promotie
# ──────────────────────────────────────────────────────────────────────

@dataclass
class AggregatedCandidate:
    wrong: str
    correct: str            # dominante 'goed'-variant
    confirmations: int      # aantal feedbackrijen met deze dominante mapping
    total_observations: int # alle mappings voor 'wrong' samen
    dominance: float        # confirmations / total_observations

    @property
    def is_consistent(self) -> bool:
        return self.dominance >= 0.0  # placeholder; echte check in select_promotions


def aggregate_candidates(
    feedback_pairs: List[Tuple[str, str]],
) -> List[AggregatedCandidate]:
    """Tel kandidaat-correcties over alle feedbackparen heen.

    Per feedbackpaar telt een (fout -> goed) hoogstens één keer mee (dedupe in
    de diff-miner), zodat 'confirmations' = aantal onafhankelijke consulten.
    """
    # wrong -> { correct -> aantal feedbackrijen }
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for original, corrected in feedback_pairs:
        for cand in mine_corrections(original, corrected):
            counts[cand.wrong][cand.correct] += 1

    result: List[AggregatedCandidate] = []
    for wrong, variants in counts.items():
        total = sum(variants.values())
        correct, dom_count = max(variants.items(), key=lambda kv: kv[1])
        result.append(AggregatedCandidate(
            wrong=wrong,
            correct=correct,
            confirmations=dom_count,
            total_observations=total,
            dominance=dom_count / total if total else 0.0,
        ))
    # Sorteer aflopend op bevestigingen voor leesbare logs
    result.sort(key=lambda c: c.confirmations, reverse=True)
    return result


def select_promotions(
    candidates: List[AggregatedCandidate],
    cfg: LearnerConfig,
) -> List[AggregatedCandidate]:
    """Welke kandidaten worden ACTIEF (voldoende én consistent bevestigd)?"""
    return [
        c for c in candidates
        if c.confirmations >= cfg.min_confirmations and c.dominance >= cfg.min_dominance
    ]


# ──────────────────────────────────────────────────────────────────────
# DB/IO-laag
# ──────────────────────────────────────────────────────────────────────

@dataclass
class LearnerReport:
    feedback_rows: int = 0
    candidates: int = 0
    promoted: int = 0
    persisted: int = 0
    exported_terms: int = 0
    promoted_pairs: List[Tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feedback_rows": self.feedback_rows,
            "candidates": self.candidates,
            "promoted": self.promoted,
            "persisted": self.persisted,
            "exported_terms": self.exported_terms,
            "promoted_pairs": self.promoted_pairs,
        }


class VocabularyLearner:
    """Draait de zelflerende lus tegen de database."""

    def __init__(self, cfg: Optional[LearnerConfig] = None):
        self.cfg = cfg or LearnerConfig()

    async def fetch_feedback_pairs(self, session) -> List[Tuple[str, str]]:
        """Haal alle bruikbare (origineel, gecorrigeerd) transcriptparen op."""
        rows = await session.execute(_sql(
            """
            SELECT transcript_original, transcript_corrected
            FROM consultation_feedback
            WHERE transcript_original IS NOT NULL
              AND transcript_corrected IS NOT NULL
              AND transcript_original <> transcript_corrected
            """
        ))
        return [(r[0], r[1]) for r in rows.all()]

    async def persist(self, session, candidates: List[AggregatedCandidate]) -> int:
        """Upsert geleerde kandidaten. Hand-gemaakte correcties blijven ongemoeid."""
        stmt = _sql(
            """
            INSERT INTO vocabulary_corrections
                (wrong_text, correct_text, category, times_confirmed, is_active, source)
            VALUES (:wrong, :correct, 'learned', :conf, :active, 'learned')
            ON CONFLICT (wrong_text, correct_text) DO UPDATE SET
                times_confirmed = EXCLUDED.times_confirmed,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
            WHERE vocabulary_corrections.source <> 'manual'
            """
        )
        persisted = 0
        for c in candidates:
            if c.confirmations < self.cfg.persist_floor:
                continue
            active = (
                c.confirmations >= self.cfg.min_confirmations
                and c.dominance >= self.cfg.min_dominance
            )
            await session.execute(stmt, {
                "wrong": c.wrong,
                "correct": c.correct,
                "conf": c.confirmations,
                "active": active,
            })
            persisted += 1
        return persisted

    async def fetch_active_mapping(self, session) -> Dict[str, str]:
        """Haal alle actieve correcties (manueel + geleerd) als {fout: goed}."""
        rows = await session.execute(_sql(
            """
            SELECT wrong_text, correct_text
            FROM vocabulary_corrections
            WHERE is_active = TRUE
            """
        ))
        mapping: Dict[str, str] = {}
        for wrong, correct in rows.all():
            mapping[str(wrong).lower()] = correct
        return mapping

    def export_custom_vocabulary(self, mapping: Dict[str, str]) -> int:
        """Schrijf de geleerde woordenlijst naar het bestand dat de
        transcriptieservice bij het opstarten inleest."""
        path = Path(self.cfg.custom_vocab_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        logger.info("vocabulary.exported", path=str(path), count=len(mapping))
        return len(mapping)

    async def run(self, session) -> LearnerReport:
        """Voer de volledige lus uit en geef een rapport terug."""
        report = LearnerReport()

        pairs = await self.fetch_feedback_pairs(session)
        report.feedback_rows = len(pairs)

        candidates = aggregate_candidates(pairs)
        report.candidates = len(candidates)

        promoted = select_promotions(candidates, self.cfg)
        report.promoted = len(promoted)
        report.promoted_pairs = [(c.wrong, c.correct) for c in promoted]

        report.persisted = await self.persist(session, candidates)
        await session.commit()

        mapping = await self.fetch_active_mapping(session)
        report.exported_terms = self.export_custom_vocabulary(mapping)

        logger.info(
            "vocabulary.learn_run_complete",
            feedback_rows=report.feedback_rows,
            candidates=report.candidates,
            promoted=report.promoted,
            persisted=report.persisted,
            exported=report.exported_terms,
        )
        return report
