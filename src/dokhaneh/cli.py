"""Command-line interface: ``dokhaneh``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer

from . import __version__
from .config import SAMPLE_CONFIG, ConfigError, load_config
from .manifest import (
    Manifest,
    ManifestError,
    generate_keypair,
    verify_files,
    verify_signature,
)
from .publisher import ordered_sources, prepare, publish
from .targets import make_targets
from .verify import check_consistency, check_mirror

app = typer.Typer(
    name="dokhaneh",
    help="Dokhaneh (دوخانه): publish releases to GitHub and domestic mirrors at once, signed.",
    no_args_is_help=True,
    add_completion=False,
)

ConfigOpt = typer.Option(None, "--config", "-c", help="Path to dokhaneh.yml")
VersionOpt = typer.Option(None, "--version", "-v", help="Release version (default: config / git tag)")


def _fail(msg: str, code: int = 1) -> None:
    typer.secho(f"✗ {msg}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _ok(msg: str) -> None:
    typer.secho(f"✓ {msg}", fg=typer.colors.GREEN)


def _gh_output(**values: str) -> None:
    """Expose values as GitHub Actions step outputs when running in Actions."""
    import os

    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for k, v in values.items():
            fh.write(f"{k}={v}\n")


@app.command("version")
def version_cmd() -> None:
    """Print the dokhaneh version."""
    typer.echo(__version__)


@app.command()
def init(
    path: Path = typer.Argument(Path("dokhaneh.yml"), help="Where to write the sample config"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Write a commented sample dokhaneh.yml."""
    if path.exists() and not force:
        _fail(f"{path} already exists (use --force)")
    path.write_text(SAMPLE_CONFIG, encoding="utf-8")
    _ok(f"wrote {path}; next: `dokhaneh keygen`")


