"""GitHub Releases target."""

from __future__ import annotations

import httpx

from ..config import ConfigError
from ._forge import ForgeError, ForgeReleaseClient
from .base import PublishResult, ReleaseBundle, Target


class GitHubTarget(Target):
    type = "github"
    default_region = "global"

    @property
    def repo(self) -> str:
        return str(self.cfg.require("repo"))

    @property
    def api(self) -> str:
        return str(self.cfg.get("api_url", "https://api.github.com")).rstrip("/")

    @property
    def web(self) -> str:
        return str(self.cfg.get("web_url", "https://github.com")).rstrip("/")

    def validate(self) -> None:
        self.cfg.require("repo")
        if "/" not in self.repo:
            raise ConfigError(f"target '{self.name}': repo must look like owner/name")

    def release_base_url(self, version: str, tag: str) -> str | None:
        if not version:
            return None
        return f"{self.web}/{self.repo}/releases/download/{tag}"

    def root_url(self) -> str:
        return f"{self.web}/{self.repo}"

    def _client(self, token: str) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(60.0, connect=15.0),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "dokhaneh",
            },
        )

    def publish(self, bundle: ReleaseBundle, dry_run: bool = False) -> PublishResult:
        self.validate()
        files = bundle.release_files
        url = f"{self.web}/{self.repo}/releases/tag/{bundle.tag}"
        if dry_run:
            return PublishResult(self.name, True, [f.name for f in files], url, skipped=True)
        token = self.cfg.secret("token", default_env="GITHUB_TOKEN")
        if not token:
            return PublishResult(self.name, False, error="no GitHub token (set token_env / GITHUB_TOKEN)")
        try:
            with self._client(token) as client:
                forge = ForgeReleaseClient(client, self.api, self.repo, "github")
                rel = forge.get_or_create(bundle.tag, f"{self.project.name} {bundle.version}", bundle.notes)
                uploaded = forge.sync_assets(rel, files, self.cfg.get("uploads_url"))
                return PublishResult(self.name, True, uploaded, rel.get("html_url", url))
        except (ForgeError, httpx.HTTPError) as e:
            return PublishResult(self.name, False, error=str(e))
