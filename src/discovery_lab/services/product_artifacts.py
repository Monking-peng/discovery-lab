from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from discovery_lab.api.errors import AppError, ConflictError, NotFoundError
from discovery_lab.db.models import (
    Claim,
    ClaimReview,
    ClaimRevision,
    ContextManifest,
    Experiment,
    Hypothesis,
    PrdArtifact,
    ProductDecision,
    Run,
    Study,
    ToolApproval,
    ToolCall,
)
from discovery_lab.domain.enums import ReviewDecision, ToolApprovalDecision, ToolCallStatus
from discovery_lab.domain.product_artifact_schemas import (
    ApprovedExperimentDraftInput,
    ExperimentRead,
    HypothesisRead,
    PrdArtifactCreate,
    PrdArtifactRead,
    PrdSectionRead,
    ProductArtifactBundleRead,
    ProductArtifactChainRead,
    ProductDecisionCreate,
    ProductDecisionRead,
)
from discovery_lab.services.hashing import canonical_json_hash

PRD_PUBLICATION_BLOCKERS = [
    "PRD_REQUIRES_FINAL_REVIEW",
    "EXTERNAL_PUBLICATION_NOT_IMPLEMENTED",
]


class ProductArtifactService:
    """Application service for the immutable hypothesis-to-PRD product chain."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_experiment_draft(
        self,
        *,
        run_id: UUID,
        tool_call_id: UUID,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist the exact approved write-tool arguments without committing the unit of work."""

        existing = self.session.scalar(
            select(Experiment).where(Experiment.tool_call_id == tool_call_id)
        )
        if existing is not None:
            hypothesis = self.session.get(Hypothesis, existing.hypothesis_id)
            if hypothesis is None:
                raise RuntimeError("Experiment points to a missing Hypothesis")
            expected_hash = canonical_json_hash(arguments)
            if existing.provenance.get("arguments_hash") != expected_hash:
                raise ConflictError(
                    "Tool Call already produced an Experiment from different arguments",
                    details={"reason": "immutable_tool_result_mismatch"},
                )
            return self._tool_result(hypothesis, existing)

        run = self.session.get(Run, run_id)
        tool_call = self.session.get(ToolCall, tool_call_id)
        if run is None:
            raise NotFoundError("agent_run", run_id)
        if tool_call is None:
            raise NotFoundError("tool_call", tool_call_id)
        if tool_call.run_id != run.id or tool_call.tool_name != "create_experiment_draft":
            raise ConflictError("Tool Call is not the approved experiment action for this Run")
        if (
            tool_call.access_mode != "write"
            or tool_call.status != ToolCallStatus.APPROVAL_REQUIRED.value
            or tool_call.arguments_hash != canonical_json_hash(arguments)
            or tool_call.arguments != arguments
        ):
            raise ConflictError(
                "Experiment creation requires the immutable Tool Call arguments",
                details={"reason": "tool_argument_contract_mismatch"},
            )

        approval = tool_call.approval
        if approval is None:
            approval = self.session.scalar(
                select(ToolApproval).where(ToolApproval.tool_call_id == tool_call.id)
            )
        if (
            approval is None
            or approval.decision != ToolApprovalDecision.APPROVE.value
            or approval.arguments_hash != tool_call.arguments_hash
        ):
            raise ConflictError("Experiment creation requires approval of the exact argument hash")
        # Test and worker sessions may intentionally disable autoflush. Flush the
        # approval identity before freezing it into downstream provenance.
        self.session.flush()

        try:
            approved = ApprovedExperimentDraftInput.model_validate(arguments)
        except ValidationError as exc:
            raise AppError(
                code="invalid_tool_arguments",
                message="Approved experiment arguments do not match the tool contract",
                status_code=422,
                details={"issues": exc.errors(include_url=False)},
            ) from exc

        claim_id = UUID(str(run.input_snapshot.get("claim_id")))
        claim_revision_id = UUID(str(run.input_snapshot.get("claim_revision_id")))
        context_manifest_id = UUID(str(run.output_summary.get("context_manifest_id")))
        if (
            approved.claim_revision_id != claim_revision_id
            or approved.hypothesis.claim_revision_id != claim_revision_id
            or approved.context_manifest_id != context_manifest_id
            or approved.hypothesis.context_manifest_id != context_manifest_id
        ):
            raise ConflictError(
                "Approved tool arguments do not match the Run's frozen claim and context",
                details={"reason": "revision_pin_mismatch"},
            )

        claim = self.session.get(Claim, claim_id)
        claim_revision = self.session.get(ClaimRevision, claim_revision_id)
        manifest = self.session.get(ContextManifest, context_manifest_id)
        if (
            claim is None
            or claim_revision is None
            or manifest is None
            or claim.study_id != run.study_id
            or claim_revision.claim_id != claim.id
            or manifest.study_id != run.study_id
        ):
            raise ConflictError("Run provenance no longer resolves inside one Study")

        review = self._claim_review_for_run(run, claim_revision)
        now = datetime.now(UTC)
        shared_provenance = {
            "schema_version": "approved-product-artifact.v1",
            "source": "approved_agent_tool_call",
            "agent_run_id": str(run.id),
            "agent_run_input_hash": run.input_hash,
            "workflow_name": run.workflow_name,
            "workflow_version": run.workflow_version,
            "tool_call_id": str(tool_call.id),
            "tool_version": tool_call.tool_version,
            "arguments_hash": tool_call.arguments_hash,
            "approval": {
                "id": str(approval.id),
                "decision": approval.decision,
                "reviewer": approval.reviewer,
                "arguments_hash": approval.arguments_hash,
                "created_at": approval.created_at.isoformat(),
            },
            "claim_review": {
                "id": str(review.id),
                "decision": review.decision,
                "reviewer": review.reviewer,
                "created_at": review.created_at.isoformat(),
            },
            "context_manifest_hash": manifest.content_hash,
            "external_system_written": False,
        }
        hypothesis_content = {
            "study_id": str(run.study_id),
            "run_id": str(run.id),
            "claim_id": str(claim.id),
            "claim_revision_id": str(claim_revision.id),
            "context_manifest_id": str(manifest.id),
            "status": "DRAFT",
            "statement": approved.hypothesis.statement,
            "expected_outcome": approved.hypothesis.expected_outcome,
            "falsification_criterion": approved.hypothesis.falsification_criterion,
            "provenance": shared_provenance,
        }
        hypothesis = Hypothesis(
            study_id=run.study_id,
            run_id=run.id,
            claim_id=claim.id,
            claim_revision_id=claim_revision.id,
            context_manifest_id=manifest.id,
            status="DRAFT",
            statement=approved.hypothesis.statement,
            expected_outcome=approved.hypothesis.expected_outcome,
            falsification_criterion=approved.hypothesis.falsification_criterion,
            provenance=shared_provenance,
            content_hash=canonical_json_hash(hypothesis_content),
            created_at=now,
        )
        self.session.add(hypothesis)
        self.session.flush()

        experiment_provenance = {
            **shared_provenance,
            "hypothesis_id": str(hypothesis.id),
            "hypothesis_content_hash": hypothesis.content_hash,
        }
        experiment_content = {
            "study_id": str(run.study_id),
            "hypothesis_id": str(hypothesis.id),
            "tool_call_id": str(tool_call.id),
            "status": "DRAFT",
            "title": approved.title,
            "target_cohort": approved.target_cohort,
            "primary_metric": approved.primary_metric,
            "success_threshold": approved.success_threshold,
            "provenance": experiment_provenance,
        }
        experiment = Experiment(
            study_id=run.study_id,
            hypothesis_id=hypothesis.id,
            tool_call_id=tool_call.id,
            status="DRAFT",
            title=approved.title,
            target_cohort=approved.target_cohort,
            primary_metric=approved.primary_metric,
            success_threshold=approved.success_threshold,
            provenance=experiment_provenance,
            content_hash=canonical_json_hash(experiment_content),
            created_at=now,
        )
        self.session.add(experiment)
        self.session.flush()
        return self._tool_result(hypothesis, experiment)

    def create_decision(
        self,
        experiment_id: UUID,
        payload: ProductDecisionCreate,
    ) -> ProductDecision:
        request_hash = canonical_json_hash(
            {
                "operation": "create_product_decision",
                "experiment_id": str(experiment_id),
                "payload": payload.model_dump(mode="json"),
            }
        )
        existing = self.session.scalar(
            select(ProductDecision).where(
                ProductDecision.client_request_id == payload.client_request_id
            )
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            if existing.experiment_id != experiment_id:
                raise ConflictError(
                    "client_request_id belongs to another Experiment",
                    details={"reason": "idempotency_key_reuse"},
                )
            return existing

        experiment = self.session.get(Experiment, experiment_id)
        if experiment is None:
            raise NotFoundError("experiment", experiment_id)
        content = payload.model_dump(mode="json", exclude={"client_request_id"})
        decision = ProductDecision(
            study_id=experiment.study_id,
            experiment_id=experiment.id,
            decision=payload.decision,
            observed_result=payload.observed_result,
            rationale=payload.rationale,
            decided_by=payload.decided_by,
            content_hash=canonical_json_hash({"experiment_id": str(experiment.id), **content}),
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=datetime.now(UTC),
        )
        self.session.add(decision)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(ProductDecision).where(
                    ProductDecision.client_request_id == payload.client_request_id
                )
            )
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return concurrent
        self.session.refresh(decision)
        return decision

    def create_prd(
        self,
        decision_id: UUID,
        payload: PrdArtifactCreate,
    ) -> PrdArtifact:
        request_hash = canonical_json_hash(
            {
                "operation": "create_prd_artifact",
                "decision_id": str(decision_id),
                "payload": payload.model_dump(mode="json"),
            }
        )
        existing = self.session.scalar(
            select(PrdArtifact).where(PrdArtifact.client_request_id == payload.client_request_id)
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            if existing.decision_id != decision_id:
                raise ConflictError(
                    "client_request_id belongs to another Product Decision",
                    details={"reason": "idempotency_key_reuse"},
                )
            return existing

        decision = self.session.get(ProductDecision, decision_id)
        if decision is None:
            raise NotFoundError("product_decision", decision_id)
        experiment = self.session.get(Experiment, decision.experiment_id)
        if experiment is None:
            raise RuntimeError("Product Decision points to a missing Experiment")
        hypothesis = self.session.get(Hypothesis, experiment.hypothesis_id)
        if hypothesis is None:
            raise RuntimeError("Experiment points to a missing Hypothesis")
        claim = self.session.get(Claim, hypothesis.claim_id)
        claim_revision = self.session.get(ClaimRevision, hypothesis.claim_revision_id)
        if claim is None or claim_revision is None:
            raise RuntimeError("Hypothesis points to missing Claim provenance")
        manifest = self.session.scalar(
            select(ContextManifest)
            .options(selectinload(ContextManifest.items))
            .where(ContextManifest.id == hypothesis.context_manifest_id)
        )
        if manifest is None:
            raise RuntimeError("Hypothesis points to a missing Context Manifest")

        citations = self._build_citations(
            hypothesis=hypothesis,
            claim=claim,
            claim_revision=claim_revision,
            manifest=manifest,
        )
        sections = self._build_prd_sections(
            claim_revision=claim_revision,
            hypothesis=hypothesis,
            experiment=experiment,
            decision=decision,
            citations=citations,
        )
        immutable_content = {
            "study_id": str(decision.study_id),
            "decision_id": str(decision.id),
            "title": payload.title,
            "status": "DRAFT",
            "sections": sections,
            "citations": citations,
            "publication_blockers": PRD_PUBLICATION_BLOCKERS,
        }
        prd = PrdArtifact(
            study_id=decision.study_id,
            decision_id=decision.id,
            title=payload.title,
            status="DRAFT",
            sections=sections,
            citations=citations,
            publication_blockers=PRD_PUBLICATION_BLOCKERS,
            content_hash=canonical_json_hash(immutable_content),
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=datetime.now(UTC),
        )
        self.session.add(prd)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(PrdArtifact).where(
                    PrdArtifact.client_request_id == payload.client_request_id
                )
            )
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return concurrent
        self.session.refresh(prd)
        return prd

    def get_prd(self, prd_id: UUID) -> PrdArtifact:
        prd = self.session.get(PrdArtifact, prd_id)
        if prd is None:
            raise NotFoundError("prd", prd_id)
        return prd

    def list_product_artifacts(self, study_id: UUID) -> ProductArtifactBundleRead:
        if self.session.get(Study, study_id) is None:
            raise NotFoundError("study", study_id)
        experiments = list(
            self.session.scalars(
                select(Experiment)
                .where(Experiment.study_id == study_id)
                .order_by(Experiment.created_at.desc(), Experiment.id.desc())
            )
        )
        if not experiments:
            return ProductArtifactBundleRead(
                study_id=study_id,
                total_experiments=0,
                items=[],
            )

        hypothesis_ids = [item.hypothesis_id for item in experiments]
        hypotheses = {
            item.id: item
            for item in self.session.scalars(
                select(Hypothesis).where(Hypothesis.id.in_(hypothesis_ids))
            )
        }
        experiment_ids = [item.id for item in experiments]
        decisions = list(
            self.session.scalars(
                select(ProductDecision)
                .where(ProductDecision.experiment_id.in_(experiment_ids))
                .order_by(ProductDecision.created_at.desc(), ProductDecision.id.desc())
            )
        )
        decision_ids = [item.id for item in decisions]
        prds = (
            list(
                self.session.scalars(
                    select(PrdArtifact)
                    .where(PrdArtifact.decision_id.in_(decision_ids))
                    .order_by(PrdArtifact.created_at.desc(), PrdArtifact.id.desc())
                )
            )
            if decision_ids
            else []
        )
        return ProductArtifactBundleRead(
            study_id=study_id,
            total_experiments=len(experiments),
            items=[
                ProductArtifactChainRead(
                    hypothesis=hypothesis_response(hypotheses[experiment.hypothesis_id]),
                    experiment=experiment_response(experiment),
                    decisions=[
                        decision_response(item)
                        for item in decisions
                        if item.experiment_id == experiment.id
                    ],
                    prds=[
                        prd_response(prd)
                        for prd in prds
                        if any(
                            decision.id == prd.decision_id
                            and decision.experiment_id == experiment.id
                            for decision in decisions
                        )
                    ],
                )
                for experiment in experiments
            ],
        )

    def _claim_review_for_run(
        self,
        run: Run,
        claim_revision: ClaimRevision,
    ) -> ClaimReview:
        review_id_raw = run.input_snapshot.get("claim_review_id")
        review = (
            self.session.get(ClaimReview, UUID(str(review_id_raw)))
            if review_id_raw is not None
            else None
        )
        if review is None:
            review = self.session.scalar(
                select(ClaimReview)
                .where(
                    ClaimReview.claim_revision_id == claim_revision.id,
                    ClaimReview.decision == ReviewDecision.ACCEPT.value,
                )
                .order_by(ClaimReview.created_at.desc(), ClaimReview.id.desc())
                .limit(1)
            )
        if (
            review is None
            or review.claim_revision_id != claim_revision.id
            or review.decision != ReviewDecision.ACCEPT.value
        ):
            raise ConflictError("Run is missing its exact accepted Claim Review")
        return review

    @staticmethod
    def _tool_result(hypothesis: Hypothesis, experiment: Experiment) -> dict[str, Any]:
        return {
            "artifact_type": "experiment_draft",
            "artifact_id": str(experiment.id),
            "hypothesis_id": str(hypothesis.id),
            "experiment_id": str(experiment.id),
            "status": "DRAFT",
            "external_system_written": False,
            "persistence": "immutable_hypothesis_and_experiment",
            "product_artifact_url": f"/v1/studies/{experiment.study_id}/product-artifacts",
        }

    @staticmethod
    def _build_citations(
        *,
        hypothesis: Hypothesis,
        claim: Claim,
        claim_revision: ClaimRevision,
        manifest: ContextManifest,
    ) -> list[dict[str, Any]]:
        review_snapshot = hypothesis.provenance.get("claim_review")
        if not isinstance(review_snapshot, dict):
            raise RuntimeError("Hypothesis is missing its frozen Claim Review snapshot")
        if review_snapshot.get("decision") != ReviewDecision.ACCEPT.value:
            raise RuntimeError("Hypothesis Claim Review snapshot is not accepted")
        claim_citation = {
            "kind": "claim_revision",
            "citation_id": f"claim-revision:{claim_revision.id}",
            "claim_id": str(claim.id),
            "revision_id": str(claim_revision.id),
            "revision": claim_revision.revision,
            "statement": claim_revision.statement,
            "summary": claim_revision.summary,
            "content_hash": claim_revision.content_hash,
            "review_id": str(review_snapshot["id"]),
            "review_decision": review_snapshot["decision"],
            "review_reviewer": str(review_snapshot["reviewer"]),
            "context_url": (f"/v1/claims/{claim.id}?claim_revision_id={claim_revision.id}"),
        }
        evidence_citations = []
        for item in sorted(manifest.items, key=lambda value: value.ordinal):
            if item.review_snapshot.get("decision") != ReviewDecision.ACCEPT.value:
                raise RuntimeError("Context Manifest contains non-accepted Evidence")
            evidence_citations.append(
                {
                    "kind": "evidence_revision",
                    "citation_id": f"evidence-revision:{item.evidence_revision_id}",
                    "evidence_id": str(item.evidence_unit_id),
                    "revision_id": str(item.evidence_revision_id),
                    "source_id": str(item.source_id),
                    "source_revision_id": str(item.source_revision_id),
                    "evidence_review_id": str(item.evidence_review_id),
                    "review_decision": item.review_snapshot["decision"],
                    "review_reviewer": str(item.review_snapshot["reviewer"]),
                    "evidence_content_hash": item.evidence_content_hash,
                    "source_content_hash": item.source_content_hash,
                    "source_name": item.source_name,
                    "quote": str(item.evidence_snapshot["quote"]),
                    "observation": item.evidence_snapshot.get("observation"),
                    "locator": dict(item.evidence_snapshot["locator"]),
                    "context_url": item.context_url,
                }
            )
        return [claim_citation, *evidence_citations]

    @staticmethod
    def _build_prd_sections(
        *,
        claim_revision: ClaimRevision,
        hypothesis: Hypothesis,
        experiment: Experiment,
        decision: ProductDecision,
        citations: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        claim_ref = str(citations[0]["citation_id"])
        evidence_refs = [
            str(item["citation_id"]) for item in citations if item["kind"] == "evidence_revision"
        ]
        evidence_observations = [
            str(item.get("observation") or item["quote"])
            for item in citations
            if item["kind"] == "evidence_revision"
        ]
        rollout = {
            "PROCEED": "Run a bounded pilot, keep human confirmation, then review the metric.",
            "ITERATE": "Revise the experiment design and repeat the bounded validation cycle.",
            "STOP": "Do not roll out; retain the decision and evidence trail for audit.",
        }[decision.decision]
        return {
            "problem": {
                "body": claim_revision.statement,
                "citation_refs": [claim_ref],
            },
            "evidence_summary": {
                "body": " ".join(evidence_observations),
                "citation_refs": evidence_refs,
            },
            "hypothesis": {
                "body": (f"{hypothesis.statement} Expected outcome: {hypothesis.expected_outcome}"),
                "citation_refs": [claim_ref, *evidence_refs],
            },
            "experiment": {
                "body": (
                    f"{experiment.title}. Cohort: {experiment.target_cohort}. "
                    f"Primary metric: {experiment.primary_metric}. Success threshold: "
                    f"{experiment.success_threshold}."
                ),
                "citation_refs": [claim_ref, *evidence_refs],
            },
            "decision": {
                "body": (
                    f"{decision.decision}: {decision.observed_result} "
                    f"Rationale: {decision.rationale}"
                ),
                "citation_refs": [claim_ref, *evidence_refs],
            },
            "scope": {
                "body": (f"A bounded, human-confirmed workflow for {experiment.target_cohort}."),
                "citation_refs": [claim_ref],
            },
            "non_goals": {
                "body": (
                    "No autonomous external publication, irreversible action, or removal of "
                    "human decision authority."
                ),
                "citation_refs": [],
            },
            "success_metrics": {
                "body": (
                    f"Measure {experiment.primary_metric}; pass at "
                    f"{experiment.success_threshold}. Falsify when: "
                    f"{hypothesis.falsification_criterion}"
                ),
                "citation_refs": [claim_ref, *evidence_refs],
            },
            "risks_and_guardrails": {
                "body": (
                    "Require human confirmation, preserve exact argument hashes, monitor "
                    "false positives, and keep source content isolated as untrusted data."
                ),
                "citation_refs": evidence_refs,
            },
            "rollout": {
                "body": rollout,
                "citation_refs": [claim_ref, *evidence_refs],
            },
        }

    @staticmethod
    def _assert_idempotent(stored_hash: str, request_hash: str) -> None:
        if stored_hash != request_hash:
            raise ConflictError(
                "client_request_id was already used with a different payload",
                details={"reason": "idempotency_key_reuse"},
            )


def hypothesis_response(hypothesis: Hypothesis) -> HypothesisRead:
    return HypothesisRead(
        id=hypothesis.id,
        study_id=hypothesis.study_id,
        run_id=hypothesis.run_id,
        claim_id=hypothesis.claim_id,
        claim_revision_id=hypothesis.claim_revision_id,
        context_manifest_id=hypothesis.context_manifest_id,
        status="DRAFT",
        statement=hypothesis.statement,
        expected_outcome=hypothesis.expected_outcome,
        falsification_criterion=hypothesis.falsification_criterion,
        provenance=hypothesis.provenance,
        content_hash=hypothesis.content_hash,
        created_at=hypothesis.created_at,
    )


def experiment_response(experiment: Experiment) -> ExperimentRead:
    return ExperimentRead(
        id=experiment.id,
        study_id=experiment.study_id,
        hypothesis_id=experiment.hypothesis_id,
        tool_call_id=experiment.tool_call_id,
        status="DRAFT",
        title=experiment.title,
        target_cohort=experiment.target_cohort,
        primary_metric=experiment.primary_metric,
        success_threshold=experiment.success_threshold,
        provenance=experiment.provenance,
        content_hash=experiment.content_hash,
        created_at=experiment.created_at,
    )


def decision_response(decision: ProductDecision) -> ProductDecisionRead:
    return ProductDecisionRead(
        id=decision.id,
        study_id=decision.study_id,
        experiment_id=decision.experiment_id,
        decision=cast(Literal["PROCEED", "ITERATE", "STOP"], decision.decision),
        observed_result=decision.observed_result,
        rationale=decision.rationale,
        decided_by=decision.decided_by,
        content_hash=decision.content_hash,
        client_request_id=decision.client_request_id,
        created_at=decision.created_at,
    )


def prd_response(prd: PrdArtifact) -> PrdArtifactRead:
    return PrdArtifactRead.model_validate(
        {
            "id": prd.id,
            "study_id": prd.study_id,
            "decision_id": prd.decision_id,
            "title": prd.title,
            "status": "DRAFT",
            "publishable": False,
            "sections": {
                key: PrdSectionRead.model_validate(value) for key, value in prd.sections.items()
            },
            "citations": prd.citations,
            "publication_blockers": prd.publication_blockers,
            "content_hash": prd.content_hash,
            "client_request_id": prd.client_request_id,
            "created_at": prd.created_at,
        }
    )
