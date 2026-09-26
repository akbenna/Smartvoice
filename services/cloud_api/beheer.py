"""
VitaScribe Cloud API - Beheer van praktijken, gebruikers en licenties

  /beheer                  de beheerpagina (static/beheer.html)
  /api/v1/beheer/...       de gegevens erachter, alleen met X-Beheer-Sleutel

De beheersleutel is ADMIN_KEY uit de omgeving. Zonder ADMIN_KEY of zonder
register staat het beheer uit. Na tien foute pogingen vanaf één adres in een
kwartier weigert de server dat adres een kwartier lang.

Werkwijze, gelijk aan Bricks Companion maar op de server:

  aanmelding  een praktijk meldt zich via /aanmelden: status 'aangemeld',
              licentietype 'kandidaat'.
  activeren   de beheerder kiest het licentietype (pilot, betaald, intern), de
              vervaldatum (pilot: standaard twaalf maanden) en de
              praktijknummers, en maakt de gebruikers aan. Elke gebruiker krijgt
              een eigen sleutel, die één keer wordt getoond.
  uithalen    status 'uitgehaald': alle sleutels van de praktijk werken binnen
              een halve minuut niet meer.

Een sleutel van een gebruiker wordt nergens bewaard, alleen de sha256 ervan.
Kwijt is kwijt: dan maakt de beheerder een nieuwe, en werkt de oude niet meer.
"""

from __future__ import annotations

import hmac
import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import licentie, register

logger = structlog.get_logger()
router = APIRouter(tags=["beheer"])
STATIC = Path(__file__).parent / "static"

LICENTIETYPES = ("kandidaat", "pilot", "betaald", "intern")
STATUSSEN = ("aangemeld", "actief", "uitgehaald", "afgewezen")
ROLLEN = ("gebruiker", "praktijkbeheerder")
PILOT_MAANDEN = 12

_mislukt: Dict[str, List[float]] = {}


def _plus_maanden(d: date, maanden: int) -> date:
    jaar, maand = divmod(d.month - 1 + maanden, 12)
    jaar += d.year
    maand += 1
    import calendar
    dag = min(d.day, calendar.monthrange(jaar, maand)[1])
    return date(jaar, maand, dag)


def _adres(request: Request) -> str:
    """Het adres dat de proxy van Railway als laatste toevoegt. Het eerste deel
    van X-Forwarded-For kan de bezoeker zelf invullen."""
    kop = request.headers.get("x-forwarded-for", "")
    if kop:
        return kop.split(",")[-1].strip()
    return request.client.host if request.client else "?"


async def vereis_beheerder(request: Request, sleutel: Optional[str] = Header(default=None, alias="X-Beheer-Sleutel")) -> str:
    verwacht = (os.getenv("ADMIN_KEY") or "").strip()
    if not verwacht:
        raise HTTPException(status_code=503, detail="Beheer staat uit: ADMIN_KEY ontbreekt op de server.")
    if not register.actief():
        raise HTTPException(status_code=503, detail="Beheer staat uit: er is geen database gekoppeld (DATABASE_URL).")
    adres = _adres(request)
    nu = time.time()
    pogingen = [t for t in _mislukt.get(adres, []) if nu - t < 900]
    _mislukt[adres] = pogingen
    alle = [t for lijst in _mislukt.values() for t in lijst]
    if len(pogingen) >= 10 or len(alle) >= 50:
        raise HTTPException(status_code=429, detail="Te veel foute pogingen. Probeer het over een kwartier opnieuw.")
    if not sleutel or not hmac.compare_digest(sleutel.strip(), verwacht):
        pogingen.append(nu)
        raise HTTPException(status_code=403, detail="Onjuiste beheersleutel.")
    return "beheerder"


def _pagina(naam: str) -> FileResponse:
    return FileResponse(STATIC / naam, headers={
        "Cache-Control": "no-store",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'",
    })


@router.get("/beheer", include_in_schema=False)
async def beheerpagina():
    return _pagina("beheer.html")


