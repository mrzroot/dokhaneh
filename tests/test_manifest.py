import base64
import subprocess

import pytest

from dokhaneh.manifest import (
    Manifest,
    ManifestError,
    build_manifest,
    generate_keypair,
    load_signing_key,
    public_key_pem,
    sign_bytes,
    verify_files,
    verify_signature,
)


def test_keypair_roundtrip(keys):
    sk = load_signing_key(keys["private"])
    assert base64.b64encode(bytes(sk.verify_key)).decode() == keys["public"]


def test_sign_and_verify(keys):
    data = b"hello"
    sig = sign_bytes(data, keys["private"])
    assert verify_signature(data, sig, keys["public"])
    assert not verify_signature(b"hellO", sig, keys["public"])
    _, other_pub = generate_keypair()
    assert not verify_signature(data, sig, other_pub)
    assert not verify_signature(data, b"not base64!!", keys["public"])


def test_bad_keys():
    with pytest.raises(ManifestError):
        load_signing_key("@@@")
    with pytest.raises(ManifestError):
        load_signing_key(base64.b64encode(b"short").decode())


def test_manifest_roundtrip_and_one_line_entries(tmp_path):
    a = tmp_path / "a.tar.gz"
    a.write_bytes(b"aaa")
    b = tmp_path / "b.zip"
    b.write_bytes(b"bbbb")
    m = build_manifest("x", "1.0", "v1.0", [a, b], [{"name": "gh", "type": "github"}])
    data = m.to_bytes()
    m2 = Manifest.from_bytes(data)
    assert m2.version == "1.0" and m2.file("b.zip").size == 4
    assert m2.to_bytes() == data
    # install.sh relies on each entry being on one line
    line = next(ln for ln in data.decode().splitlines() if '"a.tar.gz"' in ln)
    assert '{"name": "a.tar.gz", "sha256": "' in line and '"size": 3' in line


def test_duplicate_names_rejected(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    (tmp_path / "x" / "f").write_text("1")
    (tmp_path / "y" / "f").write_text("2")
    with pytest.raises(ManifestError):
        build_manifest("n", "1", "v1", [tmp_path / "x" / "f", tmp_path / "y" / "f"], [])


def test_verify_files(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"data")
    m = build_manifest("n", "1", "v1", [f], [])
    assert verify_files(m, tmp_path) == []
    f.write_bytes(b"DATA")
    assert verify_files(m, tmp_path) == ["sha256 mismatch: f.bin"]
    f.unlink()
    assert verify_files(m, tmp_path) == ["missing: f.bin"]


def test_bad_schema():
    with pytest.raises(ManifestError):
        Manifest.from_bytes(b'{"schema": "other"}')
    with pytest.raises(ManifestError):
        Manifest.from_bytes(b"not json")


def test_openssl_can_verify_our_signature(tmp_path, keys):
    """The generated install.sh verifies with openssl; prove the formats line up."""
    data = b'{"hello": "world"}\n'
    (tmp_path / "m.json").write_bytes(data)
    (tmp_path / "sig.bin").write_bytes(base64.b64decode(sign_bytes(data, keys["private"])))
    (tmp_path / "pub.pem").write_text(public_key_pem(keys["public"]))
    r = subprocess.run(
        ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", "pub.pem", "-rawin", "-in", "m.json", "-sigfile", "sig.bin"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
