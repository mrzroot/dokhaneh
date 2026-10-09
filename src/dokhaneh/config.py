"""Loading and validating ``dokhaneh.yml``."""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_NAMES = ("dokhaneh.yml", "dokhaneh.yaml", ".dokhaneh.yml")
KNOWN_TARGET_TYPES = ("github", "s3", "arvan", "liara", "gitea")

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigError(ValueError):
    """Raised when the configuration is missing or invalid."""


def expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` / ``${VAR:-default}`` in strings."""
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    return value


@dataclass
class TargetConfig:
    name: str
    type: str
    options: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.options.get(key, default)

    def require(self, key: str) -> Any:
        val = self.options.get(key)
        if val in (None, ""):
            raise ConfigError(f"target '{self.name}' ({self.type}) requires '{key}'")
        return val

    def secret(self, key: str, default_env: str | None = None) -> str | None:
        """Resolve a secret: ``<key>`` literal, else env var named by ``<key>_env``."""
        if self.options.get(key):
            return str(self.options[key])
        env_name = self.options.get(f"{key}_env", default_env)
        if env_name:
            return os.environ.get(env_name) or None
        return None


@dataclass
class Config:
    name: str
    version: str
    tag: str
    description: str
    artifacts: list[str]
    docs: str | None
    signing_private_key_env: str
    public_key: str | None
    install_asset: str | None
    install_binary: str | None
    targets: list[TargetConfig]
    base_dir: Path
    release_notes: str = ""

    def resolve_artifacts(self) -> list[Path]:
        files: list[Path] = []
        for pattern in self.artifacts:
            matches = sorted(glob.glob(str(self.base_dir / pattern), recursive=True))
            files.extend(Path(m) for m in matches if Path(m).is_file())
        # de-duplicate, keep order
        seen: set[Path] = set()
        unique = []
        for f in files:
            if f.resolve() not in seen:
                seen.add(f.resolve())
                unique.append(f)
        return unique

    def docs_dir(self) -> Path | None:
        if not self.docs:
            return None
        p = self.base_dir / self.docs
        return p if p.is_dir() else None

    def target(self, name: str) -> TargetConfig:
        for t in self.targets:
            if t.name == name:
                return t
        raise ConfigError(f"no target named '{name}'")


def _resolve_version(raw: dict[str, Any], override: str | None, required: bool = True) -> str:
    if override:
        return override.lstrip("v") if override.startswith("v") and override[1:2].isdigit() else override
    project = raw.get("project", {}) or {}
    if project.get("version"):
        return str(project["version"])
    ref = os.environ.get("GITHUB_REF_NAME") or os.environ.get("DOKHANEH_VERSION")
    if ref:
        return ref[1:] if ref.startswith("v") and ref[1:2].isdigit() else ref
    if not required:
        return ""
    raise ConfigError("project version unknown: set project.version, pass --version, or run on a tag")


def find_config(path: str | Path | None = None) -> Path:
    if path:
        p = Path(path)
        if not p.is_file():
            raise ConfigError(f"config file not found: {p}")
        return p
    for name in DEFAULT_CONFIG_NAMES:
        if Path(name).is_file():
            return Path(name)
    raise ConfigError("no dokhaneh.yml found (run `dokhaneh init`)")


def parse_config(raw: dict[str, Any], base_dir: Path, version: str | None = None, require_version: bool = True) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")
    raw = expand_env(raw)
    project = raw.get("project") or {}
    name = project.get("name")
    if not name:
        raise ConfigError("project.name is required")
    ver = _resolve_version(raw, version, require_version)
    tag_tpl = project.get("tag", "v{version}")
    signing = raw.get("signing") or {}
    install = raw.get("install") or {}
    artifacts = raw.get("artifacts") or []
    if isinstance(artifacts, str):
        artifacts = [artifacts]

    targets: list[TargetConfig] = []
    seen: set[str] = set()
    for i, t in enumerate(raw.get("targets") or []):
        if not isinstance(t, dict) or "type" not in t:
            raise ConfigError(f"targets[{i}] must be a mapping with a 'type'")
        ttype = str(t["type"]).lower()
        if ttype not in KNOWN_TARGET_TYPES:
            raise ConfigError(f"targets[{i}]: unknown type '{ttype}' (known: {', '.join(KNOWN_TARGET_TYPES)})")
        tname = str(t.get("name") or ttype)
        if tname in seen:
            raise ConfigError(f"duplicate target name '{tname}'")
        seen.add(tname)
        opts = {k: v for k, v in t.items() if k not in ("name", "type")}
        targets.append(TargetConfig(name=tname, type=ttype, options=opts))
    if not targets:
        raise ConfigError("at least one target is required")

    fmt = {"name": name, "version": ver}
    asset = install.get("asset")
    return Config(
        name=name,
        version=ver,
        tag=tag_tpl.format(**fmt),
        description=project.get("description", ""),
        artifacts=[a.format(**fmt) for a in artifacts],
        docs=raw.get("docs"),
        signing_private_key_env=signing.get("private_key_env", "DOKHANEH_SIGNING_KEY"),
        public_key=signing.get("public_key"),
        install_asset=asset.format(**fmt) if asset else None,
        install_binary=install.get("binary"),
        targets=targets,
        base_dir=base_dir,
        release_notes=project.get("release_notes", ""),
    )


def load_config(path: str | Path | None = None, version: str | None = None, require_version: bool = True) -> Config:
    p = find_config(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {p}: {e}") from e
    return parse_config(raw, p.resolve().parent, version, require_version)


SAMPLE_CONFIG = """\
# dokhaneh.yml — publish every release to GitHub *and* domestic mirrors.
# Secrets are never written here: reference environment variables with *_env keys.
project:
  name: myapp
  # version: "1.2.0"        # optional; defaults to the git tag (GITHUB_REF_NAME) or --version
  tag: "v{version}"
  description: "My application"

artifacts:                  # globs, relative to this file
  - "dist/*.tar.gz"
  - "dist/*.zip"

docs: site/                 # optional static docs folder (e.g. mkdocs build output)

signing:
  private_key_env: DOKHANEH_SIGNING_KEY   # base64 Ed25519 seed (from `dokhaneh keygen`)
  public_key: "PASTE_PUBLIC_KEY_HERE"

install:                    # used by the generated install.sh
  asset: "myapp-{version}-linux-amd64.tar.gz"
  binary: myapp             # optional: extract this binary into $DOKHANEH_INSTALL_DIR

targets:                    # order matters: global first, then domestic fallbacks
  - name: github
    type: github
    repo: myorg/myapp
    token_env: GITHUB_TOKEN

  - name: arvan
    type: arvan                                   # S3-compatible ArvanCloud Object Storage
    endpoint: https://s3.ir-thr-at1.arvanstorage.ir
    bucket: myapp-releases
    public_url: https://myapp-releases.s3.ir-thr-at1.arvanstorage.ir
    access_key_env: ARVAN_ACCESS_KEY
    secret_key_env: ARVAN_SECRET_KEY

  - name: liara
    type: liara                                   # Liara Object Storage (S3-compatible)
    endpoint: https://storage.c2.liara.site
    bucket: myapp
    public_url: https://myapp.storage.c2.liara.site
    access_key_env: LIARA_ACCESS_KEY
    secret_key_env: LIARA_SECRET_KEY

  - name: gitea
    type: gitea                                   # self-hosted / domestic Gitea or Forgejo
    url: https://git.example.ir
    repo: myorg/myapp
    token_env: GITEA_TOKEN
    mirror: true                                  # git push branch + tags
    branch: main
"""