@app.command()
def keygen(
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Also write the private key to this file (0600)"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Generate an Ed25519 signing keypair."""
    priv, pub = generate_keypair()
    if out:
        out.write_text(priv + "\n", encoding="utf-8")
        out.chmod(0o600)
    if as_json:
        typer.echo(json.dumps({"private_key": priv, "public_key": pub}))
        return
    typer.echo(f"public_key:  {pub}")
    typer.echo(f"private_key: {priv}")
    typer.echo("")
    typer.echo("• Put public_key under signing.public_key in dokhaneh.yml (it is safe to publish).")
    typer.echo("• Store private_key as the secret DOKHANEH_SIGNING_KEY. Never commit it.")


@app.command()
def sign(
    config: Optional[Path] = ConfigOpt,
    version: Optional[str] = VersionOpt,
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output dir (default .dokhaneh/<version>)"),
) -> None:
    """Build install.sh + the signed manifest without uploading anything."""
    try:
        cfg = load_config(config, version)
        prep = prepare(cfg, out)
    except (ConfigError, ManifestError) as e:
        _fail(str(e))
    for f in prep.bundle.release_files:
        typer.echo(f"  {f.name}")
    _ok(f"signed manifest for {cfg.name} {cfg.version} in {prep.out_dir}")


@app.command("install-script")
def install_script(
    config: Optional[Path] = ConfigOpt,
    version: Optional[str] = VersionOpt,
    out: Path = typer.Option(Path("install.sh"), "--out", "-o"),
) -> None:
    """Generate only install.sh (global source first, domestic fallbacks)."""
    from .installer import render_install_script

    try:
        cfg = load_config(config, version)
        if not cfg.install_asset or not cfg.public_key:
            raise ConfigError("install.asset and signing.public_key are required")
        targets = make_targets(cfg)
        script = render_install_script(
            cfg.name,
            cfg.version,
            cfg.install_asset,
            ordered_sources(targets, cfg.version, cfg.tag),
            cfg.public_key,
            cfg.install_binary,
        )
    except (ConfigError, ManifestError, ValueError) as e:
        _fail(str(e))
    out.write_text(script, encoding="utf-8")
    out.chmod(0o755)
    _ok(f"wrote {out}")


@app.command("publish")
def publish_cmd(
    config: Optional[Path] = ConfigOpt,
    version: Optional[str] = VersionOpt,
    only: Optional[list[str]] = typer.Option(None, "--only", help="Publish to these targets only (repeatable)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Sign and plan, but upload nothing"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Working dir for generated files"),
) -> None:
    """Sign and publish artifacts + docs to every target."""
    try:
        cfg = load_config(config, version)
        prep = prepare(cfg, out, only=only)
    except (ConfigError, ManifestError) as e:
        _fail(str(e))
    typer.echo(
        f"Publishing {cfg.name} {cfg.version} ({cfg.tag}) to {len(prep.targets)} target(s)"
        + (" [dry run]" if dry_run else "")
    )
    results = publish(prep, dry_run=dry_run)
    failed = 0
    for r in results:
        if r.ok:
            label = "planned" if r.skipped else "published"
            _ok(f"{r.target}: {label} {len(r.uploaded)} item(s)" + (f" → {r.url}" if r.url else ""))
            if dry_run:
                for item in r.uploaded:
                    typer.echo(f"      {item}")
        else:
            failed += 1
            typer.secho(f"✗ {r.target}: {r.error}", fg=typer.colors.RED, err=True)
    _gh_output(
        version=cfg.version,
        manifest=str(prep.bundle.manifest),
        succeeded=str(len(results) - failed),
        failed=str(failed),
    )
    if failed:
        _fail(f"{failed} of {len(results)} target(s) failed", code=2)


@app.command()
def verify(
    config: Optional[Path] = ConfigOpt,
    version: Optional[str] = VersionOpt,
    manifest: Optional[Path] = typer.Option(None, "--manifest", "-m", help="Local manifest.json to check"),
    directory: Optional[Path] = typer.Option(None, "--dir", "-d", help="Check local files against the manifest"),
    public_key: Optional[str] = typer.Option(None, "--public-key", "-k", help="Base64 Ed25519 public key"),
    deep: bool = typer.Option(False, "--deep", help="Remote mode: download and hash every file"),
    timeout: float = typer.Option(20.0, "--timeout"),
) -> None:
    """Verify signatures and that every mirror serves identical, untampered files.

    Local mode (--manifest): check signature [+ files in --dir].
    Remote mode (default): fetch the manifest from every target and compare.
    """
    if manifest:
        if not public_key:
            try:
                public_key = load_config(config, version, require_version=False).public_key
            except ConfigError:
                public_key = None
        if not public_key:
            _fail("a public key is required (--public-key or signing.public_key)")
        data = manifest.read_bytes()
        sig_path = manifest.with_name(manifest.name + ".sig")
        if not sig_path.is_file():
            _fail(f"signature not found: {sig_path}")
        if not verify_signature(data, sig_path.read_bytes(), public_key):
            _fail("BAD SIGNATURE")
        m = Manifest.from_bytes(data)
        _ok(f"signature valid: {m.name} {m.version} ({len(m.files)} files)")
        if directory:
            problems = verify_files(m, directory)
            for p in problems:
                typer.secho(f"  ✗ {p}", fg=typer.colors.RED, err=True)
            if problems:
                _fail(f"{len(problems)} file problem(s)")
            _ok(f"all {len(m.files)} files in {directory} match")
        return

    try:
        cfg = load_config(config, version)
    except ConfigError as e:
        _fail(str(e))
    key = public_key or cfg.public_key
    if not key:
        _fail("signing.public_key is not set")
    checks = []
    with httpx.Client(timeout=timeout, headers={"User-Agent": f"dokhaneh/{__version__}"}) as client:
        for t in make_targets(cfg):
            c = check_mirror(client, t, cfg.version, cfg.tag, key, deep=deep)
            checks.append(c)
            if c.ok:
                _ok(f"{c.target}: {c.url}" + (f"  [{c.problems[0]}]" if c.problems else ""))
            else:
                typer.secho(f"✗ {c.target}: {c.url}", fg=typer.colors.RED, err=True)
                for p in c.problems:
                    typer.secho(f"    {p}", fg=typer.colors.RED, err=True)
    problems = check_consistency(checks)
    for p in problems:
        typer.secho(f"✗ {p}", fg=typer.colors.RED, err=True)
    if problems or not all(c.ok for c in checks):
        _fail("verification failed", code=2)
    _ok(f"all mirrors serve the same signed manifest for {cfg.name} {cfg.version}")


@app.command()
def status(
    config: Optional[Path] = ConfigOpt,
    version: Optional[str] = VersionOpt,
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
    timeout: float = typer.Option(10.0, "--timeout"),
) -> None:
    """Check reachability of every target from where you are right now."""
    try:
        cfg = load_config(config, version, require_version=False)
        targets = make_targets(cfg)
    except ConfigError as e:
        _fail(str(e))
    with httpx.Client(timeout=timeout, headers={"User-Agent": f"dokhaneh/{__version__}"}) as client:
        results = [t.check(client) for t in targets]
    if as_json:
        typer.echo(json.dumps([r.__dict__ for r in results], indent=2, ensure_ascii=False))
    else:
        w = max(len(r.target) for r in results)
        for r in results:
            if r.found:
                mark = typer.style("UP     ", fg=typer.colors.GREEN)
            elif r.reachable:
                mark = typer.style("MISSING", fg=typer.colors.YELLOW)
            else:
                mark = typer.style("DOWN   ", fg=typer.colors.RED)
            code = r.status_code if r.status_code is not None else "---"
            ms = f"{r.latency_ms}ms" if r.latency_ms is not None else ""
            typer.echo(f"{mark} {r.target:<{w}}  {r.region:<8} {code!s:>4} {ms:>7}  {r.url}")
            if r.error:
                typer.echo(f"     {r.error}")
    up = sum(r.reachable for r in results)
    if not as_json:
        found = sum(r.found for r in results)
        what = "release found" if cfg.version else "OK"
        typer.echo(f"{up}/{len(results)} targets reachable, {found}/{len(results)} {what}")
    if up == 0:
        raise typer.Exit(2)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
