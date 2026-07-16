from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Never
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from discovery_lab.domain.enums import (
    ClaimEvidenceRelation,
    CounterevidenceStatus,
    ReviewDecision,
)
from discovery_lab.domain.integrity import (
    CLAIM_INTEGRITY_BLOCKER_ORDER,
    ClaimIntegrityBlocker,
)

AssessmentScope = Literal["claim_review", "historical_replay"]
CounterevidenceInterpretation = Literal[
    "not_evaluated", "searched_none_found", "counterevidence_found"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceEdgeInput(StrictModel):
    relationship: ClaimEvidenceRelation
    relation_confirmed: bool
    evidence_id: UUID
    requested_evidence_revision_id: UUID
    resolved_evidence_revision_id: UUID
    latest_evidence_revision_id: UUID
    evidence_study_id: UUID
    latest_review_decision: ReviewDecision | None
    synthetic_demo: bool
    citation_integrity_passed: bool
    locator_replayable: bool
    source_hash_match: bool


class ExpectedOutcome(StrictModel):
    eligible_for_claim_review: bool
    review_blockers: tuple[ClaimIntegrityBlocker, ...]
    publication_blockers: tuple[ClaimIntegrityBlocker, ...]


class GoldenCase(StrictModel):
    id: str = Field(min_length=1)
    claim_study_id: UUID
    assessment_scope: AssessmentScope = "claim_review"
    counterevidence_status: CounterevidenceStatus
    evidence_edges: tuple[EvidenceEdgeInput, ...]
    requires_exact_revision_replay: bool = False
    expected: ExpectedOutcome

    @model_validator(mode="after")
    def validate_replay_contract(self) -> GoldenCase:
        if self.requires_exact_revision_replay and self.assessment_scope != "historical_replay":
            raise ValueError("exact revision replay cases must use historical_replay scope")
        return self


class GoldenDataset(StrictModel):
    schema_version: Literal["evidence-to-claim-dataset.v2"]
    dataset: str = Field(min_length=1)
    revision: int = Field(gt=0)
    cases: tuple[GoldenCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> GoldenDataset:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evaluation case ids must be unique")
        return self


class ClaimIntegrityAssessment(StrictModel):
    eligible_for_claim_review: bool
    review_blockers: tuple[ClaimIntegrityBlocker, ...]
    publication_blockers: tuple[ClaimIntegrityBlocker, ...]
    counterevidence_interpretation: CounterevidenceInterpretation
    exact_revision_replay: bool
    old_revision_identity_preserved: bool


class EvaluationCaseResult(StrictModel):
    case_id: str
    status: Literal["passed", "failed"]
    assertions: dict[str, bool] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationSummary(StrictModel):
    case_count: int = Field(ge=1)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    claim_review_eligibility_accuracy: float = Field(ge=0.0, le=1.0)
    blocker_contract_accuracy: float = Field(ge=0.0, le=1.0)
    publication_safety_rate: float = Field(ge=0.0, le=1.0)
    counterevidence_not_run_block_rate: float = Field(ge=0.0, le=1.0)
    exact_old_revision_replay_rate: float = Field(ge=0.0, le=1.0)


class EvaluationReport(StrictModel):
    schema_version: Literal["evidence-to-claim-eval.v2"] = "evidence-to-claim-eval.v2"
    dataset: str
    dataset_revision: int
    policy_profile: dict[str, str]
    generated_at: datetime
    summary: EvaluationSummary
    cases: tuple[EvaluationCaseResult, ...]


def _ordered_blockers(
    values: set[ClaimIntegrityBlocker],
) -> tuple[ClaimIntegrityBlocker, ...]:
    return tuple(blocker for blocker in CLAIM_INTEGRITY_BLOCKER_ORDER if blocker in values)


def _counterevidence_interpretation(
    status: CounterevidenceStatus,
) -> CounterevidenceInterpretation:
    if status == CounterevidenceStatus.NOT_RUN:
        return "not_evaluated"
    if status == CounterevidenceStatus.SEARCHED_NONE_FOUND:
        return "searched_none_found"
    if status == CounterevidenceStatus.FOUND:
        return "counterevidence_found"
    return _unreachable(status)


def _unreachable(value: object) -> Never:
    raise AssertionError(f"unhandled domain value: {value!r}")


def assess_claim_integrity(case: GoldenCase) -> ClaimIntegrityAssessment:
    """Apply the deterministic candidate promotion and publication boundary.

    The inputs mirror the persisted workflow: the latest append-only review is a
    ``ReviewDecision`` and counterevidence uses the domain's three real states.
    Historical replay checks identity without pretending an old revision is the
    current revision for a new Claim promotion.
    """

    review_blockers: set[ClaimIntegrityBlocker] = set()
    formal_edges = [
        edge
        for edge in case.evidence_edges
        if edge.relationship in (ClaimEvidenceRelation.SUPPORTS, ClaimEvidenceRelation.CONTRADICTS)
    ]
    confirmed_supports = [
        edge
        for edge in formal_edges
        if edge.relationship == ClaimEvidenceRelation.SUPPORTS and edge.relation_confirmed
    ]
    if not confirmed_supports:
        review_blockers.add(ClaimIntegrityBlocker.NO_CONFIRMED_SUPPORT)

    for edge in formal_edges:
        if not edge.relation_confirmed:
            review_blockers.add(ClaimIntegrityBlocker.FORMAL_RELATION_NOT_CONFIRMED)
        if edge.latest_review_decision != ReviewDecision.ACCEPT:
            review_blockers.add(ClaimIntegrityBlocker.EVIDENCE_REVIEW_NOT_ACCEPTED)
        if edge.synthetic_demo:
            review_blockers.add(ClaimIntegrityBlocker.SYNTHETIC_EVIDENCE)
        if edge.evidence_study_id != case.claim_study_id:
            review_blockers.add(ClaimIntegrityBlocker.CROSS_STUDY_EVIDENCE)
        if edge.requested_evidence_revision_id != edge.resolved_evidence_revision_id:
            review_blockers.add(ClaimIntegrityBlocker.EVIDENCE_REVISION_MISMATCH)
        elif (
            case.assessment_scope == "claim_review"
            and edge.requested_evidence_revision_id != edge.latest_evidence_revision_id
        ):
            review_blockers.add(ClaimIntegrityBlocker.NOT_CURRENT_EVIDENCE_REVISION)
        if not edge.citation_integrity_passed:
            review_blockers.add(ClaimIntegrityBlocker.CITATION_INTEGRITY_FAILED)
        if not edge.locator_replayable:
            review_blockers.add(ClaimIntegrityBlocker.LOCATOR_REPLAY_FAILED)
        if not edge.source_hash_match:
            review_blockers.add(ClaimIntegrityBlocker.SOURCE_HASH_MISMATCH)

    stable_review_blockers = _ordered_blockers(review_blockers)
    publication_blockers = set(review_blockers)
    if case.counterevidence_status == CounterevidenceStatus.NOT_RUN:
        publication_blockers.add(ClaimIntegrityBlocker.COUNTEREVIDENCE_NOT_RUN)

    exact_revision_replay = all(
        edge.requested_evidence_revision_id == edge.resolved_evidence_revision_id
        for edge in formal_edges
    )
    old_revision_identity_preserved = bool(formal_edges) and all(
        edge.requested_evidence_revision_id == edge.resolved_evidence_revision_id
        and edge.requested_evidence_revision_id != edge.latest_evidence_revision_id
        for edge in formal_edges
    )
    return ClaimIntegrityAssessment(
        eligible_for_claim_review=not stable_review_blockers,
        review_blockers=stable_review_blockers,
        publication_blockers=_ordered_blockers(publication_blockers),
        counterevidence_interpretation=_counterevidence_interpretation(case.counterevidence_status),
        exact_revision_replay=exact_revision_replay,
        old_revision_identity_preserved=old_revision_identity_preserved,
    )


def _evaluate_case(case: GoldenCase) -> EvaluationCaseResult:
    assessment = assess_claim_integrity(case)
    assertions = {
        "claim_review_eligibility_matches": (
            assessment.eligible_for_claim_review == case.expected.eligible_for_claim_review
        ),
        "review_blockers_match": assessment.review_blockers == case.expected.review_blockers,
        "publication_blockers_match": (
            assessment.publication_blockers == case.expected.publication_blockers
        ),
    }
    if case.counterevidence_status == CounterevidenceStatus.NOT_RUN:
        assertions["not_run_is_not_treated_as_no_counterevidence"] = (
            assessment.counterevidence_interpretation == "not_evaluated"
            and ClaimIntegrityBlocker.COUNTEREVIDENCE_NOT_RUN in assessment.publication_blockers
        )
    if case.requires_exact_revision_replay:
        assertions["requested_revision_replayed_exactly"] = assessment.exact_revision_replay
        assertions["old_revision_not_substituted_by_latest"] = (
            assessment.old_revision_identity_preserved
        )

    return EvaluationCaseResult(
        case_id=case.id,
        status="passed" if all(assertions.values()) else "failed",
        assertions=assertions,
        details={
            "eligible_for_claim_review": assessment.eligible_for_claim_review,
            "review_blockers": list(assessment.review_blockers),
            "publication_blockers": list(assessment.publication_blockers),
            "counterevidence_interpretation": assessment.counterevidence_interpretation,
            "exact_revision_replay": assessment.exact_revision_replay,
            "old_revision_identity_preserved": assessment.old_revision_identity_preserved,
        },
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def run_evaluation(dataset_path: Path) -> EvaluationReport:
    dataset_path = dataset_path.resolve()
    dataset = GoldenDataset.model_validate_json(dataset_path.read_text(encoding="utf-8"))
    case_results = tuple(_evaluate_case(case) for case in dataset.cases)
    total = len(dataset.cases)

    eligibility_matches = sum(
        result.assertions["claim_review_eligibility_matches"] for result in case_results
    )
    blocker_contract_matches = sum(
        result.assertions["review_blockers_match"]
        and result.assertions["publication_blockers_match"]
        for result in case_results
    )
    publication_matches = sum(
        result.assertions["publication_blockers_match"] for result in case_results
    )
    not_run_results = [
        result
        for case, result in zip(dataset.cases, case_results, strict=True)
        if case.counterevidence_status == CounterevidenceStatus.NOT_RUN
    ]
    exact_replay_results = [
        result
        for case, result in zip(dataset.cases, case_results, strict=True)
        if case.requires_exact_revision_replay
    ]
    return EvaluationReport(
        dataset=dataset.dataset,
        dataset_revision=dataset.revision,
        policy_profile={
            "name": "evidence-to-claim-integrity",
            "version": "2",
            "review_semantics": "latest_append_only_review_decision",
            "counterevidence_semantics": "domain_counterevidence_status",
            "counterevidence_not_run_semantics": "publication_blocker",
            "revision_binding": "exact_identity",
        },
        generated_at=datetime.now(UTC),
        summary=EvaluationSummary(
            case_count=total,
            passed=sum(result.status == "passed" for result in case_results),
            failed=sum(result.status == "failed" for result in case_results),
            claim_review_eligibility_accuracy=_rate(eligibility_matches, total),
            blocker_contract_accuracy=_rate(blocker_contract_matches, total),
            publication_safety_rate=_rate(publication_matches, total),
            counterevidence_not_run_block_rate=_rate(
                sum(
                    result.assertions["not_run_is_not_treated_as_no_counterevidence"]
                    for result in not_run_results
                ),
                len(not_run_results),
            ),
            exact_old_revision_replay_rate=_rate(
                sum(
                    result.assertions["requested_revision_replayed_exactly"]
                    and result.assertions["old_revision_not_substituted_by_latest"]
                    for result in exact_replay_results
                ),
                len(exact_replay_results),
            ),
        ),
        cases=case_results,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Evidence -> Claim golden evaluation")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/golden/evidence_to_claim.json"),
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run_evaluation(arguments.dataset)
    payload = report.model_dump_json(indent=2)
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 1 if report.summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
