from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from discovery_lab.evaluation.evidence_to_claim import (
    EvaluationReport as EvidenceToClaimReport,
)
from discovery_lab.evaluation.evidence_to_claim import (
    run_evaluation as run_evidence_to_claim,
)
from discovery_lab.evaluation.source_to_evidence import (
    EvaluationReport as SourceToEvidenceReport,
)
from discovery_lab.evaluation.source_to_evidence import (
    run_evaluation as run_source_to_evidence,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BadCaseRecord(StrictModel):
    schema_version: Literal["bad-case.v1"]
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    discovered_at: datetime
    stage: Literal[
        "parse_source",
        "extract_evidence",
        "verify_citation",
        "review_evidence",
        "promote_claim",
        "retrieve_context",
        "tool_call",
        "publish_artifact",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    fixture: str = Field(min_length=1)
    symptom: str = Field(min_length=1)
    safe_error_code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    root_cause: str = Field(min_length=1)
    resolution: str = Field(min_length=1)
    regression_test: str = Field(min_length=1)
    recovery_verified: bool
    data_loss: bool

    @field_validator("fixture")
    @classmethod
    def fixture_is_safe_repo_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts or normalized.startswith("/"):
            raise ValueError("fixture must be a repository-relative path")
        return normalized

    @field_validator("regression_test")
    @classmethod
    def regression_test_is_repo_relative(cls, value: str) -> str:
        target = value.split("::", maxsplit=1)[0].replace("\\", "/")
        path = PurePosixPath(target)
        if not target or path.is_absolute() or ".." in path.parts:
            raise ValueError("regression_test must identify a repository-relative test")
        return value

    @model_validator(mode="after")
    def discovered_at_has_timezone(self) -> BadCaseRecord:
        if self.discovered_at.tzinfo is None or self.discovered_at.utcoffset() is None:
            raise ValueError("discovered_at must include a timezone")
        return self


class BadCaseInbox(StrictModel):
    schema_version: Literal["bad-case-inbox.v1"] = "bad-case-inbox.v1"
    generated_at: datetime
    total: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    items: tuple[BadCaseRecord, ...]


class CurrentEvaluationReport(StrictModel):
    schema_version: Literal["evaluation-report-index.v1"] = "evaluation-report-index.v1"
    generated_at: datetime
    total_cases: int = Field(ge=1)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    release_gate_passed: bool
    dataset_revisions: dict[str, int]
    source_to_evidence: SourceToEvidenceReport
    evidence_to_claim: EvidenceToClaimReport


class EvaluationDataError(RuntimeError):
    def __init__(self, resource: str, filename: str) -> None:
        super().__init__(f"invalid evaluation data: {resource}")
        self.resource = resource
        self.filename = filename


class EvaluationReportingService:
    """Read-only facade over repository-owned, fixed evaluation resources."""

    def __init__(self, project_root: Path = PROJECT_ROOT) -> None:
        self.project_root = project_root.resolve()

    def current_report(self) -> CurrentEvaluationReport:
        source_path = self.project_root / "evals" / "golden" / "source_to_evidence.json"
        claim_path = self.project_root / "evals" / "golden" / "evidence_to_claim.json"
        try:
            source_report = run_source_to_evidence(
                source_path,
                project_root=self.project_root,
            )
        except (OSError, ValueError) as exc:
            raise EvaluationDataError("golden_dataset", source_path.name) from exc
        try:
            claim_report = run_evidence_to_claim(claim_path)
        except (OSError, ValueError) as exc:
            raise EvaluationDataError("golden_dataset", claim_path.name) from exc

        total_cases = source_report.summary.case_count + claim_report.summary.case_count
        passed = source_report.summary.passed + claim_report.summary.passed
        failed = source_report.summary.failed + claim_report.summary.failed
        skipped = 0
        return CurrentEvaluationReport(
            generated_at=datetime.now(UTC),
            total_cases=total_cases,
            passed=passed,
            failed=failed,
            skipped=skipped,
            release_gate_passed=failed == 0 and skipped == 0 and passed == total_cases,
            dataset_revisions={
                source_report.dataset: source_report.dataset_revision,
                claim_report.dataset: claim_report.dataset_revision,
            },
            source_to_evidence=source_report,
            evidence_to_claim=claim_report,
        )

    def bad_case_inbox(self) -> BadCaseInbox:
        directory = (self.project_root / "evals" / "bad-cases").resolve()
        if not directory.is_dir():
            raise EvaluationDataError("bad_case_inbox", "bad-cases")
        try:
            paths = sorted(directory.glob("*.json"), key=lambda path: path.name)
        except OSError as exc:
            raise EvaluationDataError("bad_case_inbox", "bad-cases") from exc

        records: list[BadCaseRecord] = []
        identifiers: set[str] = set()
        for path in paths:
            resolved = path.resolve()
            if not resolved.is_relative_to(directory):
                raise EvaluationDataError("bad_case_inbox", path.name)
            try:
                record = BadCaseRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise EvaluationDataError("bad_case_inbox", path.name) from exc
            if record.id in identifiers:
                raise EvaluationDataError("bad_case_inbox", path.name)
            fixture_path = (self.project_root / record.fixture).resolve()
            regression_path = (
                self.project_root / record.regression_test.split("::", maxsplit=1)[0]
            ).resolve()
            if (
                not fixture_path.is_relative_to(self.project_root)
                or not fixture_path.is_file()
                or not regression_path.is_relative_to(self.project_root)
                or not regression_path.is_file()
            ):
                raise EvaluationDataError("bad_case_inbox", path.name)
            identifiers.add(record.id)
            records.append(record)

        ordered = tuple(sorted(records, key=lambda record: (record.discovered_at, record.id)))
        return BadCaseInbox(
            generated_at=datetime.now(UTC),
            total=len(ordered),
            unresolved=sum(not record.recovery_verified for record in ordered),
            items=ordered,
        )


def get_evaluation_reporting_service() -> EvaluationReportingService:
    return EvaluationReportingService()
