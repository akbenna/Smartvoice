"""pack_extension.sh: geen stille nieuwe sleutel, en het juiste extensie-ID.

crx3 maakt zonder waarschuwing een nieuwe sleutel als er op het pad geen staat.
Een tikfout gaf dus een nieuw extensie-ID, en dan pakt het beleid de extensie op
geen enkele werkplek meer op. Het script moet dat weigeren, en het ID dat het
in update.xml zet moet het ID zijn dat Chrome zelf uit de sleutel afleidt.

npx wordt hier vervangen door een stub die doet wat crx3 doet (sleutel maken
als hij ontbreekt, pakket schrijven), zodat de proef niet het net op hoeft.
"""

import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "pack_extension.sh"

FAKE_NPX = """#!/usr/bin/env bash
# Stand-in for `npx --yes crx3@1 -p KEY -o OUT DIR`: log the call, create the key
# when it is missing (as crx3 does), write a package.
echo "$@" >> "$NPX_LOG"
while [[ $# -gt 0 ]]; do
  case "$1" in -p) KEY="$2"; shift 2 ;; -o) OUT="$2"; shift 2 ;; *) shift ;; esac
done
[[ -e "$KEY" ]] || openssl genrsa -out "$KEY" 2048 2>/dev/null
echo "Cr24-fake" > "$OUT"
"""


def chrome_id(pem: Path) -> str:
    """The extension ID the way Chrome derives it, independent of the script."""
    key = serialization.load_pem_private_key(pem.read_bytes(), password=None)
    der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return "".join("abcdefghijklmnop"[int(c, 16)] for c in hashlib.sha256(der).hexdigest()[:32])


def make_key(path: Path) -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    return path


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npx = bin_dir / "npx"
    npx.write_text(FAKE_NPX)
    npx.chmod(0o755)
    log = tmp_path / "npx.log"
    out = tmp_path / "dist"

    def _run(*args):
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", NPX_LOG=str(log))
        res = subprocess.run(["bash", str(SCRIPT), *args, "https://server.test", str(out)],
                             capture_output=True, text=True, env=env)
        res.packed = log.exists()
        res.update_xml = (out / "update.xml").read_text() if (out / "update.xml").exists() else ""
        return res

    return _run


def test_missing_key_is_refused_without_the_flag(run, tmp_path):
    key = tmp_path / "vitascribe.pem"
    res = run(str(key))
    assert res.returncode == 1
    assert "--nieuwe-sleutel" in res.stderr
    assert not res.packed, "crx3 must not run, or it creates a key"
    assert not key.exists()


def test_new_key_only_when_asked_and_locked_down(run, tmp_path):
    key = tmp_path / "vitascribe.pem"
    res = run("--nieuwe-sleutel", str(key))
    assert res.returncode == 0, res.stderr
    assert key.exists()
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert f"appid='{chrome_id(key)}'" in res.update_xml
    assert "tweede veilige plek" in res.stdout


def test_new_key_flag_is_refused_when_a_key_exists(run, tmp_path):
    key = make_key(tmp_path / "vitascribe.pem")
    before = key.read_bytes()
    res = run("--nieuwe-sleutel", str(key))
    assert res.returncode == 1
    assert not res.packed
    assert key.read_bytes() == before


def test_existing_key_gives_the_id_chrome_would_compute(run, tmp_path):
    key = make_key(tmp_path / "vitascribe.pem")
    res = run(str(key))
    assert res.returncode == 0, res.stderr
    assert f"appid='{chrome_id(key)}'" in res.update_xml
    assert f"Extensie-ID: {chrome_id(key)}" in res.stdout
    assert "codebase='https://server.test/extension/vitascribe.crx'" in res.update_xml


def test_expected_id_mismatch_stops_before_packing(run, tmp_path):
    key = make_key(tmp_path / "vitascribe.pem")
    res = run("--verwacht-id", "a" * 32, str(key))
    assert res.returncode == 1
    assert chrome_id(key) in res.stderr
    assert not res.packed


def test_expected_id_match_packs(run, tmp_path):
    key = make_key(tmp_path / "vitascribe.pem")
    res = run("--verwacht-id", chrome_id(key), str(key))
    assert res.returncode == 0, res.stderr
    assert res.packed


def test_expected_id_and_new_key_exclude_each_other(run, tmp_path):
    res = run("--nieuwe-sleutel", "--verwacht-id", "a" * 32, str(tmp_path / "vitascribe.pem"))
    assert res.returncode == 2
    assert not res.packed


# sha256 of zero bytes, mapped to a-p: what a pipe yields when openssl reads
# nothing. It looks like any other ID, which is exactly the danger.
EMPTY_INPUT_ID = "".join("abcdefghijklmnop"[int(c, 16)] for c in hashlib.sha256(b"").hexdigest()[:32])


def test_a_file_that_is_not_a_key_is_refused(run, tmp_path):
    key = tmp_path / "vitascribe.pem"
    key.write_text("dit is geen sleutel")
    res = run(str(key))
    assert res.returncode == 1
    assert not res.packed
    assert EMPTY_INPUT_ID not in res.stdout + res.stderr + res.update_xml
