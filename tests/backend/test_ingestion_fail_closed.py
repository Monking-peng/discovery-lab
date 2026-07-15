from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from discovery_lab.agent_harness.openai_responses import (
    OpenAIResponsesConfig,
    OpenAIResponsesExtractor,
)
from discovery_lab.config import Settings
from discovery_lab.db.models import EvidenceUnit, Run, Segment
from discovery_lab.ingestion import DeterministicDemoExtractor
from discovery_lab.ingestion.models import (
    EvidenceDraft,
    ExtractionMethod,
    ExtractionResult,
)
from discovery_lab.ingestion.models import (
    Segment as ParsedSegment,
)
from discovery_lab.ingestion.parsers import narrow_locator
from discovery_lab.main import create_app
from discovery_lab.services.hashing import sha256_text
from discovery_lab.services.ingestion_runner import IngestionRunner
from discovery_lab.services.storage import LocalBlobStore


def _client_for(
    *,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    extractor: Any,
) -> TestClient:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        blob_root=tmp_path / "blobs",
        upload_max_bytes=1024 * 1024,
    )
    blob_store = LocalBlobStore(settings.blob_root)
    return TestClient(
        create_app(
            settings=settings,
            session_factory=session_factory,
            blob_store=blob_store,
            ingestion_runner=IngestionRunner(
                blob_store=blob_store,
                extractor=extractor,
            ),
        )
    )


def _upload(client: TestClient, *, content: str = "source truth") -> str:
    study = client.post("/v1/studies", json={"title": "Fail-closed study"})
    assert study.status_code == 201
    source = client.post(
        f"/v1/studies/{study.json()['id']}/sources",
        files={"file": ("source.txt", content.encode(), "text/plain")},
    )
    assert source.status_code == 201
    return str(source.json()["id"])


class _NeverCalledResponses:
    def parse(self, **_kwargs: Any) -> Any:
        raise AssertionError("missing credentials must fail before a provider call")


class _FakeClient:
    def __init__(self, responses: Any) -> None:
        self.responses = responses


def test_missing_model_key_fails_extract_step_without_partial_artifacts(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    extractor = OpenAIResponsesExtractor(
        config=OpenAIResponsesConfig(model="test-model"),
        api_key=None,
        client=_FakeClient(_NeverCalledResponses()),
    )
    with _client_for(
        session_factory=session_factory,
        tmp_path=tmp_path,
        extractor=extractor,
    ) as client:
        source_id = _upload(client)
        response = client.post(f"/v1/sources/{source_id}:process")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "model_not_configured"
    with session_factory() as session:
        run = session.scalar(select(Run))
        assert run is not None
        assert [(step.name, step.status) for step in run.steps] == [
            ("parse_source", "SUCCEEDED"),
            ("extract_evidence", "FAILED"),
            ("verify_citations", "SKIPPED"),
        ]
        assert session.scalar(select(func.count()).select_from(Segment)) == 0
        assert session.scalar(select(func.count()).select_from(EvidenceUnit)) == 0


class _FabricatingResponses:
    def parse(self, **kwargs: Any) -> Any:
        envelope = kwargs["text_format"](
            proposals=[
                {
                    "segment_id": "unknown_segment",
                    "quote": "fabricated quote",
                    "quote_start": 0,
                    "observation": "unsupported",
                    "confidence": 0.2,
                }
            ]
        )
        return SimpleNamespace(id="resp_bad", output_parsed=envelope, usage=None)


def test_model_output_with_unknown_segment_is_rejected_as_safe_502(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    extractor = OpenAIResponsesExtractor(
        config=OpenAIResponsesConfig(model="test-model"),
        api_key="test-key",
        client=_FakeClient(_FabricatingResponses()),
    )
    with _client_for(
        session_factory=session_factory,
        tmp_path=tmp_path,
        extractor=extractor,
    ) as client:
        source_id = _upload(client)
        response = client.post(f"/v1/sources/{source_id}:process")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "model_output_invalid"
    assert "unknown_segment" not in response.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(EvidenceUnit)) == 0


class _TamperedCitationExtractor:
    name = "tampered-citation-test"
    version = "1.0.0"

    def extract(self, segments: tuple[ParsedSegment, ...]) -> ExtractionResult:
        segment = segments[0]
        replayed_quote = "truth"
        locator = narrow_locator(segment, replayed_quote, segment.text.index(replayed_quote))
        claimed_quote = "source"
        tampered_locator = locator.model_copy(update={"quote_sha256": sha256_text(claimed_quote)})
        draft = EvidenceDraft.create(
            source_revision_id=segment.source_revision_id,
            segment_id=segment.segment_id,
            locator=tampered_locator,
            quote=claimed_quote,
            observation="This should never persist.",
            interpretation=None,
            inference=None,
            confidence=0.5,
            tags=("tampered",),
            extraction_method=ExtractionMethod.DETERMINISTIC_DEMO,
            synthetic_demo=True,
        )
        return ExtractionResult(
            extractor_name=self.name,
            extractor_version=self.version,
            synthetic_demo=True,
            drafts=(draft,),
        )


def test_citation_tamper_fails_verify_step_and_persists_no_evidence(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    with _client_for(
        session_factory=session_factory,
        tmp_path=tmp_path,
        extractor=_TamperedCitationExtractor(),
    ) as client:
        source_id = _upload(client)
        response = client.post(f"/v1/sources/{source_id}:process")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_source"
    with session_factory() as session:
        run = session.scalar(select(Run))
        assert run is not None
        assert [(step.name, step.status) for step in run.steps] == [
            ("parse_source", "SUCCEEDED"),
            ("extract_evidence", "SUCCEEDED"),
            ("verify_citations", "FAILED"),
        ]
        assert session.scalar(select(func.count()).select_from(Segment)) == 0
        assert session.scalar(select(func.count()).select_from(EvidenceUnit)) == 0


def test_profile_change_creates_new_run_but_reuses_immutable_segments(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        blob_root=tmp_path / "profile-blobs",
    )
    blob_store = LocalBlobStore(settings.blob_root)
    first_runner = IngestionRunner(
        blob_store=blob_store,
        extractor=DeterministicDemoExtractor(max_evidence=1),
    )
    app = create_app(
        settings=settings,
        session_factory=session_factory,
        blob_store=blob_store,
        ingestion_runner=first_runner,
    )
    with TestClient(app) as client:
        source_id = _upload(client, content="first block\n\nsecond block")
        first = client.post(f"/v1/sources/{source_id}:process")
        assert first.status_code == 200

        app.state.ingestion_runner = IngestionRunner(
            blob_store=blob_store,
            extractor=DeterministicDemoExtractor(max_evidence=2),
        )
        second = client.post(f"/v1/sources/{source_id}:process")
        assert second.status_code == 200
        assert second.json()["id"] != first.json()["id"]

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 2
        assert session.scalar(select(func.count()).select_from(Segment)) == 2


def test_zero_proposals_is_an_explicit_success_with_warning(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    with _client_for(
        session_factory=session_factory,
        tmp_path=tmp_path,
        extractor=DeterministicDemoExtractor(max_evidence=0),
    ) as client:
        source_id = _upload(client)
        response = client.post(f"/v1/sources/{source_id}:process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "SUCCEEDED"
    assert payload["output_summary"]["evidence_candidate_count"] == 0
    assert "no_evidence_proposals" in payload["output_summary"]["warnings"]
