"""Publishing a bundle to S3-compatible, GitHub and Gitea targets with mocked HTTP: bundle contents, source order, key checks, dry run, partial failures and token redaction."""
import subprocess

import boto3
import httpx
import pytest
import respx
from moto import mock_aws

from conftest import ARVAN_ENDPOINT, GITEA_URL, LIARA_ENDPOINT
from dokhaneh.config import ConfigError
from dokhaneh.manifest import Manifest, verify_signature
from dokhaneh.publisher import ordered_sources, prepare, publish
from dokhaneh.targets import make_targets

GH_API = "https://api.github.com/repos/acme/myapp"
GH_UP = "https://uploads.github.com/repos/acme/myapp/releases/1/assets"
GT_API = f"{GITEA_URL}/api/v1/repos/acme/myapp"


def _s3(endpoint):
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id="x", aws_secret_access_key="y", region_name="us-east-1"
    )


def _mock_forges(router: respx.MockRouter, uploads: dict):
    router.get(f"{GH_API}/releases/tags/v1.2.0").respond(404, json={"message": "Not Found"})
    router.post(f"{GH_API}/releases").respond(
        201, json={"id": 1, "html_url": "https://github.com/acme/myapp/releases/tag/v1.2.0", "assets": []}
    )

    def gh_upload(request):
        assert request.headers["authorization"] == "Bearer gh-test-token"
        uploads.setdefault("github", []).append(request.url.params["name"])
        return httpx.Response(201, json={"id": 99})

    router.post(GH_UP).mock(side_effect=gh_upload)

    router.get(f"{GT_API}/releases/tags/v1.2.0").respond(200, json={"id": 7, "assets": [{"id": 3, "name": "manifest.json"}]})
    router.delete(f"{GT_API}/releases/7/assets/3").respond(204)

    def gt_upload(request):
        assert request.headers["authorization"] == "token gitea-test-token"
        uploads.setdefault("gitea", []).append(request.url.params["name"])
        return httpx.Response(201, json={"id": 5})

    router.post(f"{GT_API}/releases/7/assets").mock(side_effect=gt_upload)


def test_prepare_bundle(config):
    prep = prepare(config)
    names = [f.name for f in prep.bundle.files]
    assert names == [
        "myapp-1.2.0-linux-amd64.tar.gz",
        "myapp-1.2.0.zip",
        "myapp-1.2.0-docs.tar.gz",
        "install.sh",
    ]
    data = prep.bundle.manifest.read_bytes()
    assert verify_signature(data, prep.bundle.signature.read_bytes(), config.public_key)
    m = Manifest.from_bytes(data)
    assert [x["name"] for x in m.mirrors] == ["github", "arvan", "liara", "gitea"]
    script = (prep.out_dir / "install.sh").read_text()
    assert "https://github.com/acme/myapp/releases/download/v1.2.0" in script


def test_sources_global_first(config):
    sources = ordered_sources(make_targets(config), "1.2.0", "v1.2.0")
    assert sources == [
        "https://github.com/acme/myapp/releases/download/v1.2.0",
        "https://myapp-releases.s3.ir-thr-at1.arvanstorage.ir/releases/1.2.0",
        "https://myapp.storage.c2.liara.site/pub/releases/1.2.0",
        f"{GITEA_URL}/acme/myapp/releases/download/v1.2.0",
    ]


def test_wrong_signing_key_rejected(config, monkeypatch):
    from dokhaneh.manifest import generate_keypair

    monkeypatch.setenv("DOKHANEH_SIGNING_KEY", generate_keypair()[0])
    with pytest.raises(ConfigError, match="does not match"):
        prepare(config)


def test_missing_signing_key(config, monkeypatch):
    monkeypatch.delenv("DOKHANEH_SIGNING_KEY")
    with pytest.raises(ConfigError, match="no signing key"):
        prepare(config)


def test_dry_run_uploads_nothing(config):
    with respx.mock(assert_all_called=False) as router:
        results = publish(prepare(config), dry_run=True)
        assert router.calls.call_count == 0
    assert all(r.ok and r.skipped for r in results)
    arvan = next(r for r in results if r.target == "arvan")
    assert "releases/1.2.0/manifest.json" in arvan.uploaded
    assert "docs/guide/index.html" in arvan.uploaded
    assert "install.sh" in arvan.uploaded


@mock_aws
def test_publish_all_targets(project, config):
    _s3(ARVAN_ENDPOINT).create_bucket(Bucket="myapp-releases")
    _s3(LIARA_ENDPOINT).create_bucket(Bucket="myapp")
    uploads: dict = {}
    with respx.mock(assert_all_called=True) as router:
        _mock_forges(router, uploads)
        prep = prepare(config)
        results = publish(prep)
    failed = [r for r in results if not r.ok]
    assert not failed, failed

    expected = {f.name for f in prep.bundle.release_files}
    assert set(uploads["github"]) == expected
    assert set(uploads["gitea"]) == expected

    keys = {o["Key"] for o in _s3(ARVAN_ENDPOINT).list_objects_v2(Bucket="myapp-releases")["Contents"]}
    assert {f"releases/1.2.0/{n}" for n in expected} <= keys
    assert {"install.sh", "docs/index.html", "docs/guide/index.html", "releases/latest/manifest.json"} <= keys
    obj = _s3(ARVAN_ENDPOINT).get_object(Bucket="myapp-releases", Key="releases/1.2.0/manifest.json")
    assert obj["ContentType"] == "application/json"
    assert obj["Body"].read() == prep.bundle.manifest.read_bytes()

    lkeys = {o["Key"] for o in _s3(LIARA_ENDPOINT).list_objects_v2(Bucket="myapp")["Contents"]}
    assert "pub/releases/1.2.0/manifest.json.sig" in lkeys

    # gitea mirror: branch + tag pushed to the bare repo
    refs = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname)"], cwd=project["bare"], capture_output=True, text=True
    ).stdout.split()
    assert "refs/heads/main" in refs and "refs/tags/v1.2.0" in refs


@mock_aws
def test_one_failing_target_does_not_stop_others(config):
    # arvan bucket deliberately missing; liara fine
    _s3(LIARA_ENDPOINT).create_bucket(Bucket="myapp")
    uploads: dict = {}
    with respx.mock(assert_all_called=False) as router:
        _mock_forges(router, uploads)
        results = {r.target: r for r in publish(prepare(config))}
    assert not results["arvan"].ok and "NoSuchBucket" in results["arvan"].error
    assert results["liara"].ok and results["github"].ok and results["gitea"].ok


def test_github_error_is_reported(config):
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{GH_API}/releases/tags/v1.2.0").respond(401, json={"message": "Bad credentials"})
        prep = prepare(config, only=["github"])
        [res] = publish(prep)
    assert not res.ok and "401" in res.error


def test_gitea_token_is_redacted(config, monkeypatch):
    t = config.target("gitea")
    t.options.pop("push_url")
    t.options["url"] = "http://127.0.0.1:9"  # nothing listens here
    t.options["release"] = False
    prep = prepare(config, only=["gitea"])
    [res] = publish(prep)
    assert not res.ok
    assert "gitea-test-token" not in (res.error or "")
