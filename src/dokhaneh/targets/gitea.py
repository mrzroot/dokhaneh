"""Gitea / Forgejo target: git mirror push + release assets."""

from __future__ import annotations

import subprocess
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from ..config import ConfigError
from ._forge import ForgeError, ForgeReleaseClient
from .base import PublishResult, ReleaseBundle, Target


def _redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret else text


class GiteaTarget(Target):
    type = "gitea"

    @property
    def url(self) -> str:
        return str(self.cfg.require("url")).rstrip("/")

    @property
    def repo(self) -> str:
        return str(self.cfg.require("repo"))

    def validate(self) -> None:
        self.cfg.require("url")
        if "/" not in self.repo:
            raise ConfigError(f"target '{self.name}': repo must look like owner/name")

    def release_base_url(self, version: str, tag: str) -> str | None:
        if not version or not self.cfg.get("release", True):
            return None
        return f"{self.url}/{self.repo}/releases/download/{tag}"

    def root_url(self) -> str:
        return f"{self.url}/api/v1/version"

    def push_url(self, token: str | None) -> str:
        if self.cfg.get("push_url"):
            return str(self.cfg.get("push_url"))
        parts = urlsplit(f"{self.url}/{self.repo}.git")
        netloc = parts.netloc
        if token:
            user = quote(str(self.cfg.get("username", "oauth2")), safe="")
            netloc = f"{user}:{quote(token, safe='')}@{netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))

    # -- git mirror ----------------------------------------------------
    def _git(self, args: list[str], token: str | None) -> None:
        cwd = self.cfg.get("repo_dir") or str(self.project.base_dir)
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if proc.returncode != 0:
            msg = _redact((proc.stderr or proc.stdout).strip(), token)
            raise ForgeError(f"git {_redact(' '.join(args[:1]), token)} failed: {msg}")

    def mirror(self, bundle: ReleaseBundle, token: str | None) -> list[str]:
        url = self.push_url(token)
        branch = str(self.cfg.get("branch", "main"))
        pushed = []
        force = ["--force"] if self.cfg.get("force", True) else []
        self._git(["push", *force, url, f"HEAD:refs/heads/{branch}"], token)
        pushed.append(f"branch:{branch}")
        self._git(["push", *force, url, "--tags"], token)
        pushed.append("tags")
        return pushed

    def publish(self, bundle: ReleaseBundle, dry_run: bool = False) -> PublishResult:
        self.validate()
        do_mirror = bool(self.cfg.get("mirror", True))
        do_release = bool(self.cfg.get("release", True))
        planned = (["git-mirror"] if do_mirror else []) + ([f.name for f in bundle.release_files] if do_release else [])
        url = f"{self.url}/{self.repo}/releases/tag/{bundle.tag}"
        if dry_run:
            return PublishResult(self.name, True, planned, url, skipped=True)
        token = self.cfg.secret("token", default_env="GITEA_TOKEN")
        uploaded: list[str] = []
        try:
            if do_mirror:
                uploaded += self.mirror(bundle, token)
            if do_release:
                if not token:
                    raise ForgeError("no Gitea token (set token_env / GITEA_TOKEN)")
                headers = {"Authorization": f"token {token}", "User-Agent": "dokhaneh"}
                with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0), headers=headers) as client:
                    forge = ForgeReleaseClient(client, f"{self.url}/api/v1", self.repo, "gitea")
                    rel = forge.get_or_create(bundle.tag, f"{self.project.name} {bundle.version}", bundle.notes)
                    uploaded += forge.sync_assets(rel, bundle.release_files)
            return PublishResult(self.name, True, uploaded, url)
        except (ForgeError, httpx.HTTPError) as e:
            return PublishResult(self.name, False, uploaded, error=_redact(str(e), token))