@router.get("/beheer/beheer.js", include_in_schema=False)
async def beheerscript():
    return _pagina("beheer.js")


# ── Gegevens ──

PRAKTIJKVELDEN = ("naam", "plaats", "praktijknummers", "agb", "contact_naam", "contact_email", "telefoon",
                  "fte", "werkplekken", "licentietype", "status", "geldig_tot", "serienummer",
                  "eigen_sleutels_verplicht", "notities")


def _json(rij) -> dict:
    uit = {}
    for k, v in dict(rij).items():
        if isinstance(v, date):
            v = v.isoformat()
        elif hasattr(v, "isoformat"):
            v = v.isoformat()
        elif k == "fte" and v is not None:
            v = float(v)
        uit[k] = v
    return uit


class PraktijkInvoer(BaseModel):
    model_config = {"extra": "forbid"}
    naam: Optional[str] = Field(None, max_length=200)
    plaats: Optional[str] = Field(None, max_length=100)
    praktijknummers: Optional[List[str]] = None
    agb: Optional[str] = Field(None, max_length=20)
    contact_naam: Optional[str] = Field(None, max_length=200)
    contact_email: Optional[str] = Field(None, max_length=200)
    telefoon: Optional[str] = Field(None, max_length=40)
    fte: Optional[float] = Field(None, ge=0, le=999)
    werkplekken: Optional[int] = Field(None, ge=0, le=9999)
    licentietype: Optional[str] = None
    status: Optional[str] = None
    geldig_tot: Optional[date] = None
    geldig_tot_leeg: bool = False          # true = onbeperkt (alleen 'intern')
    serienummer: Optional[str] = Field(None, max_length=40)
    eigen_sleutels_verplicht: Optional[bool] = None
    notities: Optional[str] = Field(None, max_length=4000)


def _controleer(invoer: PraktijkInvoer) -> dict:
    velden = invoer.model_dump(exclude_unset=True)
    velden.pop("geldig_tot_leeg", None)
    if invoer.geldig_tot_leeg:
        velden["geldig_tot"] = None
    if "licentietype" in velden and velden["licentietype"] not in LICENTIETYPES:
        raise HTTPException(status_code=400, detail="Onbekend licentietype.")
    if "status" in velden and velden["status"] not in STATUSSEN:
        raise HTTPException(status_code=400, detail="Onbekende status.")
    if "praktijknummers" in velden:
        nummers = []
        for n in velden["praktijknummers"] or []:
            n = str(n).strip()
            if not licentie.PRAKTIJKNUMMER.match(n):
                raise HTTPException(status_code=400, detail=f"'{n}' is geen praktijknummer (3 tot 6 cijfers).")
            if n not in nummers:
                nummers.append(n)
        velden["praktijknummers"] = nummers
    if "naam" in velden and not (velden["naam"] or "").strip():
        raise HTTPException(status_code=400, detail="Een praktijk heeft een naam nodig.")
    return velden


async def _praktijk(pid: int) -> dict:
    rij = await register.fetchrow("SELECT * FROM vs_praktijken WHERE id = $1", pid)
    if not rij:
        raise HTTPException(status_code=404, detail="Deze praktijk bestaat niet.")
    return _json(rij)


