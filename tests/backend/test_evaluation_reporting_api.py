from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from discovery_lab.api.errors import AppError
from discovery_lab.api.evaluation_routes import router
from discovery_lab.services.evaluation_reporting import (
    BadCaseRecord,
    EvaluationDataError,
    EvaluationReportingService,
    get_evaluation_reporting_service,
)


def _app(service: EvaluationReportingService) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_evaluation_reporting_service] = lambda: service
    return app


def test_current_report_api_returns_real_case_results_and_dataset_revisions() -> None:
    project_root = Path(__file__).resolve().parents[2]
    with TestClient(_app(EvaluationReportingService(project_root))) as client:
        response = client.get("/v1/evaluation/reports/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cases"] == 26
    assert payload["passed"] == 26
    assert payload["failed"] == 0
    assert payload["skipped"] == 0
    assert payload["release_gate_passed"] is True
    assert payload["dataset_revisions"] == {
        "helphub-source-to-evidence": 2,
        "evidence-to-claim-integrity": 2,
    }
    assert len(payload["source_to_evidence"]["cases"]) == 11
    assert len(payload["evidence_to_claim"]["cases"]) == 15


def test_bad_case_inbox_is_strict_and_repository_owned() -> None:
    project_root = Path(__file__).resolve().parents[2]
    app = _app(EvaluationReportingService(project_root))
    operation = app.openapi()["paths"]["/v1/evaluation/bad-cases"]["get"]
    with TestClient(app) as client:
        response = client.get("/v1/evaluation/bad-cases")

    assert operation.get("parameters", []) == []
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert response.json()["items"][0]["schema_version"] == "bad-case.v1"


def test_malformed_bad_case_fails_closed_without_partial_inbox(tmp_path: Path) -> None:
    directory = tmp_path / "evals" / "bad-cases"
    directory.mkdir(parents=True)
    malformed = {
        "schema_version": "bad-case.v1",
        "id": "malformed-case",
        "discovered_at": "2026-07-15T10:00:00Z",
        "stage": "parse_source",
        "severity": "medium",
        "fixture": "fixtures/input.csv",
        "symptom": "failure",
        "safe_error_code": "invalid_source",
        "root_cause": "cause",
        "resolution": "fix",
        "regression_test": "tests/test_input.py::test_case",
        "recovery_verified": False,
        "data_loss": False,
        "unexpected": "must be rejected",
    }
    (directory / "malformed.json").write_text(json.dumps(malformed), encoding="utf-8")
    service = EvaluationReportingService(tmp_path)

    with pytest.raises(EvaluationDataError):
        service.bad_case_inbox()

    with TestClient(_app(service), raise_server_exceptions=False) as client:
        response = client.get("/v1/evaluation/bad-cases")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "evaluation_data_invalid"


def test_bad_case_schema_rejects_path_traversal() -> None:
    payload = {
        "schema_version": "bad-case.v1",
        "id": "unsafe-fixture",
        "discovered_at": "2026-07-15T10:00:00Z",
        "stage": "parse_source",
        "severity": "high",
        "fixture": "../secret.txt",
        "symptom": "unsafe path",
        "safe_error_code": "invalid_source",
        "root_cause": "unsafe input",
        "resolution": "reject path",
        "regression_test": "tests/test_input.py::test_case",
        "recovery_verified": False,
        "data_loss": False,
    }

    with pytest.raises(ValueError):
        BadCaseRecord.model_validate(payload)
