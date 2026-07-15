from __future__ import annotations

import pytest

from discovery_lab.ingestion import BlobIntegrityError, LocalBlobStore


def test_local_blob_store_is_content_addressed_and_idempotent(tmp_path) -> None:
    store = LocalBlobStore(tmp_path)
    first = store.put_bytes(b"immutable source", media_type="text/plain")
    second = store.put_bytes(b"immutable source", media_type="text/plain")

    assert first == second
    assert first.uri == f"blob://sha256/{first.digest}"
    assert store.contains(first.digest)
    assert store.read_bytes(first) == b"immutable source"


def test_local_blob_store_rejects_expected_hash_mismatch(tmp_path) -> None:
    store = LocalBlobStore(tmp_path)
    with pytest.raises(BlobIntegrityError):
        store.put_bytes(b"actual", expected_sha256="0" * 64)


def test_local_blob_store_detects_existing_corruption(tmp_path) -> None:
    store = LocalBlobStore(tmp_path)
    ref = store.put_bytes(b"trusted")
    target = store._path_for_digest(ref.digest)
    target.write_bytes(b"corrupt")

    with pytest.raises(BlobIntegrityError):
        store.read_bytes(ref)
    with pytest.raises(BlobIntegrityError):
        store.put_bytes(b"trusted")
