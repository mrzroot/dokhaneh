"""Verify signed manifests locally and across all mirrors."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import httpx

from .manifest import MANIFEST_NAME, SIGNATURE_NAME, Manifest, ManifestError, verify_signature
from .targets import Target


@dataclass
class MirrorCheck:
    target: str
    url: str
    ok: bool
    manifest_sha256: str | None = None
    problems: list[str] = field(default_factory=list)


def check_mirror(
    client: httpx.Client, target: Target, version: str, tag: str, public_key: str, deep: bool = False
) -> MirrorCheck:
    base = target.release_base_url(version, tag)
    if not base:
        return MirrorCheck(target.name, "-", True, problems=["no release downloads on this target (skipped)"])
    chk = MirrorCheck(target.name, base, False)
    try:
        m = client.get(f"{base}/{MANIFEST_NAME}", follow_redirects=True)
        s = client.get(f"{base}/{SIGNATURE_NAME}", follow_redirects=True)
    except httpx.HTTPError as e:
        chk.problems.append(f"unreachable: {type(e).__name__}: {e}")
        return chk
    if m.status_code != 200 or s.status_code != 200:
        chk.problems.append(f"manifest HTTP {m.status_code}, signature HTTP {s.status_code}")
        return chk
    chk.manifest_sha256 = hashlib.sha256(m.content).hexdigest()
    if not verify_signature(m.content, s.content, public_key):
        chk.problems.append("BAD SIGNATURE")
        return chk
    try:
        manifest = Manifest.from_bytes(m.content)
    except ManifestError as e:
        chk.problems.append(str(e))
        return chk
    if manifest.version != version:
        chk.problems.append(f"manifest is for version {manifest.version}, expected {version}")
        return chk
    if deep:
        for f in manifest.files:
            try:
                r = client.get(f"{base}/{f.name}", follow_redirects=True)
            except httpx.HTTPError as e:
                chk.problems.append(f"{f.name}: unreachable ({type(e).__name__})")
                continue
            if r.status_code != 200:
                chk.problems.append(f"{f.name}: HTTP {r.status_code}")
            elif hashlib.sha256(r.content).hexdigest() != f.sha256:
                chk.problems.append(f"{f.name}: sha256 mismatch")
    chk.ok = not chk.problems
    return chk


def check_consistency(checks: list[MirrorCheck]) -> list[str]:
    """All reachable mirrors must serve byte-identical manifests."""
    digests = {c.manifest_sha256 for c in checks if c.manifest_sha256 and c.ok}
    if len(digests) > 1:
        return ["mirrors serve DIFFERENT signed manifests (re-publish to sync them)"]
    return []
