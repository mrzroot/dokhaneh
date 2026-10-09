from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml

from dokhaneh.config import load_config
from dokhaneh.manifest import generate_keypair

ARVAN_ENDPOINT = "https://s3.ir-thr-at1.arvanstorage.ir"
LIARA_ENDPOINT = "https://storage.c2.liara.site"
GITEA_URL = "https://git.example.ir"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def keys():
    priv, pub = generate_keypair()
    return {"private": priv, "public": pub}


@pytest.fixture
def project(tmp_path: Path, keys, monkeypatch):
    """A tiny project: git repo + dist artifact + docs + dokhaneh.yml."""
    root = tmp_path / "proj"
    (root / "dist").mkdir(parents=True)
    (root / "site").mkdir()
    (root / "site" / "index.html").write_text("<h1>docs</h1>")
    (root / "site" / "guide").mkdir()
    (root / "site" / "guide" / "index.html").write_text("<p>guide</p>")

    # artifact: tar.gz containing an executable "myapp"
    payload = b"#!/bin/sh\necho hello from myapp\n"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("myapp-1.2.0/myapp")
        info.size = len(payload)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(payload))
    (root / "dist" / "myapp-1.2.0-linux-amd64.tar.gz").write_bytes(buf.getvalue())
    (root / "dist" / "myapp-1.2.0.zip").write_bytes(b"PK\x05\x06" + b"\0" * 18)

    # git repo + bare "gitea" remote
    bare = tmp_path / "gitea-remote.git"
    _git(tmp_path, "init", "--bare", "-q", str(bare))
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "README").write_text("hi")
    _git(root, "add", "README")
    _git(root, "commit", "-q", "-m", "init")
    _git(root, "tag", "v1.2.0")

    cfg = {
        "project": {"name": "myapp", "version": "1.2.0", "release_notes": "notes"},
        "artifacts": ["dist/*.tar.gz", "dist/*.zip"],
        "docs": "site/",
        "signing": {"public_key": keys["public"]},
        "install": {"asset": "myapp-{version}-linux-amd64.tar.gz", "binary": "myapp"},
        "targets": [
            {"name": "github", "type": "github", "repo": "acme/myapp"},
            {
                "name": "arvan",
                "type": "arvan",
                "bucket": "myapp-releases",
                "access_key_env": "ARVAN_ACCESS_KEY",
                "secret_key_env": "ARVAN_SECRET_KEY",
            },
            {
                "name": "liara",
                "type": "liara",
                "bucket": "myapp",
                "prefix": "pub",
                "access_key_env": "LIARA_ACCESS_KEY",
                "secret_key_env": "LIARA_SECRET_KEY",
            },
            {
                "name": "gitea",
                "type": "gitea",
                "url": GITEA_URL,
                "repo": "acme/myapp",
                "push_url": str(bare),
            },
        ],
    }
    (root / "dokhaneh.yml").write_text(yaml.safe_dump(cfg, allow_unicode=True))

    for k, v in {
        "DOKHANEH_SIGNING_KEY": keys["private"],
        "GITHUB_TOKEN": "gh-test-token",
        "GITEA_TOKEN": "gitea-test-token",
        "ARVAN_ACCESS_KEY": "ak",
        "ARVAN_SECRET_KEY": "sk",
        "LIARA_ACCESS_KEY": "lk",
        "LIARA_SECRET_KEY": "ls",
        "AWS_DEFAULT_REGION": "us-east-1",
        "MOTO_S3_CUSTOM_ENDPOINTS": f"{ARVAN_ENDPOINT},{LIARA_ENDPOINT}",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.chdir(root)
    return {"root": root, "bare": bare, "config_path": root / "dokhaneh.yml"}


@pytest.fixture
def config(project):
    return load_config(project["config_path"])
