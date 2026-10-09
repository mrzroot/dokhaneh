"""Run the generated POSIX install.sh against file:// mirrors."""

import os
import shutil
import subprocess

import pytest

from dokhaneh.publisher import prepare

pytestmark = pytest.mark.skipif(
    not (shutil.which("sh") and shutil.which("openssl") and shutil.which("curl")),
    reason="needs sh, openssl and curl",
)


def _mirror(prep, dest):
    dest.mkdir(parents=True)
    for f in prep.bundle.release_files:
        shutil.copy(f, dest / f.name)
    return dest


def _run(prep, sources, tmp_path):
    env = {
        **os.environ,
        "DOKHANEH_SOURCES": " ".join(sources),
        "DOKHANEH_INSTALL_DIR": str(tmp_path / "bin"),
        "DOKHANEH_TIMEOUT": "2",
    }
    return subprocess.run(["sh", str(prep.out_dir / "install.sh")], env=env, capture_output=True, text=True, timeout=60)


def test_falls_back_to_domestic_mirror(config, tmp_path):
    prep = prepare(config)
    good = _mirror(prep, tmp_path / "arvan")
    r = _run(prep, [f"file://{tmp_path}/github-blocked", f"file://{good}"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "unreachable" in r.stderr
    out = subprocess.run([str(tmp_path / "bin" / "myapp")], capture_output=True, text=True).stdout
    assert out.strip() == "hello from myapp"


def test_tampered_mirror_is_skipped(config, tmp_path):
    prep = prepare(config)
    evil = _mirror(prep, tmp_path / "evil")
    (evil / "myapp-1.2.0-linux-amd64.tar.gz").write_bytes(b"malware")
    good = _mirror(prep, tmp_path / "good")
    r = _run(prep, [f"file://{evil}", f"file://{good}"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "SHA-256 MISMATCH" in r.stderr


def test_forged_manifest_is_rejected(config, tmp_path):
    prep = prepare(config)
    evil = _mirror(prep, tmp_path / "evil")
    m = evil / "manifest.json"
    m.write_text(m.read_text().replace('"size": ', '"size":  '))
    r = _run(prep, [f"file://{evil}"], tmp_path)
    assert r.returncode != 0
    assert "BAD SIGNATURE" in r.stderr
    assert not (tmp_path / "bin" / "myapp").exists()


def test_all_mirrors_down(config, tmp_path):
    prep = prepare(config)
    r = _run(prep, [f"file://{tmp_path}/a", f"file://{tmp_path}/b"], tmp_path)
    assert r.returncode != 0
    assert "no mirror delivered" in r.stderr


def test_download_only_mode(config, tmp_path):
    config.install_binary = None
    prep = prepare(config)
    good = _mirror(prep, tmp_path / "m")
    env_out = tmp_path / "out"
    env = {**os.environ, "DOKHANEH_SOURCES": f"file://{good}", "DOKHANEH_OUT_DIR": str(env_out)}
    r = subprocess.run(["sh", str(prep.out_dir / "install.sh")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (env_out / "myapp-1.2.0-linux-amd64.tar.gz").is_file()
