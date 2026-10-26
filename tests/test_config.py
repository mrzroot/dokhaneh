"""Config loading: defaults, environment-variable expansion, version taken from the git tag, required fields."""
import pytest

from dokhaneh.config import ConfigError, load_config, parse_config


def base(**over):
    raw = {"project": {"name": "p", "version": "1.0"}, "targets": [{"type": "github", "repo": "a/b"}]}
    raw.update(over)
    return raw


def test_defaults(tmp_path):
    c = parse_config(base(), tmp_path)
    assert c.tag == "v1.0"
    assert c.targets[0].name == "github"
    assert c.signing_private_key_env == "DOKHANEH_SIGNING_KEY"


def test_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("BUCKET", "bkt")
    raw = base(targets=[{"type": "arvan", "bucket": "${BUCKET}", "prefix": "${NOPE:-dflt}"}])
    c = parse_config(raw, tmp_path)
    assert c.targets[0].get("bucket") == "bkt"
    assert c.targets[0].get("prefix") == "dflt"


def test_version_from_tag(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REF_NAME", "v2.3.4")
    raw = base()
    del raw["project"]["version"]
    assert parse_config(raw, tmp_path).version == "2.3.4"
    assert parse_config(raw, tmp_path, version="v9.0").version == "9.0"


def test_version_required(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    monkeypatch.delenv("DOKHANEH_VERSION", raising=False)
    raw = base()
    del raw["project"]["version"]
    with pytest.raises(ConfigError):
        parse_config(raw, tmp_path)
    assert parse_config(raw, tmp_path, require_version=False).version == ""


@pytest.mark.parametrize(
    "raw",
    [
        {"targets": [{"type": "github"}]},
        base(targets=[]),
        base(targets=[{"type": "ftp"}]),
        base(targets=[{"type": "github", "repo": "a/b"}, {"type": "github", "repo": "c/d"}]),
        base(targets=["nope"]),
    ],
)
def test_invalid(tmp_path, raw):
    with pytest.raises(ConfigError):
        parse_config(raw, tmp_path)


def test_load_and_artifacts(project, config):
    names = [p.name for p in config.resolve_artifacts()]
    assert names == ["myapp-1.2.0-linux-amd64.tar.gz", "myapp-1.2.0.zip"]
    assert config.install_asset == "myapp-1.2.0-linux-amd64.tar.gz"
    assert config.docs_dir().name == "site"


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yml")
