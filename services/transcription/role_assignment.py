"""
Rolherkenning arts / patiënt
============================

Vervangt de fragiele aanname "eerste spreker = arts" door een taalkundige
beoordeling: wie stelt de vragen, geeft beleid en gebruikt medische termen
(arts), versus wie beschrijft klachten in de ik-vorm (patiënt). Robuust voor
wie het consult opent en voor een derde stem (kind/mantelzorger/tolk).

Pure stdlib, deterministisch en unit-testbaar. Scores worden genormaliseerd op
tekstlengte zodat een lange beurt niet automatisch "wint".
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

_WORD_RE = re.compile(r"[a-zà-ÿ]+", flags=re.IGNORECASE)

# Arts-cues: vragen stellen, beleid/advies geven, onderzoek beschrijven
_ARTS_PHRASES = [
    "sinds wanneer", "hoe lang", "hoe vaak", "kunt u", "heeft u", "hebt u",
    "doet het pijn", "waar precies", "ik adviseer", "ik schrijf", "ik geef u",
    "ik wil dat u", "we gaan", "ik onderzoek", "ik luister", "ik voel hier",
    "ik zie", "ik hoor", "adem in", "ademt u", "recept", "verwijzing",
    "verwijs", "controle", "bloeddruk meten", "ik denk aan", "we spreken af",
    "neem dit", "drie keer per dag", "kom terug", "laat ik",
]
_ARTS_WORDS = {
    "hoe", "waar", "wanneer", "waarom", "welke", "diagnose", "onderzoek",
    "beleid", "advies", "controle", "recept", "verwijzing", "medicatie",
    "dosering", "uitslag",
}

# Patiënt-cues: klachten in ik-vorm, lichamelijke beleving
_PATIENT_PHRASES = [
    "ik heb", "ik voel", "ik ben", "ik kan niet", "ik merk", "ik word",
    "last van", "het doet pijn", "mijn hoofd", "mijn buik", "mijn rug",
    "al een week", "al dagen", "de laatste tijd", "ik slaap", "ik durf",
    "ik maak me zorgen", "het gaat niet", "ik krijg",
]
_PATIENT_WORDS = {
    "mijn", "pijn", "moe", "misselijk", "duizelig", "benauwd", "zorgen",
    "bang", "vervelend",
}


def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def _count_phrases(text: str, phrases: List[str]) -> int:
    t = (text or "").lower()
    return sum(t.count(p) for p in phrases)


def _score(text: str) -> float:
    """Differentieel: positief = arts-achtig, negatief = patiënt-achtig.
    Genormaliseerd per 100 tokens."""
    toks = _tokens(text)
    n = max(len(toks), 1)
    tokset = toks

    arts = _count_phrases(text, _ARTS_PHRASES) * 2.0
    arts += sum(1 for w in tokset if w in _ARTS_WORDS)
    arts += (text or "").count("?") * 1.5  # vragen ~ arts

    patient = _count_phrases(text, _PATIENT_PHRASES) * 2.0
    patient += sum(1 for w in tokset if w in _PATIENT_WORDS)

    # Medische terminologie pleit voor arts (best-effort)
    arts += _medical_term_hits(tokset) * 1.0

    return (arts - patient) / n * 100.0


_MED_TERMS: Optional[set] = None


def _medical_term_hits(tokens: List[str]) -> int:
    global _MED_TERMS
    if _MED_TERMS is None:
        try:
            from shared.vocabulary import (
                MEDICATION_CORRECTIONS,
                MEDICAL_TERM_CORRECTIONS,
            )
            terms = set()
            for v in list(MEDICATION_CORRECTIONS.values()) + list(MEDICAL_TERM_CORRECTIONS.values()):
                for w in v.lower().split():
                    if len(w) > 3:
                        terms.add(w)
            _MED_TERMS = terms
        except Exception:
            _MED_TERMS = set()
    if not _MED_TERMS:
        return 0
    return sum(1 for t in tokens if t in _MED_TERMS)


def assign_roles(
    speaker_texts: Dict[str, str],
    speaker_order: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Wijs elke diarisatie-spreker een rol toe.

    Args:
        speaker_texts: {spreker_label: alle tekst van die spreker}
        speaker_order: volgorde van eerste optreden (fallback bij gelijke score)

    Returns:
        {spreker_label: "arts" | "patient" | "spreker_3" | ...}
    """
    labels = list(speaker_texts.keys())
    if not labels:
        return {}
    order = speaker_order or labels

    if len(labels) == 1:
        return {labels[0]: "arts"}

    # Score per spreker; sorteer aflopend (meest arts-achtig eerst).
    scored = sorted(
        labels,
        key=lambda lbl: (_score(speaker_texts[lbl]), -order.index(lbl) if lbl in order else 0),
        reverse=True,
    )

    roles: Dict[str, str] = {}
    arts_label = scored[0]
    roles[arts_label] = "arts"

    # Meest patiënt-achtige (laagste score) -> patiënt
    patient_label = scored[-1]
    roles[patient_label] = "patient"

    # Overige sprekers -> spreker_3, spreker_4, ... in volgorde van optreden
    n = 3
    for lbl in order:
        if lbl in roles:
            continue
        roles[lbl] = f"spreker_{n}"
        n += 1
    # Labels die niet in order stonden
    for lbl in labels:
        if lbl not in roles:
            roles[lbl] = f"spreker_{n}"
            n += 1
    return roles
