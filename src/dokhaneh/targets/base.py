"""Common target interface."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ..config import Config, TargetConfig
from ..manifest import MANIFEST_NAME


@dataclass
class ReleaseBundle:
    """Everything a target needs to publish one release."""

    version: str
    tag: str
    files: list[Path]  # artifacts + install.sh (+ docs archive): all listed in the manifest
    manifest: Path
    signature: Path
    docs_dir: Path | None = None
    notes: str = ""

    @property
    def release_files(self) -> list[Path]:
        return [*self.files, self.manifest, self.signature]


@dataclass
class PublishResult:
    target: str
    ok: bool
    uploaded: list[str] = field(default_factory=list)
    url: str | None = None
    error: str | None = None
    skipped: bool = False


@dataclass
class StatusResult:
    target: str
    type: str
    region: str
    url: str
    reachable: bool  # host answered (any HTTP status < 500)
    status_code: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    found: bool = False  # the probed file exists (HTTP < 400)


class Target:
    """Base class. Subclasses implement :meth:`publish` and :meth:`release_base_url`."""

    type: str = "base"
    default_region: str = "domestic"

    def __init__(self, cfg: TargetConfig, project: Config):
        self.cfg = cfg
        self.project = project
        self.name = cfg.name

    @property
    def region(self) -> str:
        return str(self.cfg.get("region", self.default_region))

    # -- URLs ----------------------------------------------------------
    def release_base_url(self, version: str, tag: str) -> str | None:
        """Public HTTP(S) base where ``<file>`` of this release can be downloaded."""
        raise NotImplementedError

    def docs_url(self) -> str | None:
        return None

    def status_url(self) -> str:
        """URL probed by ``dokhaneh status``."""
        v = self.project.version
        if v:
            base = self.release_base_url(v, self.project.tag)
            if base:
                return f"{base}/{MANIFEST_NAME}"
        return self.root_url()

    def root_url(self) -> str:
        raise NotImplementedError

    def mirror_info(self) -> dict[str, str]:
        info = {"name": self.name, "type": self.type, "region": self.region}
        base = self.release_base_url(self.project.version, self.project.tag)
        if base:
            info["url"] = base
        return info

    # -- actions -------------------------------------------------------
    def validate(self) -> None:
        """Raise ConfigError if required options are missing."""

    def publish(self, bundle: ReleaseBundle, dry_run: bool = False) -> PublishResult:
        raise NotImplementedError

    def check(self, client: httpx.Client) -> StatusResult:
        url = self.status_url()
        start = time.monotonic()
        try:
            r = client.head(url, follow_redirects=True)
            if r.status_code in (403, 405, 501):  # some hosts reject HEAD
                r = client.get(url, follow_redirects=True, headers={"Range": "bytes=0-0"})
            ms = int((time.monotonic() - start) * 1000)
            return StatusResult(
                self.name,
                self.type,
                self.region,
                url,
                reachable=r.status_code < 500,
                status_code=r.status_code,
                latency_ms=ms,
                found=r.status_code < 400,
            )
        except httpx.HTTPError as e:
            ms = int((time.monotonic() - start) * 1000)
            return StatusResult(self.name, self.type, self.region, url, False, None, ms, f"{type(e).__name__}: {e}")