@router.get("/api/v1/beheer/praktijken")
async def praktijken(_: str = Depends(vereis_beheerder)):
    rijen = await register.fetch(
        """
        SELECT p.*,
               (SELECT count(*) FROM vs_gebruikers g WHERE g.praktijk_id = p.id AND g.actief) AS gebruikers_actief,
               (SELECT count(*) FROM vs_gebruikers g WHERE g.praktijk_id = p.id) AS gebruikers_totaal,
               (SELECT max(laatst_gezien) FROM vs_gebruikers g WHERE g.praktijk_id = p.id) AS laatst_gebruikt,
               COALESCE((SELECT json_agg(json_build_object('dienst', s.dienst, 'aanbieder', s.aanbieder, 'hint', s.hint))
                           FROM vs_praktijk_sleutels s WHERE s.praktijk_id = p.id), '[]'::json) AS eigen_sleutels
          FROM vs_praktijken p
         ORDER BY CASE p.status WHEN 'aangemeld' THEN 0 WHEN 'actief' THEN 1 ELSE 2 END, p.naam
        """
    )
    uit = []
    for r in rijen:
        d = _json(r)
        d["eigen_sleutels"] = json.loads(d["eigen_sleutels"]) if isinstance(d["eigen_sleutels"], str) else d["eigen_sleutels"]
        uit.append(d)
    return {"praktijken": uit, "vandaag": licentie.vandaag().isoformat(), "pilot_maanden": PILOT_MAANDEN}


@router.post("/api/v1/beheer/praktijken")
async def praktijk_maken(invoer: PraktijkInvoer, door: str = Depends(vereis_beheerder)):
    velden = _controleer(invoer)
    if not velden.get("naam"):
        raise HTTPException(status_code=400, detail="Een praktijk heeft een naam nodig.")
    kolommen = [k for k in velden if k in PRAKTIJKVELDEN]
    rij = await register.fetchrow(
        f"INSERT INTO vs_praktijken ({', '.join(kolommen)}) VALUES ({', '.join(f'${i + 1}' for i in range(len(kolommen)))}) RETURNING id",
        *[velden[k] for k in kolommen],
    )
    await register.log(door, "praktijk.gemaakt", rij["id"], naam=velden["naam"])
    return await _praktijk(rij["id"])


@router.patch("/api/v1/beheer/praktijken/{pid}")
async def praktijk_wijzigen(pid: int, invoer: PraktijkInvoer, door: str = Depends(vereis_beheerder)):
    oud = await _praktijk(pid)
    velden = _controleer(invoer)
    # Activeren zonder datum: twaalf maanden vanaf vandaag. Alleen de eigen
    # praktijk (intern) mag onbeperkt; een derde nooit zonder dat je het kiest.
    type_ = velden.get("licentietype", oud["licentietype"])
    if (velden.get("status") == "actief" and "geldig_tot" not in velden and oud["geldig_tot"] is None
            and type_ != "intern"):
        velden["geldig_tot"] = _plus_maanden(licentie.vandaag(), PILOT_MAANDEN)
    kolommen = [k for k in velden if k in PRAKTIJKVELDEN]
    if kolommen:
        zet = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(kolommen))
        await register.execute(f"UPDATE vs_praktijken SET {zet}, bijgewerkt_op = now() WHERE id = $1",
                               pid, *[velden[k] for k in kolommen])
        licentie.wis_cache()
        await register.log(door, "praktijk.gewijzigd", pid,
                           velden={k: (str(velden[k]) if k != "notities" else "…") for k in kolommen})
    return await _praktijk(pid)


@router.post("/api/v1/beheer/praktijken/{pid}/verlengen")
async def praktijk_verlengen(pid: int, door: str = Depends(vereis_beheerder)):
    """Twaalf maanden erbij, vanaf de huidige einddatum of vandaag als die al voorbij is."""
    oud = await _praktijk(pid)
    basis = licentie.vandaag()
    if oud["geldig_tot"]:
        huidig = date.fromisoformat(oud["geldig_tot"])
        basis = max(basis, huidig)
    nieuw = _plus_maanden(basis, PILOT_MAANDEN)
    await register.execute("UPDATE vs_praktijken SET geldig_tot = $2, bijgewerkt_op = now() WHERE id = $1", pid, nieuw)
    licentie.wis_cache()
    await register.log(door, "praktijk.verlengd", pid, tot=nieuw.isoformat())
    return await _praktijk(pid)


