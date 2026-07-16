import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from discovery_lab.evaluation.source_to_evidence import GoldenDataset, run_evaluation


def test_helphub_golden_dataset_passes_source_to_evidence_gate() -> None:
    project_root = Path(__file__).resolve().parents[2]

    report = run_evaluation(
        project_root / "evals" / "golden" / "source_to_evidence.json",
        project_root=project_root,
    )

    assert report.summary.failed == 0
    assert report.summary.case_count == 11
    assert report.summary.passed == 11
    assert report.summary.citation_integrity_rate == 1.0
    assert report.summary.locator_replay_rate == 1.0
    injection = next(case for case in report.cases if case.case_id == "source-prompt-injection")
    assert injection.status == "passed"
    assert all(injection.assertions.values())


def test_insufficient_support_case_is_executed_not_skipped() -> None:
    project_root = Path(__file__).resolve().parents[2]
    report = run_evaluation(
        project_root / "evals" / "golden" / "source_to_evidence.json",
        project_root=project_root,
    )

    result = next(
        case for case in report.cases if case.case_id == "universal-auto-escalation-is-unsupported"
    )

    assert result.status == "passed"
    assert result.details["actual_status"] == "insufficient_evidence"
    assert result.assertions["counterevidence_quotes_replayed"] is True
    assert result.assertions["universal_claim_has_no_exact_source_support"] is True


def test_unknown_case_fields_are_rejected_instead_of_skipped() -> None:
    project_root = Path(__file__).resolve().parents[2]
    payload = json.loads(
        (project_root / "evals" / "golden" / "source_to_evidence.json").read_text(encoding="utf-8")
    )
    payload["cases"][0]["unknown_expectation"] = True

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)
