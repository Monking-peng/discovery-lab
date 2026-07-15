from __future__ import annotations

from discovery_lab.ingestion import DeterministicDemoExtractor
from discovery_lab.services.ingestion_runner import IngestionRunner
from discovery_lab.services.storage import LocalBlobStore


def test_ingestion_runner_executes_bounded_graph_with_only_artifact_refs(tmp_path) -> None:
    runner = IngestionRunner(
        blob_store=LocalBlobStore(tmp_path / "blobs"),
        extractor=DeterministicDemoExtractor(),
    )
    raw_source = b"Customer needs reliable escalation."

    result = runner.run(
        run_id="run_test",
        source_revision_id="revision_test",
        content=raw_source,
        filename="interview.txt",
        media_type="text/plain",
    )

    assert result.graph_state["stage"] == "verified"
    assert result.graph_state["segments_ref"].startswith("memory://segments/run_test/")
    assert result.graph_state["extraction_ref"].startswith("memory://extraction/run_test/")
    assert result.graph_state["verification_ref"].startswith("memory://verification/run_test/")
    assert raw_source.decode() not in repr(result.graph_state)
    assert len(result.segments) == 1
    assert len(result.extraction.drafts) == 1
    assert result.extraction.synthetic_demo is True
    assert result.verification.all_verified

    profile = runner.profile
    assert profile["workflow"] == {"name": "source_to_evidence", "version": "2.0.0"}
    assert profile["extractor"]["name"] == "deterministic-demo-extractor"
    assert profile["extractor"]["version"] == "1.0.0"
    assert "api_key" not in repr(profile).lower()
