"""Thuisarts-koppeltabel, linkbewaking en de gebruiksregel.

Wat hier bewaakt wordt is steeds hetzelfde: er mag geen adres, geen tekst en
geen aandoening in het gebruikslog belanden, en er mag geen link naar de
patiënt gaan die niemand met het oog heeft gezien.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import main
from services.cloud_api.config import get_config

WORTEL = Path(__file__).resolve().parent.parent
TABEL = WORTEL / "chrome-extension" / "lib" / "thuisarts-icpc.json"
SEED = WORTEL / "services" / "learning" / "seed_data" / "soep_seed_examples.json"

ICPC = re.compile(r"^[A-Z]\d{2}$")


def _laad_script(naam: str):
    """De scripts staan buiten het pakket; hier los inladen."""
    pad = WORTEL / "scripts" / f"{naam}.py"
    spec = importlib.util.spec_from_file_location(naam, pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("API_USERS", "dr.bennaghmouch:sleutel-a")
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def tabel():
    return json.loads(TABEL.read_text(encoding="utf-8"))


# ── de tabel ─────────────────────────────────────────────────────────────────

def test_every_row_has_a_valid_icpc_and_title(tabel):
    assert tabel["paginas"], "de tabel is leeg"
    for rij in tabel["paginas"]:
        assert ICPC.match(rij["icpc"]), rij
        assert isinstance(rij["titel"], str) and rij["titel"].strip(), rij


def test_a_filled_url_points_to_thuisarts_and_is_checked(tabel):
    """Zolang de tabel nog geen adressen heeft, loopt deze proef leeg door; hij
    slaat toe zodra iemand er een invult zonder hem te controleren."""
    for rij in tabel["paginas"]:
        if not rij.get("url"):
            continue
        assert rij["url"].startswith("https://www.thuisarts.nl/"), rij
        assert rij.get("gecontroleerd_op"), f"{rij['icpc']} heeft een URL maar geen controledatum"
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", rij["gecontroleerd_op"]), rij
        assert rij.get("door"), f"{rij['icpc']} is gecontroleerd maar door niemand"


def test_every_seed_code_is_in_the_table(tabel):
    """Loopt de tabel achter op de voorbeeldbank, dan krijgt de arts bij een
    veelvoorkomende code geen pagina te zien zonder dat iemand dat merkt."""
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    codes = {
        (v["soep"].get("icpc_code") or "").strip().upper()
        for v in seed["examples"]
        if (v.get("soep") or {}).get("icpc_code")
    }
    gedekt = {r["icpc"] for r in tabel["paginas"]}
    uitzondering = {u["icpc"] for u in tabel.get("uitzonderingen", [])}
    ontbreekt = sorted(codes - gedekt - uitzondering)
    assert not ontbreekt, f"niet in de tabel en geen uitzondering: {ontbreekt}"


def test_an_exception_carries_a_reason(tabel):
    for uitzondering in tabel.get("uitzonderingen", []):
        assert ICPC.match(uitzondering["icpc"]), uitzondering
        assert uitzondering.get("reden", "").strip(), uitzondering


# ── de linkbewaking ──────────────────────────────────────────────────────────

class _Antwoord:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _nep_opener(monkeypatch, controle, gedrag):
    """Doet alsof thuisarts.nl antwoordt, zonder het net op te gaan."""
    import urllib.error

    class Opener:
        def open(self, verzoek, timeout=None):
            uitkomst = gedrag(verzoek.full_url)
            if isinstance(uitkomst, int) and uitkomst >= 300:
                raise urllib.error.HTTPError(
                    verzoek.full_url, uitkomst, "nep", {"Location": "https://www.thuisarts.nl/elders"}, None
                )
            return _Antwoord(uitkomst)

    monkeypatch.setattr(controle.urllib.request, "build_opener", lambda *a, **k: Opener())


def test_link_check_reports_a_404(monkeypatch, capsys):
    controle = _laad_script("check_thuisarts_links")
    _nep_opener(monkeypatch, controle, lambda url: 404)
    assert controle.controleer("https://www.thuisarts.nl/weg") == ("stuk", "404")


def test_link_check_reports_a_redirect_and_does_not_follow_it(monkeypatch):
    controle = _laad_script("check_thuisarts_links")
    _nep_opener(monkeypatch, controle, lambda url: 301)
    oordeel, toelichting = controle.controleer("https://www.thuisarts.nl/oud")
    assert oordeel == "verwijst"
    assert "301" in toelichting and "elders" in toelichting


def test_link_check_calls_unreachable_not_broken(monkeypatch):
    """Niet kunnen kijken is niet hetzelfde als kapot; anders haalt iemand bij
    een storing een goede link uit de tabel."""
    import urllib.error

    controle = _laad_script("check_thuisarts_links")

    class Opener:
        def open(self, *a, **k):
            raise urllib.error.URLError("naam niet gevonden")

    monkeypatch.setattr(controle.urllib.request, "build_opener", lambda *a, **k: Opener())
    assert controle.controleer("https://www.thuisarts.nl/x")[0] == "onbereikbaar"


def test_a_good_link_is_good(monkeypatch):
    controle = _laad_script("check_thuisarts_links")
    _nep_opener(monkeypatch, controle, lambda url: 200)
    assert controle.controleer("https://www.thuisarts.nl/hoesten") == ("goed", "200")


# ── de gebruiksregel ─────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(main.app)


def test_usage_logs_only_action_and_rubric(client, tmp_path):
    resp = client.post("/api/v1/usage", headers={"X-API-Key": "sleutel-a"},
                       json={"action": "patient.thuisarts", "kind": "R78"})
    assert resp.status_code == 200
    regel = json.loads((tmp_path / "audit.jsonl").read_text().strip().splitlines()[-1])
    assert regel["action"] == "patient.thuisarts"
    assert regel["kind"] == "R78"
    assert regel["user"] == "dr.bennaghmouch"
    assert "thuisarts.nl" not in json.dumps(regel)


def test_usage_rejects_a_url_or_free_text(client):
    """Een veld dat er niet hoort wordt geweigerd en niet stil weggelaten: wie
    per ongeluk tekst meestuurt, moet dat merken."""
    for extra in ({"url": "https://www.thuisarts.nl/hoesten"}, {"tekst": "Jan de Vries"}, {"e": "..."}):
        body = {"action": "patient.thuisarts", "kind": "R78"}
        body.update(extra)
        assert client.post("/api/v1/usage", headers={"X-API-Key": "sleutel-a"}, json=body).status_code == 422


def test_usage_rejects_an_unknown_action(client):
    resp = client.post("/api/v1/usage", headers={"X-API-Key": "sleutel-a"},
                       json={"action": "letters.generate", "kind": "R78"})
    assert resp.status_code == 400


def test_usage_rejects_a_kind_that_is_not_icpc(client):
    for kind in ("acute bronchitis", "R78.01", "<script>", "R7"):
        resp = client.post("/api/v1/usage", headers={"X-API-Key": "sleutel-a"},
                           json={"action": "patient.thuisarts", "kind": kind})
        assert resp.status_code in (400, 422), kind


def test_usage_requires_a_key(client):
    assert client.post("/api/v1/usage", json={"action": "patient.thuisarts", "kind": "R78"}).status_code in (401, 403)
