#!/usr/bin/env python3
"""
VitaScribe - Linkbewaking voor de Thuisarts-koppeltabel

Links verlopen. Een pagina wordt hernoemd, samengevoegd of weggehaald, en dan
wijst de extensie de patiënt stilletjes naar een 404 of, erger, naar een pagina
over iets anders. Dit script loopt de tabel na en meldt wat er niet klopt.

  python3 scripts/check_thuisarts_links.py

Draait wekelijks vanaf de server (zie deploy/cron/vitascribe-thuisarts.cron) en
niet vanuit de browser van de arts: dan zou elk spreekuur de hele tabel
langsgaan, en zou thuisarts.nl kunnen zien hoe vaak een praktijk welke pagina
opvraagt.

Wat het WEL kan: zien of een adres nog bestaat en of het doorverwijst.
Wat het NIET kan: zien of de pagina nog over de juiste aandoening gaat. Een
doorverwijzing wordt daarom gemeld en niet gevolgd-en-goedgekeurd; dat oordeel
blijft bij een mens. Om dezelfde reden schrijft dit script niets in de tabel.
`gecontroleerd_op` betekent "met het oog gezien door `door`", en een 200 van
de server is dat niet: een pagina kan bereikbaar blijven terwijl de inhoud
naar een andere aandoening is verschoven. Een machine die die datum ververst,
laat een verouderde regel eruitzien als een verse controle.

Afsluitcode 0 als alles goed is, 1 als er iets te bekijken valt. Zo ziet cron
het verschil.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
TABEL = WORTEL / "chrome-extension" / "lib" / "thuisarts-icpc.json"

AGENT = "VitaScribe-linkcontrole/1.0 (+huisartsenpraktijk; wekelijkse controle van eigen tabel)"
WACHT = 15


class Geenvolg(urllib.request.HTTPRedirectHandler):
    """Een doorverwijzing is nieuws, geen omweg: we willen hem zien staan."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def controleer(url: str) -> tuple[str, str]:
    """(oordeel, toelichting) waarbij oordeel 'goed', 'verwijst' of 'stuk' is."""
    opener = urllib.request.build_opener(Geenvolg)
    verzoek = urllib.request.Request(url, headers={"User-Agent": AGENT}, method="GET")
    try:
        with opener.open(verzoek, timeout=WACHT) as antwoord:
            return ("goed", f"{antwoord.status}") if antwoord.status == 200 else ("stuk", str(antwoord.status))
    except urllib.error.HTTPError as fout:
        if fout.code in (301, 302, 303, 307, 308):
            doel = fout.headers.get("Location", "?")
            return "verwijst", f"{fout.code} naar {doel}"
        return "stuk", str(fout.code)
    except (urllib.error.URLError, TimeoutError, OSError) as fout:
        # Niet kunnen kijken is niet hetzelfde als stuk; dat verschil moet in
        # de melding blijven staan, anders haalt iemand een goede link weg.
        return "onbereikbaar", str(getattr(fout, "reason", fout))[:80]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.parse_args()

    tabel = json.loads(TABEL.read_text(encoding="utf-8"))
    rijen = [r for r in tabel["paginas"] if r.get("url")]
    zonder = len(tabel["paginas"]) - len(rijen)

    if not rijen:
        print(f"Geen enkele regel heeft een URL ({zonder} regels wachten op invulling).")
        print("Zie scripts/thuisarts_tabel.py; zolang de tabel leeg is toont de extensie geen link.")
        return 1

    gemeld = 0
    for rij in rijen:
        oordeel, toelichting = controleer(rij["url"])
        if oordeel == "goed":
            continue
        gemeld += 1
        print(f"{rij['icpc']:<4} {oordeel:<12} {rij['url']}  ({toelichting})")

    print(f"\n{len(rijen)} links gecontroleerd, {gemeld} met een opmerking"
          + (f", {zonder} regels nog zonder URL" if zonder else "") + ".")
    if gemeld:
        print("Een doorverwijzing wordt niet gevolgd: kijk zelf waar hij heen gaat voordat je de tabel aanpast.")
    return 1 if (gemeld or zonder) else 0


if __name__ == "__main__":
    sys.exit(main())
