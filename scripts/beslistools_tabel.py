#!/usr/bin/env python3
"""
VitaScribe - Koppeltabel ICPC -> ProVita Care nakijken en aanzetten

De tabel `chrome-extension/lib/beslistools-icpc.json` koppelt een ICPC-code aan
een naslagdeel in ProVita Care of een uitlegfilmpje voor de patiënt. Een regel
verschijnt pas in de extensie als een arts hem heeft nagekeken: de link
geopend en gezien dat de inhoud bij de code past.

  python3 scripts/beslistools_tabel.py --toon
      alle regels, met wat nog niet is nagekeken
  python3 scripts/beslistools_tabel.py --controleer fw-copd --door AB
      zet regel fw-copd aan, met vandaag als controledatum
  python3 scripts/beslistools_tabel.py --intrekken fw-copd
      zet een regel weer uit

Een regel toevoegen of een code wijzigen gaat met de hand in het JSON-bestand;
een nieuwe regel begint altijd met gecontroleerd_op en door op null.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

TABEL = Path(__file__).resolve().parent.parent / "chrome-extension" / "lib" / "beslistools-icpc.json"
BASIS = "https://www.provita-care.nl"
INITIALEN = re.compile(r"^[A-Za-z.]{1,8}$")


def lees() -> dict:
    return json.loads(TABEL.read_text(encoding="utf-8"))


def schrijf(tabel: dict) -> None:
    TABEL.write_text(json.dumps(tabel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def toon(tabel: dict) -> None:
    for r in tabel["links"]:
        staat = f"aan sinds {r['gecontroleerd_op']} ({r['door']})" if r.get("gecontroleerd_op") and r.get("door") else "NOG NAKIJKEN"
        print(f"{r['id']:<28} {','.join(r['icpc']):<18} {staat:<28} {BASIS}{r['pad']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--toon", action="store_true")
    ap.add_argument("--controleer", metavar="ID")
    ap.add_argument("--door", metavar="INITIALEN")
    ap.add_argument("--intrekken", metavar="ID")
    args = ap.parse_args()
    tabel = lees()
    per_id = {r["id"]: r for r in tabel["links"]}

    if args.controleer:
        if not args.door or not INITIALEN.match(args.door):
            print("Geef met --door je initialen mee.", file=sys.stderr)
            return 2
        r = per_id.get(args.controleer)
        if not r:
            print(f"Geen regel met id {args.controleer}.", file=sys.stderr)
            return 2
        r["gecontroleerd_op"] = date.today().isoformat()
        r["door"] = args.door
        schrijf(tabel)
        print(f"{args.controleer} staat aan: {BASIS}{r['pad']}")
        return 0
    if args.intrekken:
        r = per_id.get(args.intrekken)
        if not r:
            print(f"Geen regel met id {args.intrekken}.", file=sys.stderr)
            return 2
        r["gecontroleerd_op"] = None
        r["door"] = None
        schrijf(tabel)
        print(f"{args.intrekken} staat uit.")
        return 0
    toon(tabel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
