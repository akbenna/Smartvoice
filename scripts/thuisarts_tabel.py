#!/usr/bin/env python3
"""
SmartVoice - Koppeltabel ICPC -> Thuisarts.nl klaarzetten en nakijken

De tabel in `chrome-extension/lib/thuisarts-icpc.json` hoort dezelfde codes te
dekken als de voorbeeldbank waar de SOEP-herkenning op steunt. Loopt dat uit
elkaar, dan krijgt de arts bij een veelvoorkomende code geen pagina te zien
zonder dat iemand dat merkt. Dit script houdt de twee gelijk:

  python3 scripts/thuisarts_tabel.py            toont wat er ontbreekt
  python3 scripts/thuisarts_tabel.py --aanvullen  zet ontbrekende codes erbij

Wat het NIET doet is een URL verzinnen. Een adres op thuisarts.nl valt niet uit
de ICPC-code af te leiden, en een link die wel opent maar over een andere
aandoening gaat is erger dan geen link: de patiënt leest dan met vertrouwen het
verkeerde. Het invullen is daarom mensenwerk, één keer, met het oog. Het script
zet de regel klaar met `url: null`; wie hem invult zet zijn initialen in `door`
en de datum in `gecontroleerd_op`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
TABEL = WORTEL / "chrome-extension" / "lib" / "thuisarts-icpc.json"
SEED = WORTEL / "services" / "learning" / "seed_data" / "soep_seed_examples.json"

ICPC = re.compile(r"^[A-Z]\d{2}$")


def seed_codes() -> dict[str, str]:
    """De ICPC-codes uit de voorbeeldbank, met hun titel."""
    data = json.loads(SEED.read_text(encoding="utf-8"))
    uit: dict[str, str] = {}
    for voorbeeld in data.get("examples", []):
        soep = voorbeeld.get("soep") or {}
        code = (soep.get("icpc_code") or "").strip().upper()
        if ICPC.match(code):
            uit.setdefault(code, (soep.get("icpc_titel") or "").strip())
    return dict(sorted(uit.items()))


def lees_tabel() -> dict:
    return json.loads(TABEL.read_text(encoding="utf-8"))


def schrijf_tabel(tabel: dict) -> None:
    TABEL.write_text(json.dumps(tabel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aanvullen", action="store_true", help="ontbrekende codes als lege regel toevoegen")
    args = p.parse_args()

    codes = seed_codes()
    tabel = lees_tabel()
    rijen = tabel["paginas"]
    gedekt = {r["icpc"] for r in rijen}
    uitzondering = {u["icpc"] for u in tabel.get("uitzonderingen", [])}

    ontbreekt = [c for c in codes if c not in gedekt and c not in uitzondering]
    zonder_url = sorted({r["icpc"] for r in rijen if not r.get("url")})
    ongecontroleerd = sorted({r["icpc"] for r in rijen if r.get("url") and not r.get("gecontroleerd_op")})
    vreemd = sorted({r["icpc"] for r in rijen} - set(codes) - uitzondering)

    if args.aanvullen and ontbreekt:
        for code in ontbreekt:
            rijen.append({"icpc": code, "titel": codes[code], "url": None,
                          "gecontroleerd_op": None, "door": None})
        tabel["paginas"] = sorted(rijen, key=lambda r: (r["icpc"], r.get("titel") or ""))
        schrijf_tabel(tabel)
        print(f"{len(ontbreekt)} regels toegevoegd; vul de URL met de hand in.")
        return 0

    print(f"Voorbeeldbank: {len(codes)} codes. Tabel: {len(rijen)} regels over {len(gedekt)} codes.")
    if ontbreekt:
        print(f"\nNiet in de tabel ({len(ontbreekt)}): " + ", ".join(ontbreekt))
        print("  Draai met --aanvullen, of zet ze in 'uitzonderingen' met een reden.")
    if zonder_url:
        print(f"\nNog zonder URL ({len(zonder_url)}): " + ", ".join(zonder_url))
        print("  Zoek de pagina op thuisarts.nl, plak het adres, zet je initialen in 'door'")
        print("  en vandaag in 'gecontroleerd_op'. Pas dan toont de extensie de link.")
    if ongecontroleerd:
        print(f"\nURL zonder controledatum ({len(ongecontroleerd)}): " + ", ".join(ongecontroleerd))
    if vreemd:
        print(f"\nIn de tabel maar niet in de voorbeeldbank ({len(vreemd)}): " + ", ".join(vreemd))
        print("  Dat mag - de tabel mag ruimer zijn dan de seed - maar kijk of het klopt.")
    if not (ontbreekt or zonder_url or ongecontroleerd):
        print("\nDe tabel is volledig en gecontroleerd.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
