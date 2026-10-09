"""Ed25519-signed release manifests.

The manifest is a JSON document listing every published file with its SHA-256
and size. Its exact bytes are signed with Ed25519; the detached signature is
stored next to it as base64 in ``manifest.json.sig``. Because every mirror
serves the very same signed bytes, a client can prove that any mirror carries
exactly what the maintainer released.

Each file entry is serialised on a single line so that the POSIX ``install.sh``
can extract a hash with ``grep``/``sed`` without needing a JSON parser.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from . import __version__

MANIFEST_NAME = "manifest.json"
SIGNATURE_NAME = "manifest.json.sig"
SCHEMA = "dokhaneh/manifest/v1"

# DER prefix for an Ed25519 SubjectPublicKeyInfo (RFC 8410)
_ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


class ManifestError(ValueError):
    pass


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------- keys
def generate_keypair() -> tuple[str, str]:
    """Return ``(private_seed_b64, public_key_b64)``."""
    sk = SigningKey.generate()
    return (
        base64.b64encode(bytes(sk)).decode(),
        base64.b64encode(bytes(sk.verify_key)).decode(),
    )


def load_signing_key(b64: str) -> SigningKey:
    try:
        raw = base64.b64decode(b64.strip(), validate=True)
    except Exception as e:  # noqa: BLE001
        raise ManifestError("signing key is not valid base64") from e
    if len(raw) == 64:  # libsodium-style seed||pubkey
        raw = raw[:32]
    if len(raw) != 32:
        raise ManifestError("signing key must be a 32-byte Ed25519 seed (base64)")
    return SigningKey(raw)


def load_verify_key(b64: str) -> VerifyKey:
    try:
        raw = base64.b64decode(b64.strip(), validate=True)
    except Exception as e:  # noqa: BLE001
        raise ManifestError("public key is not valid base64") from e
    if len(raw) != 32:
        raise ManifestError("public key must be 32 bytes (base64)")
    return VerifyKey(raw)


def public_key_pem(public_b64: str) -> str:
    """PEM (SPKI) form of the public key, usable by ``openssl pkeyutl``."""
    raw = bytes(load_verify_key(public_b64))
    body = base64.b64encode(_ED25519_SPKI_PREFIX + raw).decode()
    return f"-----BEGIN PUBLIC KEY-----\n{body}\n-----END PUBLIC KEY-----\n"


# ---------------------------------------------------------------- manifest
@dataclass
class FileEntry:
    name: str
    sha256: str
    size: int


@dataclass
class Manifest:
    name: str
    version: str
    tag: str
    created: str
    files: list[FileEntry]
    mirrors: list[dict[str, str]]
    generator: str = f"dokhaneh/{__version__}"
    schema: str = SCHEMA

    # -- serialisation -------------------------------------------------
    def to_bytes(self) -> bytes:
        head = {
            "schema": self.schema,
            "name": self.name,
            "version": self.version,
            "tag": self.tag,
            "created": self.created,
            "generator": self.generator,
        }
        lines = ["{"]
        for k, v in head.items():
            lines.append(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
        lines.append('  "files": [')
        for i, f in enumerate(self.files):
            entry = json.dumps({"name": f.name, "sha256": f.sha256, "size": f.size}, ensure_ascii=False)
            lines.append(f"    {entry}{',' if i < len(self.files) - 1 else ''}")
        lines.append("  ],")
        lines.append('  "mirrors": [')
        for i, m in enumerate(self.mirrors):
            entry = json.dumps(m, ensure_ascii=False, sort_keys=True)
            lines.append(f"    {entry}{',' if i < len(self.mirrors) - 1 else ''}")
        lines.append("  ]")
        lines.append("}")
        return ("\n".join(lines) + "\n").encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> Manifest:
        try:
            obj: dict[str, Any] = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ManifestError(f"manifest is not valid JSON: {e}") from e
        if obj.get("schema") != SCHEMA:
            raise ManifestError(f"unsupported manifest schema: {obj.get('schema')!r}")
        return cls(
            name=obj["name"],
            version=obj["version"],
            tag=obj.get("tag", ""),
            created=obj.get("created", ""),
            files=[FileEntry(**f) for f in obj.get("files", [])],
            mirrors=list(obj.get("mirrors", [])),
            generator=obj.get("generator", ""),
            schema=obj["schema"],
        )

    def file(self, name: str) -> FileEntry | None:
        return next((f for f in self.files if f.name == name), None)


def build_manifest(name: str, version: str, tag: str, files: list[Path], mirrors: list[dict[str, str]]) -> Manifest:
    names = [f.name for f in files]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ManifestError(f"duplicate artifact file names: {', '.join(sorted(dupes))}")
    entries = [FileEntry(f.name, sha256_file(f), f.stat().st_size) for f in files]
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return Manifest(name=name, version=version, tag=tag, created=created, files=entries, mirrors=mirrors)


def sign_bytes(data: bytes, signing_key_b64: str) -> bytes:
    """Return the base64-encoded detached signature (as bytes, newline-terminated)."""
    sig = load_signing_key(signing_key_b64).sign(data).signature
    return base64.b64encode(sig) + b"\n"


def verify_signature(data: bytes, signature_b64: bytes | str, public_key_b64: str) -> bool:
    if isinstance(signature_b64, bytes):
        signature_b64 = signature_b64.decode("ascii", "replace")
    try:
        sig = base64.b64decode(signature_b64.strip(), validate=True)
    except Exception:  # noqa: BLE001
        return False
    try:
        load_verify_key(public_key_b64).verify(data, sig)
        return True
    except (BadSignatureError, ValueError):
        return False


def verify_files(manifest: Manifest, directory: Path) -> list[str]:
    """Check local files against the manifest; return a list of problems."""
    problems = []
    for f in manifest.files:
        p = directory / f.name
        if not p.is_file():
            problems.append(f"missing: {f.name}")
            continue
        if p.stat().st_size != f.size:
            problems.append(f"size mismatch: {f.name}")
            continue
        if sha256_file(p) != f.sha256:
            problems.append(f"sha256 mismatch: {f.name}")
    return problems
