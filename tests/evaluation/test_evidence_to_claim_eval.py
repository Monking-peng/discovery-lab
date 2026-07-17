import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from discovery_lab.evaluation.evidence_to_claim import GoldenDataset, run_evaluation


def test_evidence_to_claim_golden_dataset_passes_release_gate() -> None:
    project_root = Path(__file__).resolve().parents[2]

    report = run_evaluation(project_root / "evals" / "golden" / "evidence_to_claim.json")

    assert report.summary.failed == 0
    assert report.summary.case_count == 15
    assert report.summary.passed == 15
    assert report.summary.claim_review_eligibility_accuracy == 1.0
    assert report.summary.blocker_contract_accuracy == 1.0
    assert report.summary.publication_safety_rate == 1.0
    assert report.summary.counterevidence_not_run_block_rate == 1.0
    assert report.summary.exact_old_revision_replay_rate == 1.0


def test_not_run_counterevidence_is_an_explicit_publication_blocker() -> None:
    project_root = Path(__file__).resolve().parents[2]
    report = run_evaluation(project_root / "evals" / "golden" / "evidence_to_claim.json")

    result = next(
        case
        for case in report.cases
        if case.case_id == "counterevidence-not-run-blocks-publication"
    )

    assert result.status == "passed"
    assert result.details["eligible_for_claim_review"] is True
    assert result.details["counterevidence_interpretation"] == "not_evaluated"
    assert result.details["publication_blockers"] == ["COUNTEREVIDENCE_NOT_RUN"]
    assert result.assertions["not_run_is_not_treated_as_no_counterevidence"] is True


def test_old_evidence_revision_is_replayed_without_latest_revision_substitution() -> None:
    project_root = Path(__file__).resolve().parents[2]
    report = run_evaluation(project_root / "evals" / "golden" / "evidence_to_claim.json")

    result = next(
        case for case in report.cases if case.case_id == "old-revision-replays-by-exact-identity"
    )

    assert result.status == "passed"
    assert result.details["exact_revision_replay"] is True
    assert result.details["old_revision_identity_preserved"] is True
    assert result.assertions["requested_revision_replayed_exactly"] is True
    assert result.assertions["old_revision_not_substituted_by_latest"] is True


def test_invalid_support_cases_fail_closed_with_exact_blockers() -> None:
    project_root = Path(__file__).resolve().parents[2]
    report = run_evaluation(project_root / "evals" / "golden" / "evidence_to_claim.json")
    expected = {
        "missing-evidence-review-fails-closed": "EVIDENCE_REVIEW_NOT_ACCEPTED",
        "synthetic-support-cannot-promote": "SYNTHETIC_EVIDENCE",
        "cross-study-support-cannot-promote": "CROSS_STUDY_EVIDENCE",
        "revision-resolution-mismatch-fails-closed": "EVIDENCE_REVISION_MISMATCH",
        "citation-integrity-failure-blocks-review": "CITATION_INTEGRITY_FAILED",
        "locator-replay-failure-blocks-review": "LOCATOR_REPLAY_FAILED",
        "context-only-claim-has-no-support": "NO_CONFIRMED_SUPPORT",
    }

    for case_id, blocker in expected.items():
        result = next(case for case in report.cases if case.case_id == case_id)
        assert result.status == "passed"
        assert result.details["eligible_for_claim_review"] is False
        assert result.details["review_blockers"] == [blocker]
        assert result.details["publication_blockers"] == [blocker]


def test_multiple_blockers_are_reported_without_hiding_not_run() -> None:
    project_root = Path(__file__).resolve().parents[2]
    report = run_evaluation(project_root / "evals" / "golden" / "evidence_to_claim.json")
    result = next(
        case
        for case in report.cases
        if case.case_id == "multiple-independent-blockers-are-all-visible"
    )

    assert result.status == "passed"
    assert len(result.details["review_blockers"]) == 9
    assert result.details["publication_blockers"][-1] == "COUNTEREVIDENCE_NOT_RUN"
    assert result.assertions["not_run_is_not_treated_as_no_counterevidence"] is True


def test_non_domain_counterevidence_status_is_rejected() -> None:
    project_root = Path(__file__).resolve().parents[2]
    payload = json.loads(
        (project_root / "evals" / "golden" / "evidence_to_claim.json").read_text(encoding="utf-8")
    )
    payload["cases"][0]["counterevidence_status"] = "SUCCEEDED"

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)
