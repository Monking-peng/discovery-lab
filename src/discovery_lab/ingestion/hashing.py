"""Deterministic hashing helpers used by provenance-sensitive ingestion code."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 hex digest for *value*."""

    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash text exactly as UTF-8 without hidden normalization."""

    return sha256_bytes(value.encode("utf-8"))


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible data in a stable, UTF-8 representation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def stable_id(namespace: str, *parts: str, length: int = 24) -> str:
    """Build a readable deterministic identifier from an ordered set of parts."""

    payload: Mapping[str, str | Sequence[str]] = {
        "namespace": namespace,
        "parts": parts,
    }
    digest = sha256_bytes(canonical_json_bytes(payload))
    return f"{namespace}_{digest[:length]}"
