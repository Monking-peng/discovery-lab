"""Content-addressed immutable blob storage port and local adapter."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import Field

from .hashing import sha256_bytes
from .models import StrictFrozenModel

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BlobStoreError(RuntimeError):
    pass


class BlobNotFoundError(BlobStoreError):
    pass


class BlobIntegrityError(BlobStoreError):
    pass


class BlobRef(StrictFrozenModel):
    algorithm: str = "sha256"
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: str | None = None

    @property
    def uri(self) -> str:
        return f"blob://sha256/{self.digest}"


@runtime_checkable
class BlobStore(Protocol):
    """A deliberately small port; mutation and overwrite are not capabilities."""

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str | None = None,
        expected_sha256: str | None = None,
    ) -> BlobRef: ...

    def read_bytes(self, ref: BlobRef) -> bytes: ...

    def contains(self, digest: str) -> bool: ...


class LocalBlobStore:
    """Store immutable blobs by digest below a caller-owned local directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for_digest(self, digest: str) -> Path:
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError("digest must be a lowercase SHA-256 hex string")
        return self.root / "sha256" / digest[:2] / digest[2:4] / f"{digest}.blob"

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str | None = None,
        expected_sha256: str | None = None,
    ) -> BlobRef:
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        digest = sha256_bytes(content)
        if expected_sha256 is not None and expected_sha256 != digest:
            raise BlobIntegrityError("content digest does not match expected_sha256")

        target = self._path_for_digest(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = target.read_bytes()
            if sha256_bytes(existing) != digest:
                raise BlobIntegrityError(f"existing blob is corrupt: {digest}") from None
            if existing != content:
                raise BlobIntegrityError(f"digest collision detected: {digest}") from None
        else:
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
            except BaseException:
                # An interrupted exclusive write must not masquerade as a valid blob.
                target.unlink(missing_ok=True)
                raise

        return BlobRef(digest=digest, size_bytes=len(content), media_type=media_type)

    def read_bytes(self, ref: BlobRef) -> bytes:
        target = self._path_for_digest(ref.digest)
        try:
            content = target.read_bytes()
        except FileNotFoundError as exc:
            raise BlobNotFoundError(ref.uri) from exc
        if len(content) != ref.size_bytes or sha256_bytes(content) != ref.digest:
            raise BlobIntegrityError(f"blob failed integrity verification: {ref.uri}")
        return content

    def contains(self, digest: str) -> bool:
        return self._path_for_digest(digest).is_file()
