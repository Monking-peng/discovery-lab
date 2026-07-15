from __future__ import annotations

from discovery_lab.agent_harness import InMemoryIngestionArtifacts, compile_ingestion_graph
from discovery_lab.ingestion import DeterministicDemoExtractor, LocalBlobStore


def test_graph_persists_artifacts_and_checkpoints_only_small_refs(tmp_path) -> None:
    blob_store = LocalBlobStore(tmp_path / "blobs")
    blob_ref = blob_store.put_bytes(
        b"A user needs urgent-ticket escalation.", media_type="text/plain"
    )
    artifacts = InMemoryIngestionArtifacts(blob_store)
    graph = compile_ingestion_graph(
        artifacts=artifacts,
        extractor=DeterministicDemoExtractor(),
    )

    state = graph.invoke(
        {
            "run_id": "run_1",
            "source_revision_id": "rev_1",
            "blob_ref": blob_ref.model_dump(mode="json"),
            "filename": "interview.txt",
            "media_type": "text/plain",
        }
    )

    assert state["stage"] == "verified"
    assert state["segments_ref"].startswith("memory://segments/")
    assert state["extraction_ref"].startswith("memory://extraction/")
    assert state["verification_ref"].startswith("memory://verification/")
    assert "segments" not in state
    assert "extraction" not in state
    assert artifacts.load_verification(state["verification_ref"]).all_verified
