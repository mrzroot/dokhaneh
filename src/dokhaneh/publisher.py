"""Build a signed release bundle and push it to every target."""

from __future__ import annotations

import os
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path

from .config import Config, ConfigError
from .installer import render_install_script
from .manifest import (
    MANIFEST_NAME,
    SIGNATURE_NAME,
    build_manifest,
    load_signing_key,
    sign_bytes,
)
from .targets import PublishResult, ReleaseBundle, Target, make_targets


@dataclass
class Prepared:
    bundle: ReleaseBundle
    targets: list[Target]
    out_dir: Path


def ordered_sources(targets: list[Target], version: str, tag: str) -> list[str]:
    """Global sources first, then domestic, preserving config order inside each group."""
    glob_ = [t for t in targets if t.region == "global"]
    dom = [t for t in targets if t.region != "global"]
    urls = []
    for t in [*glob_, *dom]:
        u = t.release_base_url(version, tag)
        if u and u not in urls:
            urls.append(u)
    return urls


def _make_docs_archive(docs: Path, dest: Path) -> Path:
    with tarfile.open(dest, "w:gz") as tar:
        for p in sorted(docs.rglob("*")):
            tar.add(p, arcname=p.relative_to(docs).as_posix(), recursive=False)
    return dest


def resolve_signing_key(config: Config, key: str | None = None) -> str:
    key = key or os.environ.get(config.signing_private_key_env)
    if not key:
        raise ConfigError(f"no signing key: set ${config.signing_private_key_env} (create one with `dokhaneh keygen`)")
    sk = load_signing_key(key)
    if config.public_key:
        import base64

        pub = base64.b64encode(bytes(sk.verify_key)).decode()
        if pub != config.public_key.strip():
            raise ConfigError("signing key does not match signing.public_key in dokhaneh.yml")
    return key


def prepare(
    config: Config,
    out_dir: Path | None = None,
    only: list[str] | None = None,
    signing_key: str | None = None,
) -> Prepared:
    key = resolve_signing_key(config, signing_key)
    all_targets = make_targets(config)
    for t in all_targets:
        t.validate()
    targets = [t for t in all_targets if not only or t.name in only]
    if only and len(targets) != len(set(only)):
        raise ConfigError(f"unknown target(s) in --only: {', '.join(only)}")

    artifacts = config.resolve_artifacts()
    if not artifacts:
        raise ConfigError(f"no artifacts matched {config.artifacts}")

    out = (out_dir or config.base_dir / ".dokhaneh" / config.version).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    files: list[Path] = list(artifacts)
    docs = config.docs_dir()
    if config.docs and docs is None:
        raise ConfigError(f"docs directory not found: {config.docs}")
    if docs:
        files.append(_make_docs_archive(docs, out / f"{config.name}-{config.version}-docs.tar.gz"))

    # The installer embeds the *full* mirror list (not just --only), so it is
    # identical everywhere and can be listed (and signed) in the manifest.
    if config.install_asset:
        if not config.public_key:
            raise ConfigError("install.asset is set but signing.public_key is missing")
        if config.install_asset not in {f.name for f in files}:
            raise ConfigError(f"install.asset '{config.install_asset}' is not one of the artifacts")
        script = render_install_script(
            config.name,
            config.version,
            config.install_asset,
            ordered_sources(all_targets, config.version, config.tag),
            config.public_key,
            config.install_binary,
        )
        sh = out / "install.sh"
        sh.write_text(script, encoding="utf-8")
        sh.chmod(0o755)
        files.append(sh)

    manifest = build_manifest(config.name, config.version, config.tag, files, [t.mirror_info() for t in all_targets])
    data = manifest.to_bytes()
    (out / MANIFEST_NAME).write_bytes(data)
    (out / SIGNATURE_NAME).write_bytes(sign_bytes(data, key))

    bundle = ReleaseBundle(
        version=config.version,
        tag=config.tag,
        files=files,
        manifest=out / MANIFEST_NAME,
        signature=out / SIGNATURE_NAME,
        docs_dir=docs,
        notes=config.release_notes,
    )
    return Prepared(bundle, targets, out)


def publish(prepared: Prepared, dry_run: bool = False) -> list[PublishResult]:
    results = []
    for t in prepared.targets:
        try:
            results.append(t.publish(prepared.bundle, dry_run=dry_run))
        except Exception as e:  # noqa: BLE001 — one broken mirror must not stop the others
            results.append(PublishResult(t.name, False, error=f"{type(e).__name__}: {e}"))
    return results
