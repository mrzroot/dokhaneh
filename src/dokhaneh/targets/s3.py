"""S3-compatible object storage targets (generic S3, ArvanCloud, Liara)."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from ..config import ConfigError
from ..manifest import MANIFEST_NAME, SIGNATURE_NAME
from .base import PublishResult, ReleaseBundle, Target


def _content_type(path: Path) -> str:
    if path.name == MANIFEST_NAME:
        return "application/json"
    if path.name == SIGNATURE_NAME or path.suffix == ".sh":
        return "text/plain; charset=utf-8"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class S3Target(Target):
    """Any S3-compatible bucket.

    Layout inside the bucket (``prefix`` is optional)::

        <prefix>/releases/<version>/<files, manifest.json, manifest.json.sig, install.sh>
        <prefix>/releases/latest/...    (same files, overwritten each release)
        <prefix>/install.sh             (latest installer)
        <prefix>/docs/...               (static docs site)
    """

    type = "s3"
    default_endpoint: str | None = None
    default_public_url_tpl: str | None = None  # e.g. "https://{bucket}.example"
    default_region_name: str = "us-east-1"

    @property
    def bucket(self) -> str:
        return str(self.cfg.require("bucket"))

    @property
    def endpoint(self) -> str | None:
        return self.cfg.get("endpoint", self.default_endpoint)

    @property
    def prefix(self) -> str:
        return str(self.cfg.get("prefix", "")).strip("/")

    @property
    def public_url(self) -> str:
        url = self.cfg.get("public_url")
        if not url and self.default_public_url_tpl:
            url = self.default_public_url_tpl.format(bucket=self.bucket)
        if not url and self.endpoint:
            url = f"{self.endpoint.rstrip('/')}/{self.bucket}"
        if not url:
            raise ConfigError(f"target '{self.name}' needs 'public_url'")
        return str(url).rstrip("/")

    def _key(self, *parts: str) -> str:
        return "/".join(p for p in (self.prefix, *parts) if p)

    def _public(self, key: str) -> str:
        return f"{self.public_url}/{key}"

    def validate(self) -> None:
        self.cfg.require("bucket")
        _ = self.public_url

    def release_base_url(self, version: str, tag: str) -> str | None:
        if not version:
            return None
        return self._public(self._key("releases", version))

    def docs_url(self) -> str | None:
        return self._public(self._key("docs")) + "/"

    def root_url(self) -> str:
        return self._public(self._key("install.sh"))

    def client(self):
        import boto3
        from botocore.config import Config as BotoConfig

        access = self.cfg.secret("access_key")
        secret = self.cfg.secret("secret_key")
        if not access or not secret:
            raise ConfigError(f"target '{self.name}': missing access_key/secret_key (use *_env options)")
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            region_name=str(self.cfg.get("region_name", self.default_region_name)),
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": str(self.cfg.get("addressing_style", "path"))},
                retries={"max_attempts": 5, "mode": "standard"},
            ),
        )

    def plan(self, bundle: ReleaseBundle) -> list[tuple[Path, str]]:
        uploads: list[tuple[Path, str]] = []
        for f in bundle.release_files:
            uploads.append((f, self._key("releases", bundle.version, f.name)))
        if self.cfg.get("latest", True):
            for f in bundle.release_files:
                uploads.append((f, self._key("releases", "latest", f.name)))
            for f in bundle.files:
                if f.name == "install.sh":
                    uploads.append((f, self._key("install.sh")))
        if bundle.docs_dir and self.cfg.get("docs", True):
            for p in sorted(bundle.docs_dir.rglob("*")):
                if p.is_file():
                    rel = p.relative_to(bundle.docs_dir).as_posix()
                    uploads.append((p, self._key("docs", rel)))
        return uploads

    def publish(self, bundle: ReleaseBundle, dry_run: bool = False) -> PublishResult:
        try:
            self.validate()
        except ConfigError as e:
            return PublishResult(self.name, False, error=str(e))
        uploads = self.plan(bundle)
        url = self.release_base_url(bundle.version, bundle.tag)
        if dry_run:
            return PublishResult(self.name, True, [k for _, k in uploads], url, skipped=True)
        acl = self.cfg.get("acl", "public-read")
        done: list[str] = []
        try:
            s3 = self.client()
            for path, key in uploads:
                extra = {"ContentType": _content_type(path)}
                if acl:
                    extra["ACL"] = acl
                if path.name in (MANIFEST_NAME, SIGNATURE_NAME, "install.sh") or "/latest/" in key:
                    extra["CacheControl"] = "no-cache"
                s3.upload_file(str(path), self.bucket, key, ExtraArgs=extra)
                done.append(key)
            return PublishResult(self.name, True, done, url)
        except Exception as e:  # noqa: BLE001 — boto raises many types
            return PublishResult(self.name, False, done, error=f"{type(e).__name__}: {e}")


class ArvanTarget(S3Target):
    """ArvanCloud Object Storage (S3-compatible, hosted inside Iran)."""

    type = "arvan"
    default_endpoint = "https://s3.ir-thr-at1.arvanstorage.ir"
    default_public_url_tpl = "https://{bucket}.s3.ir-thr-at1.arvanstorage.ir"
    default_region_name = "ir-thr-at1"


class LiaraTarget(S3Target):
    """Liara Object Storage (S3-compatible, hosted inside Iran).

    Copy the exact endpoint from your Liara panel; the default below is the
    commonly documented one and may differ per region.
    """

    type = "liara"
    default_endpoint = "https://storage.c2.liara.site"
    default_public_url_tpl = "https://{bucket}.storage.c2.liara.site"
    default_region_name = "us-east-1"
