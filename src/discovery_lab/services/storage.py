from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from discovery_lab.services.hashing import sha256_bytes


class BlobStore(Protocol):
    def put(self, content: bytes, *, content_hash: str) -> str: ...

    def get(self, uri: str) -> bytes: ...


class LocalBlobStore:
    """Content-addressed local storage; the returned URI contains no user filename."""

    _URI_PREFIX = "blob://sha256/"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put(self, content: bytes, *, content_hash: str) -> str:
        actual_hash = sha256_bytes(content)
        if actual_hash != content_hash:
            raise ValueError("content_hash does not match the supplied bytes")

        destination = self._path_for_hash(content_hash)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256_bytes(destination.read_bytes()) != content_hash:
                raise OSError("existing content-addressed blob failed its integrity check")
        else:
            temporary = destination.with_suffix(f".{os.getpid()}.{uuid4().hex}.tmp")
            try:
                temporary.write_bytes(content)
                with suppress(FileExistsError):
                    os.link(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
            if sha256_bytes(destination.read_bytes()) != content_hash:
                raise OSError("concurrent content-addressed blob failed its integrity check")
        return f"{self._URI_PREFIX}{content_hash}"

    def get(self, uri: str) -> bytes:
        if not uri.startswith(self._URI_PREFIX):
            raise ValueError("unsupported blob URI")
        content_hash = uri.removeprefix(self._URI_PREFIX)
        path = self._path_for_hash(content_hash)
        content = path.read_bytes()
        if sha256_bytes(content) != content_hash:
            raise OSError("stored blob failed its integrity check")
        return content

    def _path_for_hash(self, content_hash: str) -> Path:
        if len(content_hash) != 64 or any(c not in "0123456789abcdef" for c in content_hash):
            raise ValueError("invalid SHA-256 content hash")
        # ``content_hash`` is restricted to lowercase hex above, so this join
        # cannot traverse outside the configured root. Avoid resolving a path
        # while another thread is creating it; Windows may transiently report
        # different canonical parents during that race.
        return self.root / content_hash[:2] / content_hash
