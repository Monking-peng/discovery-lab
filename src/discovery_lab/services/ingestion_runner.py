from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from discovery_lab.agent_harness.ingestion_graph import (
    InMemoryIngestionArtifacts,
    compile_ingestion_graph,
)
from discovery_lab.agent_harness.openai_responses import (
    SYSTEM_INSTRUCTIONS,
    OpenAIResponsesConfig,
    OpenAIResponsesExtractor,
)
from discovery_lab.ingestion import (
    BlobRef,
    CitationVerifier,
    DeterministicDemoExtractor,
    EvidenceExtractor,
    ExtractionResult,
    Segment,
    VerificationResult,
)
from discovery_lab.services.hashing import sha256_bytes, sha256_text
from discovery_lab.services.storage import BlobStore as ApplicationBlobStore


class CitationIntegrityFailure(RuntimeError):
    """Raised when any model/demo citation cannot be replayed exactly."""


class _ApplicationBlobAdapter:
    """Expose the application blob store through the ingestion read-only port."""

    def __init__(self, store: ApplicationBlobStore) -> None:
        self._store = store

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str | None = None,
        expected_sha256: str | None = None,
    ) -> BlobRef:
        digest = sha256_bytes(content)
        if expected_sha256 is not None and expected_sha256 != digest:
            raise ValueError("content digest does not match expected_sha256")
        self._store.put(content, content_hash=digest)
        return BlobRef(digest=digest, size_bytes=len(content), media_type=media_type)

    def read_bytes(self, ref: BlobRef) -> bytes:
        return self._store.get(ref.uri)

    def contains(self, digest: str) -> bool:
        try:
            self._store.get(f"blob://sha256/{digest}")
        except (FileNotFoundError, OSError, ValueError):
            return False
        return True


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not-installed"


@dataclass(frozen=True, slots=True)
class IngestionExecutionResult:
    segments: tuple[Segment, ...]
    extraction: ExtractionResult
    verification: VerificationResult
    graph_state: dict[str, Any]


class IngestionRunner:
    """Run the bounded LangGraph ingestion workflow and return verified artifacts."""

    workflow_name = "source_to_evidence"
    workflow_version = "2.0.0"
    verifier_name = "deterministic-citation-verifier"
    verifier_version = "1.0.0"

    def __init__(
        self,
        *,
        blob_store: ApplicationBlobStore,
        extractor: EvidenceExtractor,
    ) -> None:
        self.blob_store = blob_store
        self.extractor = extractor

    @property
    def profile(self) -> dict[str, Any]:
        extractor_config: dict[str, Any]
        config = getattr(self.extractor, "config", None)
        if config is not None and hasattr(config, "model_dump"):
            extractor_config = config.model_dump(mode="json")
        else:
            extractor_config = {
                "max_evidence": getattr(self.extractor, "max_evidence", None),
                "max_quote_chars": getattr(self.extractor, "max_quote_chars", None),
            }
        return {
            "workflow": {
                "name": self.workflow_name,
                "version": self.workflow_version,
            },
            "runtime": {"langgraph_version": _package_version("langgraph")},
            "parser": {
                "name": "deterministic-source-parser",
                "version": "1.0.0",
                "schema_version": "segment.v1",
                "supported_formats": ["text", "markdown", "csv", "pdf"],
                "pymupdf_version": _package_version("PyMuPDF"),
            },
            "extractor": {
                "name": getattr(self.extractor, "name", type(self.extractor).__name__),
                "version": getattr(self.extractor, "version", "unknown"),
                "prompt_version": getattr(
                    getattr(self.extractor, "config", None), "prompt_version", None
                ),
                "model": getattr(getattr(self.extractor, "config", None), "model", None),
                "configuration": extractor_config,
                "system_instructions_sha256": (
                    sha256_text(SYSTEM_INSTRUCTIONS)
                    if isinstance(self.extractor, OpenAIResponsesExtractor)
                    else None
                ),
            },
            "verifier": {
                "name": self.verifier_name,
                "version": self.verifier_version,
                "semantic_support_checked": False,
            },
            "artifact_policy": "verified_results_persisted_transactionally",
        }

    def run(
        self,
        *,
        run_id: str,
        source_revision_id: str,
        content: bytes,
        filename: str,
        media_type: str,
    ) -> IngestionExecutionResult:
        adapter = _ApplicationBlobAdapter(self.blob_store)
        blob_ref = adapter.put_bytes(
            content,
            media_type=media_type,
            expected_sha256=sha256_bytes(content),
        )
        artifacts = InMemoryIngestionArtifacts(adapter)
        graph = compile_ingestion_graph(
            artifacts=artifacts,
            extractor=self.extractor,
            verifier=CitationVerifier(),
        )
        state = graph.invoke(
            {
                "run_id": run_id,
                "source_revision_id": source_revision_id,
                "blob_ref": blob_ref.model_dump(mode="json"),
                "filename": filename,
                "media_type": media_type,
                "stage": "registered",
            },
            config={"configurable": {"thread_id": run_id}},
        )
        segments = artifacts.load_segments(state["segments_ref"])
        extraction = artifacts.load_extraction(state["extraction_ref"])
        verification = artifacts.load_verification(state["verification_ref"])
        draft_ids = [draft.draft_id for draft in extraction.drafts]
        check_ids = [check.draft_id for check in verification.checks]
        if (
            len(set(draft_ids)) != len(draft_ids)
            or len(set(check_ids)) != len(check_ids)
            or set(draft_ids) != set(check_ids)
            or not verification.all_verified
        ):
            raise CitationIntegrityFailure("one or more evidence citations failed verification")
        return IngestionExecutionResult(
            segments=segments,
            extraction=extraction,
            verification=verification,
            graph_state={
                "stage": state["stage"],
                "segments_ref": state["segments_ref"],
                "extraction_ref": state["extraction_ref"],
                "verification_ref": state["verification_ref"],
            },
        )


def build_ingestion_runner(
    *,
    blob_store: ApplicationBlobStore,
    mode: str,
    openai_model: str,
    openai_api_key: str | None,
    prompt_version: str,
) -> IngestionRunner:
    if mode == "demo":
        extractor: EvidenceExtractor = DeterministicDemoExtractor()
    elif mode == "openai":
        extractor = OpenAIResponsesExtractor(
            config=OpenAIResponsesConfig(
                model=openai_model,
                prompt_version=prompt_version,
            ),
            api_key=openai_api_key,
        )
    else:
        raise ValueError(f"unsupported evidence extractor mode: {mode}")
    return IngestionRunner(blob_store=blob_store, extractor=extractor)
