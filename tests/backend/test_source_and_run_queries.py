from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from discovery_lab.db.models import SourceRevision
from discovery_lab.services.hashing import sha256_bytes


def _create_study(client: TestClient) -> str:
    response = client.post(
        "/v1/studies",
        json={"title": "Query API study", "decision_question": "What should change?"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _upload_source(client: TestClient, study_id: str, filename: str) -> dict[str, object]:
    response = client.post(
        f"/v1/studies/{study_id}/sources",
        files={"file": (filename, f"Traceable content from {filename}", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_source_query_is_paginated_and_returns_latest_revision_and_real_state(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    study_id = _create_study(client)
    queued = _upload_source(client, study_id, "queued.txt")
    ready = _upload_source(client, study_id, "ready.txt")
    third = _upload_source(client, study_id, "third.txt")

    process_response = client.post(f"/v1/sources/{ready['id']}:process")
    assert process_response.status_code == 200, process_response.text

    revised_content = b"A second immutable revision"
    with session_factory() as session:
        session.add(
            SourceRevision(
                source_id=UUID(str(queued["id"])),
                revision=2,
                filename="queued-v2.txt",
                mime_type="text/plain",
                byte_size=len(revised_content),
                content_hash=sha256_bytes(revised_content),
                blob_uri="sha256://test/latest-revision",
                provenance={"test_fixture": True},
            )
        )
        session.commit()

    pages: list[dict[str, object]] = []
    for offset in range(3):
        response = client.get(
            f"/v1/studies/{study_id}/sources",
            params={"limit": 1, "offset": offset},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert set(payload) == {"items", "total"}
        assert payload["total"] == 3
        assert len(payload["items"]) == 1
        pages.extend(payload["items"])

    assert {item["id"] for item in pages} == {queued["id"], ready["id"], third["id"]}
    by_id = {item["id"]: item for item in pages}

    queued_item = by_id[queued["id"]]
    assert queued_item["domain_status"] == "UPLOADED"
    assert queued_item["status"] == "queued"
    assert queued_item["progress"] == 0
    assert queued_item["revision"]["revision"] == 2
    assert queued_item["revision"]["filename"] == "queued-v2.txt"

    ready_item = by_id[ready["id"]]
    assert ready_item["domain_status"] == "PROCESSED"
    assert ready_item["status"] == "ready"
    assert ready_item["progress"] == 100

    beyond_end = client.get(
        f"/v1/studies/{study_id}/sources",
        params={"limit": 10, "offset": 99},
    ).json()
    assert beyond_end == {"items": [], "total": 3}


def test_run_query_returns_three_steps_and_preserves_total_across_pages(
    client: TestClient,
) -> None:
    study_id = _create_study(client)
    sources = [_upload_source(client, study_id, f"source-{index}.txt") for index in range(3)]
    for source in sources:
        response = client.post(f"/v1/sources/{source['id']}:process")
        assert response.status_code == 200, response.text

    first_page = client.get(
        f"/v1/studies/{study_id}/runs",
        params={"limit": 2, "offset": 0},
    )
    assert first_page.status_code == 200, first_page.text
    first_payload = first_page.json()
    assert set(first_payload) == {"items", "total"}
    assert first_payload["total"] == 3
    assert len(first_payload["items"]) == 2

    second_payload = client.get(
        f"/v1/studies/{study_id}/runs",
        params={"limit": 2, "offset": 2},
    ).json()
    assert second_payload["total"] == 3
    assert len(second_payload["items"]) == 1

    runs = [*first_payload["items"], *second_payload["items"]]
    assert len({run["id"] for run in runs}) == 3
    assert {run["source_id"] for run in runs} == {source["id"] for source in sources}
    for run in runs:
        assert run["status"] == "SUCCEEDED"
        assert [step["name"] for step in run["steps"]] == [
            "parse_source",
            "extract_evidence",
            "verify_citations",
        ]
        assert [step["ordinal"] for step in run["steps"]] == [0, 1, 2]
        assert all(step["status"] == "SUCCEEDED" for step in run["steps"])


def test_source_and_run_queries_surface_failed_processing_state(client: TestClient) -> None:
    study_id = _create_study(client)
    upload = client.post(
        f"/v1/studies/{study_id}/sources",
        files={
            "file": (
                "unsupported.docx",
                b"not a word document",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload.status_code == 201, upload.text

    process = client.post(f"/v1/sources/{upload.json()['id']}:process")
    assert process.status_code == 422
    assert process.json()["error"]["code"] == "unsupported_source"

    source_payload = client.get(f"/v1/studies/{study_id}/sources").json()
    assert source_payload["total"] == 1
    source = source_payload["items"][0]
    assert source["domain_status"] == "FAILED"
    assert source["status"] == "failed"
    assert source["progress"] == 0

    run_payload = client.get(f"/v1/studies/{study_id}/runs").json()
    assert run_payload["total"] == 1
    run = run_payload["items"][0]
    assert run["status"] == "FAILED"
    assert [step["status"] for step in run["steps"]] == ["FAILED", "SKIPPED", "SKIPPED"]


def test_source_and_run_queries_validate_pagination_and_missing_studies(
    client: TestClient,
) -> None:
    missing_id = uuid4()
    for collection in ("sources", "runs"):
        missing = client.get(f"/v1/studies/{missing_id}/{collection}")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"

        invalid_limit = client.get(f"/v1/studies/{missing_id}/{collection}", params={"limit": 0})
        assert invalid_limit.status_code == 422
        assert invalid_limit.json()["error"]["code"] == "validation_error"

        invalid_offset = client.get(f"/v1/studies/{missing_id}/{collection}", params={"offset": -1})
        assert invalid_offset.status_code == 422
        assert invalid_offset.json()["error"]["code"] == "validation_error"
