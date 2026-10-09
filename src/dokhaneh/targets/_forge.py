"""Shared release logic for GitHub-like forges (GitHub, Gitea/Forgejo)."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import httpx


class ForgeError(RuntimeError):
    pass


def _raise(r: httpx.Response, what: str) -> None:
    if r.status_code >= 400:
        detail = r.text[:300].replace("\n", " ")
        raise ForgeError(f"{what} failed: HTTP {r.status_code} {detail}")


def content_type(path: Path) -> str:
    if path.name.endswith(".sig") or path.suffix == ".sh":
        return "text/plain"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class ForgeReleaseClient:
    """Minimal client for GitHub-style ``/releases`` endpoints."""

    def __init__(self, client: httpx.Client, api: str, repo: str, flavor: str):
        self.client = client
        self.api = api.rstrip("/")
        self.repo = repo
        self.flavor = flavor  # "github" | "gitea"

    def get_or_create(self, tag: str, name: str, body: str) -> dict[str, Any]:
        r = self.client.get(f"{self.api}/repos/{self.repo}/releases/tags/{tag}")
        if r.status_code == 200:
            return r.json()
        if r.status_code != 404:
            _raise(r, "looking up release")
        payload = {"tag_name": tag, "name": name, "body": body, "draft": False, "prerelease": False}
        r = self.client.post(f"{self.api}/repos/{self.repo}/releases", json=payload)
        _raise(r, "creating release")
        return r.json()

    def list_assets(self, release: dict[str, Any]) -> list[dict[str, Any]]:
        if release.get("assets") is not None:
            return list(release["assets"])
        r = self.client.get(f"{self.api}/repos/{self.repo}/releases/{release['id']}/assets")
        _raise(r, "listing assets")
        return r.json()

    def delete_asset(self, release: dict[str, Any], asset: dict[str, Any]) -> None:
        if self.flavor == "github":
            url = f"{self.api}/repos/{self.repo}/releases/assets/{asset['id']}"
        else:
            url = f"{self.api}/repos/{self.repo}/releases/{release['id']}/assets/{asset['id']}"
        r = self.client.delete(url)
        if r.status_code != 404:
            _raise(r, f"deleting old asset {asset.get('name')}")

    def upload_asset(self, release: dict[str, Any], path: Path, upload_base: str | None = None) -> None:
        if self.flavor == "github":
            base = (upload_base or "https://uploads.github.com").rstrip("/")
            url = f"{base}/repos/{self.repo}/releases/{release['id']}/assets"
            r = self.client.post(
                url,
                params={"name": path.name},
                content=path.read_bytes(),
                headers={"Content-Type": content_type(path)},
            )
        else:
            url = f"{self.api}/repos/{self.repo}/releases/{release['id']}/assets"
            with open(path, "rb") as fh:
                r = self.client.post(
                    url, params={"name": path.name}, files={"attachment": (path.name, fh, content_type(path))}
                )
        _raise(r, f"uploading {path.name}")

    def sync_assets(self, release: dict[str, Any], files: list[Path], upload_base: str | None = None) -> list[str]:
        existing = {a["name"]: a for a in self.list_assets(release)}
        uploaded = []
        for f in files:
            if f.name in existing:
                self.delete_asset(release, existing[f.name])
            self.upload_asset(release, f, upload_base)
            uploaded.append(f.name)
        return uploaded
