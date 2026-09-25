"""Extensiepakket: de overstap van SmartVoice naar VitaScribe mag geen werkplek stranden.

Werkplekken die eerder zijn geïnstalleerd hebben een update.xml die naar
/extension/smartvoice.crx wijst, en blijven daar vragen tot er een nieuwe
update.xml is gepubliceerd. Beide paden moeten dus hetzelfde pakket geven,
welke van de twee bestandsnamen er ook op schijf staat.
"""

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import main

PATHS = ("/extension/vitascribe.crx", "/extension/smartvoice.crx")


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.mark.parametrize("on_disk", ["vitascribe.crx", "smartvoice.crx"])
def test_both_paths_serve_the_package_whatever_its_file_name(client, monkeypatch, tmp_path, on_disk):
    (tmp_path / on_disk).write_bytes(b"Cr24-package")
    monkeypatch.setenv("EXTENSION_DIST_DIR", str(tmp_path))
    for path in PATHS:
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.content == b"Cr24-package"
        assert resp.headers["content-type"] == "application/x-chrome-extension"


def test_the_new_name_wins_when_both_files_exist(client, monkeypatch, tmp_path):
    (tmp_path / "vitascribe.crx").write_bytes(b"new")
    (tmp_path / "smartvoice.crx").write_bytes(b"old")
    monkeypatch.setenv("EXTENSION_DIST_DIR", str(tmp_path))
    for path in PATHS:
        assert client.get(path).content == b"new", path


def test_no_package_is_a_404_not_a_crash(client, monkeypatch, tmp_path):
    monkeypatch.setenv("EXTENSION_DIST_DIR", str(tmp_path))
    for path in PATHS:
        assert client.get(path).status_code == 404, path
    monkeypatch.delenv("EXTENSION_DIST_DIR")
    assert client.get(PATHS[0]).status_code == 404
