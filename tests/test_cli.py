"""dokhaneh CLI: init/keygen, sign and verify, publish --dry-run, install-script output, verify against a local mirror server and status exit codes."""
import json

import httpx
import respx
from typer.testing import CliRunner

from dokhaneh.cli import app
from dokhaneh.publisher import prepare

runner = CliRunner()


def test_version_and_help():
    assert runner.invoke(app, ["version"]).exit_code == 0
    assert "publish" in runner.invoke(app, ["--help"]).output


def test_init_and_keygen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0 and (tmp_path / "dokhaneh.yml").exists()
    assert runner.invoke(app, ["init"]).exit_code == 1  # no overwrite
    r = runner.invoke(app, ["keygen", "--json", "--out", "k.key"])
    keys = json.loads(r.output)
    assert (tmp_path / "k.key").read_text().strip() == keys["private_key"]
    assert oct((tmp_path / "k.key").stat().st_mode)[-3:] == "600"


def test_sign_then_verify_local(project):
    r = runner.invoke(app, ["sign"])
    assert r.exit_code == 0, r.output
    out = project["root"] / ".dokhaneh" / "1.2.0"
    # all files listed in the manifest live in dist/ or the bundle dir; copy artifacts in
    for f in (project["root"] / "dist").iterdir():
        (out / f.name).write_bytes(f.read_bytes())
    r = runner.invoke(app, ["verify", "--manifest", str(out / "manifest.json"), "--dir", str(out)])
    assert r.exit_code == 0, r.output
    assert "signature valid" in r.output

    (out / "myapp-1.2.0.zip").write_bytes(b"X" * 22)  # same size, different bytes
    r = runner.invoke(app, ["verify", "--manifest", str(out / "manifest.json"), "--dir", str(out)])
    assert r.exit_code == 1
    assert "sha256 mismatch: myapp-1.2.0.zip" in r.output


def test_publish_dry_run(project, tmp_path, monkeypatch):
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    r = runner.invoke(app, ["publish", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "arvan: planned" in r.output and "releases/1.2.0/install.sh" in r.output
    assert "failed=0" in gh_out.read_text()


def test_publish_unknown_only(project):
    r = runner.invoke(app, ["publish", "--only", "nope", "--dry-run"])
    assert r.exit_code == 1


def test_install_script_cmd(project):
    r = runner.invoke(app, ["install-script", "-o", "inst.sh"])
    assert r.exit_code == 0, r.output
    assert "arvanstorage.ir" in (project["root"] / "inst.sh").read_text()


def _serve(router, base, files):
    for name, data in files.items():
        router.get(f"{base}/{name}").respond(200, content=data)
    router.get(url__startswith=base + "/").respond(404)


def _bundle_files(prep):
    return {f.name: f.read_bytes() for f in prep.bundle.release_files}


def test_verify_remote(config, project):
    prep = prepare(config)
    files = _bundle_files(prep)
    bases = {
        "github": "https://github.com/acme/myapp/releases/download/v1.2.0",
        "arvan": "https://myapp-releases.s3.ir-thr-at1.arvanstorage.ir/releases/1.2.0",
        "liara": "https://myapp.storage.c2.liara.site/pub/releases/1.2.0",
        "gitea": "https://git.example.ir/acme/myapp/releases/download/v1.2.0",
    }
    with respx.mock(assert_all_called=False) as router:
        for b in bases.values():
            _serve(router, b, files)
        r = runner.invoke(app, ["verify", "--deep"])
    assert r.exit_code == 0, r.output
    assert "all mirrors serve the same signed manifest" in r.output

    tampered = dict(files)
    tampered["myapp-1.2.0.zip"] = b"evil"
    with respx.mock(assert_all_called=False) as router:
        for name, b in bases.items():
            _serve(router, b, tampered if name == "liara" else files)
        r = runner.invoke(app, ["verify", "--deep"])
    assert r.exit_code == 2
    assert "liara" in r.output and "sha256 mismatch" in r.output


def test_status(project):
    with respx.mock() as router:
        router.head(url__startswith="https://github.com/").respond(200)
        router.head(url__startswith="https://myapp-releases.s3").respond(404)
        router.head(url__startswith="https://myapp.storage").mock(side_effect=httpx.ConnectTimeout("t/o"))
        router.head(url__startswith="https://git.example.ir/").respond(405)
        router.get(url__startswith="https://git.example.ir/").respond(206)
        r = runner.invoke(app, ["status", "--json"])
    assert r.exit_code == 0, r.output
    data = {x["target"]: x for x in json.loads(r.output)}
    assert data["github"]["reachable"] and data["github"]["region"] == "global"
    assert data["github"]["found"]
    assert data["arvan"]["reachable"] and not data["arvan"]["found"]  # host up, release missing
    assert data["arvan"]["region"] == "domestic"
    assert not data["liara"]["reachable"] and "ConnectTimeout" in data["liara"]["error"]
    assert data["gitea"]["reachable"] and data["gitea"]["status_code"] == 206


def test_status_all_down_exit_code(project):
    with respx.mock() as router:
        router.route().mock(side_effect=httpx.ConnectError("no route"))
        r = runner.invoke(app, ["status"])
    assert r.exit_code == 2
    assert "0/4 targets reachable, 0/4 release found" in r.output