@router.delete("/api/v1/beheer/praktijken/{pid}/sleutels/{dienst}")
async def praktijksleutel_verwijderen(pid: int, dienst: str, door: str = Depends(vereis_beheerder)):
    """De beheerder kan een eigen sleutel van een praktijk weghalen, niet lezen."""
    await _praktijk(pid)
    await register.execute("DELETE FROM vs_praktijk_sleutels WHERE praktijk_id = $1 AND dienst = $2", pid, dienst)
    await register.log(door, "praktijk.sleutel_verwijderd", pid, dienst=dienst)
    return await _praktijk(pid)


# ── Gebruikers ──

class GebruikerInvoer(BaseModel):
    model_config = {"extra": "forbid"}
    naam: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=200)
    rol: Optional[str] = None
    actief: Optional[bool] = None


GEBRUIKERVELDEN = "id, praktijk_id, naam, email, rol, sleutel_hint, actief, aangemaakt_op, laatst_gezien, laatst_praktijknummer"


@router.get("/api/v1/beheer/praktijken/{pid}/gebruikers")
async def gebruikers(pid: int, _: str = Depends(vereis_beheerder)):
    await _praktijk(pid)
    rijen = await register.fetch(f"SELECT {GEBRUIKERVELDEN} FROM vs_gebruikers WHERE praktijk_id = $1 ORDER BY naam", pid)
    return {"gebruikers": [_json(r) for r in rijen]}


@router.post("/api/v1/beheer/praktijken/{pid}/gebruikers")
async def gebruiker_maken(pid: int, invoer: GebruikerInvoer, door: str = Depends(vereis_beheerder)):
    await _praktijk(pid)
    naam = (invoer.naam or "").strip()
    if not naam:
        raise HTTPException(status_code=400, detail="Een gebruiker heeft een naam nodig.")
    rol = invoer.rol or "gebruiker"
    if rol not in ROLLEN:
        raise HTTPException(status_code=400, detail="Onbekende rol.")
    sleutel = licentie.nieuwe_sleutel()
    rij = await register.fetchrow(
        f"INSERT INTO vs_gebruikers (praktijk_id, naam, email, rol, sleutel_hash, sleutel_hint) "
        f"VALUES ($1, $2, $3, $4, $5, $6) RETURNING {GEBRUIKERVELDEN}",
        pid, naam, (invoer.email or "").strip(), rol, licentie.sleutel_hash(sleutel), licentie.hint(sleutel),
    )
    await register.log(door, "gebruiker.gemaakt", pid, gebruiker=rij["id"], rol=rol)
    return {"gebruiker": _json(rij), "sleutel": sleutel}


async def _gebruiker(gid: int) -> dict:
    rij = await register.fetchrow(f"SELECT {GEBRUIKERVELDEN} FROM vs_gebruikers WHERE id = $1", gid)
    if not rij:
        raise HTTPException(status_code=404, detail="Deze gebruiker bestaat niet.")
    return _json(rij)


@router.patch("/api/v1/beheer/gebruikers/{gid}")
async def gebruiker_wijzigen(gid: int, invoer: GebruikerInvoer, door: str = Depends(vereis_beheerder)):
    oud = await _gebruiker(gid)
    velden = invoer.model_dump(exclude_unset=True)
    if "rol" in velden and velden["rol"] not in ROLLEN:
        raise HTTPException(status_code=400, detail="Onbekende rol.")
    if "naam" in velden and not (velden["naam"] or "").strip():
        raise HTTPException(status_code=400, detail="Een gebruiker heeft een naam nodig.")
    if velden:
        kolommen = list(velden)
        zet = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(kolommen))
        await register.execute(f"UPDATE vs_gebruikers SET {zet} WHERE id = $1", gid, *[velden[k] for k in kolommen])
        licentie.wis_cache()
        await register.log(door, "gebruiker.gewijzigd", oud["praktijk_id"], gebruiker=gid,
                           velden={k: str(v) for k, v in velden.items() if k != "email"})
    return await _gebruiker(gid)


