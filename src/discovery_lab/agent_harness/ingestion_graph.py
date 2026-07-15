"""Small-state LangGraph orchestration for parse -> extract -> verify."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypedDict, runtime_checkable

from discovery_lab.ingestion.blob_store import BlobRef, BlobStore
from discovery_lab.ingestion.extractors import EvidenceExtractor
from discovery_lab.ingestion.hashing import canonical_json_bytes, sha256_bytes
from discovery_lab.ingestion.models import ExtractionResult, Segment, VerificationResult
from discovery_lab.ingestion.parsers import parse_source
from discovery_lab.ingestion.verification import CitationVerifier


class IngestionState(TypedDict, total=False):
    """Checkpoint-safe state: identifiers and small metadata, never source bodies."""

    run_id: str
    source_revision_id: str
    blob_ref: dict[str, Any]
    filename: str | None
    media_type: str | None
    segments_ref: str
    extraction_ref: str
    verification_ref: str
    stage: str


@runtime_checkable
class IngestionArtifactPort(Protocol):
    def load_blob(self, ref: BlobRef) -> bytes: ...

    def save_segments(self, run_id: str, segments: tuple[Segment, ...]) -> str: ...

    def load_segments(self, ref: str) -> tuple[Segment, ...]: ...

    def save_extraction(self, run_id: str, result: ExtractionResult) -> str: ...

    def load_extraction(self, ref: str) -> ExtractionResult: ...

    def save_verification(self, run_id: str, result: VerificationResult) -> str: ...

    def load_verification(self, ref: str) -> VerificationResult: ...


class InMemoryIngestionArtifacts:
    """Test/demo port. Production must replace it with transactional repositories."""

    def __init__(self, blob_store: BlobStore) -> None:
        self._blob_store = blob_store
        self._objects: dict[str, Any] = {}

    def load_blob(self, ref: BlobRef) -> bytes:
        return self._blob_store.read_bytes(ref)

    def _save(self, kind: str, run_id: str, value: Any, payload: Any) -> str:
        digest = sha256_bytes(canonical_json_bytes(payload))
        ref = f"memory://{kind}/{run_id}/{digest}"
        self._objects.setdefault(ref, value)
        return ref

    def save_segments(self, run_id: str, segments: tuple[Segment, ...]) -> str:
        return self._save(
            "segments",
            run_id,
            segments,
            [segment.model_dump(mode="json") for segment in segments],
        )

    def load_segments(self, ref: str) -> tuple[Segment, ...]:
        value = self._objects[ref]
        if not isinstance(value, tuple) or any(not isinstance(item, Segment) for item in value):
            raise TypeError("artifact reference is not a segment collection")
        return value

    def save_extraction(self, run_id: str, result: ExtractionResult) -> str:
        return self._save("extraction", run_id, result, result.model_dump(mode="json"))

    def load_extraction(self, ref: str) -> ExtractionResult:
        value = self._objects[ref]
        if not isinstance(value, ExtractionResult):
            raise TypeError("artifact reference is not an extraction result")
        return value

    def save_verification(self, run_id: str, result: VerificationResult) -> str:
        return self._save("verification", run_id, result, result.model_dump(mode="json"))

    def load_verification(self, ref: str) -> VerificationResult:
        value = self._objects[ref]
        if not isinstance(value, VerificationResult):
            raise TypeError("artifact reference is not a verification result")
        return value


def create_ingestion_graph_builder(
    *,
    artifacts: IngestionArtifactPort,
    extractor: EvidenceExtractor,
    verifier: CitationVerifier | None = None,
) -> Any:
    """Return an uncompiled LangGraph builder so the app can inject a checkpointer."""

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover - dependency setup failure
        raise RuntimeError("ingestion graph requires the langgraph package") from exc

    citation_verifier = verifier or CitationVerifier()

    def parse_node(state: IngestionState) -> Mapping[str, Any]:
        blob_ref = BlobRef.model_validate(state["blob_ref"])
        source_bytes = artifacts.load_blob(blob_ref)
        segments = parse_source(
            source_revision_id=state["source_revision_id"],
            content=source_bytes,
            filename=state.get("filename"),
            media_type=state.get("media_type") or blob_ref.media_type,
        )
        segments_ref = artifacts.save_segments(state["run_id"], segments)
        return {"segments_ref": segments_ref, "stage": "parsed"}

    def extract_node(state: IngestionState) -> Mapping[str, Any]:
        segments = artifacts.load_segments(state["segments_ref"])
        result = extractor.extract(segments)
        extraction_ref = artifacts.save_extraction(state["run_id"], result)
        return {"extraction_ref": extraction_ref, "stage": "extracted"}

    def verify_node(state: IngestionState) -> Mapping[str, Any]:
        blob_ref = BlobRef.model_validate(state["blob_ref"])
        source_bytes = artifacts.load_blob(blob_ref)
        segments = artifacts.load_segments(state["segments_ref"])
        extraction = artifacts.load_extraction(state["extraction_ref"])
        verification = citation_verifier.verify(extraction, segments, source_bytes)
        verification_ref = artifacts.save_verification(state["run_id"], verification)
        return {"verification_ref": verification_ref, "stage": "verified"}

    builder = StateGraph(IngestionState)
    builder.add_node("parse", parse_node)
    builder.add_node("extract", extract_node)
    builder.add_node("verify", verify_node)
    builder.add_edge(START, "parse")
    builder.add_edge("parse", "extract")
    builder.add_edge("extract", "verify")
    builder.add_edge("verify", END)
    return builder


def compile_ingestion_graph(
    *,
    artifacts: IngestionArtifactPort,
    extractor: EvidenceExtractor,
    verifier: CitationVerifier | None = None,
    checkpointer: Any | None = None,
) -> Any:
    builder = create_ingestion_graph_builder(
        artifacts=artifacts,
        extractor=extractor,
        verifier=verifier,
    )
    return builder.compile(checkpointer=checkpointer)