@router.post("/api/v1/beheer/gebruikers/{gid}/nieuwe-sleutel")
async def gebruiker_nieuwe_sleutel(gid: int, door: str = Depends(vereis_beheerder)):
    """Een nieuwe sleutel; de oude werkt direct niet meer."""
    oud = await _gebruiker(gid)
    sleutel = licentie.nieuwe_sleutel()
    await register.execute("UPDATE vs_gebruikers SET sleutel_hash = $2, sleutel_hint = $3 WHERE id = $1",
                           gid, licentie.sleutel_hash(sleutel), licentie.hint(sleutel))
    licentie.wis_cache()
    await register.log(door, "gebruiker.nieuwe_sleutel", oud["praktijk_id"], gebruiker=gid)
    return {"gebruiker": await _gebruiker(gid), "sleutel": sleutel}


# ── Instellingen, log en export ──

class Instellingen(BaseModel):
    model_config = {"extra": "forbid"}
    tarief_per_fte: Optional[float] = Field(None, ge=0, le=1_000_000)
    serveradres: Optional[str] = Field(None, max_length=200)
    winkellink: Optional[str] = Field(None, max_length=500)


@router.get("/api/v1/beheer/instellingen")
async def instellingen_lezen(_: str = Depends(vereis_beheerder)):
    rijen = await register.fetch("SELECT sleutel, waarde FROM vs_instellingen")
    uit = {r["sleutel"]: r["waarde"] for r in rijen}
    return {
        "tarief_per_fte": float(uit["tarief_per_fte"]) if uit.get("tarief_per_fte") else None,
        "serveradres": uit.get("serveradres", ""),
        "winkellink": uit.get("winkellink", ""),
    }


@router.put("/api/v1/beheer/instellingen")
async def instellingen_opslaan(invoer: Instellingen, door: str = Depends(vereis_beheerder)):
    for k, v in invoer.model_dump(exclude_unset=True).items():
        await register.execute(
            "INSERT INTO vs_instellingen (sleutel, waarde) VALUES ($1, $2) "
            "ON CONFLICT (sleutel) DO UPDATE SET waarde = EXCLUDED.waarde", k, "" if v is None else str(v))
    await register.log(door, "instellingen.gewijzigd")
    return await instellingen_lezen(door)


@router.get("/api/v1/beheer/log")
async def beheerlog(_: str = Depends(vereis_beheerder)):
    rijen = await register.fetch(
        "SELECT l.op, l.door, l.handeling, l.praktijk_id, p.naam AS praktijk, l.details "
        "FROM vs_beheerlog l LEFT JOIN vs_praktijken p ON p.id = l.praktijk_id ORDER BY l.op DESC LIMIT 200")
    uit = []
    for r in rijen:
        d = _json(r)
        d["details"] = json.loads(d["details"]) if isinstance(d["details"], str) else d["details"]
        uit.append(d)
    return {"log": uit}


@router.get("/api/v1/beheer/export")
async def export(_: str = Depends(vereis_beheerder)):
    """Het register als JSON, om naast de database te bewaren. Zonder sleutels
    van gebruikers (die bestaan nergens) en zonder de versleutelde sleutels van
    praktijken (alleen welke dienst en aanbieder)."""
    praktijk_rijen = await register.fetch("SELECT * FROM vs_praktijken ORDER BY id")
    gebruiker_rijen = await register.fetch(f"SELECT {GEBRUIKERVELDEN} FROM vs_gebruikers ORDER BY id")
    sleutel_rijen = await register.fetch("SELECT praktijk_id, dienst, aanbieder, hint, ingesteld_op FROM vs_praktijk_sleutels")
    inhoud = {
        "gemaakt_op": licentie.vandaag().isoformat(),
        "praktijken": [_json(r) for r in praktijk_rijen],
        "gebruikers": [_json(r) for r in gebruiker_rijen],
        "eigen_sleutels": [_json(r) for r in sleutel_rijen],
    }
    return JSONResponse(inhoud, headers={
        "Content-Disposition": f'attachment; filename="vitascribe-register-{inhoud["gemaakt_op"]}.json"',
        "Cache-Control": "no-store",
    })
