from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from discovery_lab.agent_harness.discovery_graph import (
    DiscoveryWorkflowState,
    compile_discovery_graph,
)
from discovery_lab.api.errors import AppError, ConflictError, NotFoundError
from discovery_lab.db.models import (
    Claim,
    ClaimReview,
    ClaimRevision,
    ContextManifest,
    Run,
    RunStep,
    Study,
    ToolApproval,
    ToolCall,
)
from discovery_lab.domain.agent_schemas import (
    AgentRunCreate,
    AgentRunList,
    AgentRunRead,
    ContextManifestReferenceRead,
    ToolApprovalCreate,
    ToolApprovalRead,
    ToolCallRead,
    ToolDefinitionRead,
    ToolRegistryRead,
)
from discovery_lab.domain.enums import (
    ClaimStatus,
    CounterevidenceStatus,
    RetrievalPurpose,
    ReviewDecision,
    RunStatus,
    RunStepStatus,
    ToolApprovalDecision,
    ToolCallStatus,
)
from discovery_lab.domain.retrieval_schemas import RetrievalCreate
from discovery_lab.domain.schemas import RunStepRead
from discovery_lab.services.hashing import canonical_json_hash
from discovery_lab.services.product_artifacts import ProductArtifactService
from discovery_lab.services.retrieval import RetrievalService

WORKFLOW_NAME = "opportunity_discovery"
WORKFLOW_VERSION = "1.0.0"
TOOL_POLICY_VERSION: Literal["tool-policy.v1"] = "tool-policy.v1"

TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "retrieve_reviewed_evidence",
        "version": "1.0.0",
        "description": (
            "Create an immutable hybrid-retrieval Context Manifest over current, accepted, "
            "non-synthetic Evidence Revisions."
        ),
        "access_mode": "read",
        "risk_level": "low",
        "requires_approval": False,
        "server_allowlisted": True,
        "mcp_exposed": True,
        "input_schema": {
            "study_id": "uuid",
            "query": "string",
            "purpose": "support|counterevidence|explore",
            "limit": "integer:1..20",
        },
        "output_schema": {
            "context_manifest_id": "uuid",
            "content_hash": "sha256",
            "item_count": "integer",
        },
    },
    {
        "name": "create_experiment_draft",
        "version": "1.0.0",
        "description": (
            "Persist a bounded experiment draft inside Discovery Lab. It never writes to an "
            "external system and requires approval of the exact argument hash."
        ),
        "access_mode": "write",
        "risk_level": "medium",
        "requires_approval": True,
        "server_allowlisted": True,
        "mcp_exposed": False,
        "input_schema": {
            "title": "string",
            "primary_metric": "string",
            "success_threshold": "string",
            "target_cohort": "string",
            "claim_revision_id": "uuid",
            "context_manifest_id": "uuid",
            "hypothesis": "object",
        },
        "output_schema": {
            "artifact_type": "experiment_draft",
            "status": "DRAFT",
            "external_system_written": False,
        },
    },
)


def tool_registry_response() -> ToolRegistryRead:
    return ToolRegistryRead(
        policy_version=TOOL_POLICY_VERSION,
        items=[ToolDefinitionRead.model_validate(item) for item in TOOL_DEFINITIONS],
    )


def _tool_definition(name: str) -> dict[str, Any]:
    for definition in TOOL_DEFINITIONS:
        if definition["name"] == name:
            return definition
    raise AppError(
        code="tool_not_allowed",
        message="The requested tool is not in the server allowlist",
        status_code=422,
        details={"tool_name": name, "policy_version": TOOL_POLICY_VERSION},
    )


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    run: Run
    manifest: ContextManifest


class _DiscoveryToolAdapter:
    def __init__(
        self,
        *,
        session: Session,
        study_id: UUID,
        run_id: UUID,
        retrieval: RetrievalCreate | None,
        tool_call_id: UUID | None = None,
    ) -> None:
        self.session = session
        self.study_id = study_id
        self.run_id = run_id
        self.retrieval = retrieval
        self.tool_call_id = tool_call_id

    def retrieve_context(
        self,
        _state: DiscoveryWorkflowState,
    ) -> dict[str, Any]:
        if self.retrieval is None:
            raise RuntimeError("resume adapter cannot execute retrieval")
        manifest = RetrievalService(self.session).create_context_manifest(
            self.study_id,
            self.retrieval,
        )
        return {
            "context_manifest_id": str(manifest.id),
            "context_manifest_hash": manifest.content_hash,
            "context_item_count": len(manifest.items),
            "context_items": [
                {
                    "rank": item.ordinal,
                    "evidence_revision_id": str(item.evidence_revision_id),
                    "source_revision_id": str(item.source_revision_id),
                    "observation": item.evidence_snapshot.get("observation"),
                }
                for item in manifest.items
            ],
        }

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        definition = _tool_definition(tool_name)
        if definition["access_mode"] != "write" or tool_name != "create_experiment_draft":
            raise AppError(
                code="tool_execution_forbidden",
                message="The requested write tool cannot be executed by this workflow",
                status_code=409,
            )
        if self.tool_call_id is None:
            raise RuntimeError("write-tool adapter requires the persisted Tool Call identity")
        return ProductArtifactService(self.session).create_experiment_draft(
            run_id=self.run_id,
            tool_call_id=self.tool_call_id,
            arguments=arguments,
        )


class AgentRunService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self, study_id: UUID, payload: AgentRunCreate) -> AgentRunRecord:
        request_hash = canonical_json_hash(
            {
                "operation": "create_agent_run",
                "study_id": str(study_id),
                "payload": payload.model_dump(mode="json"),
            }
        )
        existing = self.session.scalar(
            select(Run).where(Run.client_request_id == payload.client_request_id)
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            if existing.study_id != study_id or existing.workflow_name != WORKFLOW_NAME:
                raise ConflictError(
                    "client_request_id belongs to another Agent Run",
                    details={"reason": "idempotency_key_reuse"},
                )
            return self.get_run(existing.id)

        if self.session.get(Study, study_id) is None:
            raise NotFoundError("study", study_id)
        claim_revision, claim, claim_review = self._reviewed_current_claim(
            study_id,
            payload.claim_revision_id,
        )
        _tool_definition(payload.requested_action.tool_name)

        run_id = uuid4()
        retrieval_payload = RetrievalCreate(
            query=payload.retrieval.query,
            purpose=payload.retrieval.purpose,
            limit=payload.retrieval.limit,
            client_request_id=f"agent:{run_id}:retrieval",
        )
        adapter = _DiscoveryToolAdapter(
            session=self.session,
            study_id=study_id,
            run_id=run_id,
            retrieval=retrieval_payload,
        )
        graph = compile_discovery_graph(port=adapter)
        graph_state = graph.invoke(
            {
                "phase": "start",
                "run_id": str(run_id),
                "goal": payload.goal,
                "claim_revision_id": str(claim_revision.id),
                "claim_statement": claim_revision.statement,
                "retrieval_query": payload.retrieval.query,
                "retrieval_purpose": payload.retrieval.purpose.value,
                "retrieval_limit": payload.retrieval.limit,
                "requested_tool": payload.requested_action.tool_name,
                "requested_tool_arguments": payload.requested_action.arguments.model_dump(
                    mode="json"
                ),
            }
        )
        manifest_id = UUID(str(graph_state["context_manifest_id"]))
        manifest = RetrievalService(self.session).get_context_manifest(manifest_id)
        now = datetime.now(UTC)
        input_snapshot = {
            "schema_version": "agent-run-input.v1",
            "goal": payload.goal,
            "study_id": str(study_id),
            "claim_id": str(claim.id),
            "claim_revision_id": str(claim_revision.id),
            "claim_statement": claim_revision.statement,
            "claim_review_id": str(claim_review.id),
            "claim_review_decision": claim_review.decision,
            "claim_review_reviewer": claim_review.reviewer,
            "retrieval": payload.retrieval.model_dump(mode="json"),
            "requested_action": payload.requested_action.model_dump(mode="json"),
            "client_request_id": payload.client_request_id,
        }
        run = Run(
            id=run_id,
            study_id=study_id,
            source_id=None,
            workflow_name=WORKFLOW_NAME,
            workflow_version=WORKFLOW_VERSION,
            status=RunStatus.RUNNING.value,
            input_snapshot=input_snapshot,
            input_hash=canonical_json_hash(input_snapshot),
            output_summary={},
            error=None,
            started_at=now,
            completed_at=None,
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=now,
        )
        steps = self._new_steps(run, input_snapshot, now)
        self.session.add(run)
        self.session.flush()

        plan_step, retrieval_step, draft_step, approval_step, finalize_step = steps
        plan_step.status = RunStepStatus.SUCCEEDED.value
        plan_step.started_at = now
        plan_step.completed_at = now
        plan_step.output_summary = {
            "plan": graph_state["plan"],
            "prompt_profile": graph_state["prompt_profile"],
        }
        retrieval_step.status = RunStepStatus.SUCCEEDED.value
        retrieval_step.started_at = now
        retrieval_step.completed_at = now
        retrieval_step.output_summary = {
            "context_manifest_id": str(manifest.id),
            "context_manifest_hash": manifest.content_hash,
            "item_count": len(manifest.items),
        }

        read_arguments = {
            "study_id": str(study_id),
            "query": manifest.query,
            "purpose": manifest.purpose,
            "limit": manifest.result_limit,
        }
        read_result = {
            "context_manifest_id": str(manifest.id),
            "content_hash": manifest.content_hash,
            "item_count": len(manifest.items),
            "context_url": f"/v1/context-manifests/{manifest.id}",
        }
        self.session.add(
            ToolCall(
                run_id=run.id,
                run_step_id=retrieval_step.id,
                tool_name="retrieve_reviewed_evidence",
                tool_version="1.0.0",
                access_mode="read",
                risk_level="low",
                status=ToolCallStatus.SUCCEEDED.value,
                arguments=read_arguments,
                arguments_hash=canonical_json_hash(read_arguments),
                result=read_result,
                result_hash=canonical_json_hash(read_result),
                policy_snapshot=self._policy_snapshot("retrieve_reviewed_evidence"),
                requires_approval=False,
                started_at=now,
                completed_at=now,
                created_at=now,
            )
        )

        if not manifest.items:
            draft_step.status = RunStepStatus.FAILED.value
            draft_step.started_at = now
            draft_step.completed_at = now
            draft_step.error = {"code": "insufficient_evidence"}
            approval_step.status = RunStepStatus.SKIPPED.value
            finalize_step.status = RunStepStatus.SKIPPED.value
            run.status = RunStatus.FAILED.value
            run.completed_at = now
            run.error = {
                "code": "insufficient_evidence",
                "message": "No eligible reviewed evidence matched the retrieval query",
            }
            run.output_summary = {
                "phase": "FAILED",
                "execution_prevented": True,
                "context_manifest_id": str(manifest.id),
                "context_manifest_hash": manifest.content_hash,
                "plan": graph_state["plan"],
                "prompt_profile": graph_state["prompt_profile"],
                "hypothesis": {},
            }
        else:
            draft_step.status = RunStepStatus.SUCCEEDED.value
            draft_step.started_at = now
            draft_step.completed_at = now
            draft_step.output_summary = {"hypothesis": graph_state["hypothesis"]}
            approval_step.status = RunStepStatus.WAITING_HUMAN.value
            approval_step.started_at = now
            write_arguments = dict(graph_state["proposed_tool_arguments"])
            write_call = ToolCall(
                run_id=run.id,
                run_step_id=approval_step.id,
                tool_name=str(graph_state["proposed_tool_name"]),
                tool_version="1.0.0",
                access_mode="write",
                risk_level="medium",
                status=ToolCallStatus.APPROVAL_REQUIRED.value,
                arguments=write_arguments,
                arguments_hash=canonical_json_hash(write_arguments),
                result=None,
                result_hash=None,
                policy_snapshot=self._policy_snapshot(str(graph_state["proposed_tool_name"])),
                requires_approval=True,
                started_at=now,
                completed_at=None,
                created_at=now,
            )
            self.session.add(write_call)
            self.session.flush()
            approval_step.output_summary = {
                "tool_call_id": str(write_call.id),
                "arguments_hash": write_call.arguments_hash,
                "policy": "exact_arguments_require_human_approval",
            }
            run.output_summary = {
                "phase": "WAITING_HUMAN",
                "execution_prevented": True,
                "context_manifest_id": str(manifest.id),
                "context_manifest_hash": manifest.content_hash,
                "plan": graph_state["plan"],
                "prompt_profile": graph_state["prompt_profile"],
                "hypothesis": graph_state["hypothesis"],
                "pending_tool_call_id": str(write_call.id),
            }

        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(Run).where(Run.client_request_id == payload.client_request_id)
            )
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return self.get_run(concurrent.id)
        return self.get_run(run.id)

    def approve_tool_call(
        self,
        tool_call_id: UUID,
        payload: ToolApprovalCreate,
    ) -> AgentRunRecord:
        request_hash = canonical_json_hash(
            {
                "operation": "approve_tool_call",
                "tool_call_id": str(tool_call_id),
                "payload": payload.model_dump(mode="json"),
            }
        )
        existing = self.session.scalar(
            select(ToolApproval).where(ToolApproval.client_request_id == payload.client_request_id)
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            if existing.tool_call_id != tool_call_id:
                raise ConflictError(
                    "client_request_id belongs to another Tool Call",
                    details={"reason": "idempotency_key_reuse"},
                )
            existing_call = self.session.get(ToolCall, existing.tool_call_id)
            if existing_call is None:
                raise RuntimeError("Tool Approval points to a missing Tool Call")
            return self.get_run(existing_call.run_id)

        tool_call = self.session.scalar(
            select(ToolCall)
            .options(selectinload(ToolCall.approval))
            .where(ToolCall.id == tool_call_id)
        )
        if tool_call is None:
            raise NotFoundError("tool_call", tool_call_id)
        if not tool_call.requires_approval or tool_call.access_mode != "write":
            raise ConflictError("This Tool Call does not accept a human approval")
        if tool_call.status != ToolCallStatus.APPROVAL_REQUIRED.value or tool_call.approval:
            raise ConflictError("This Tool Call is no longer waiting for approval")
        if payload.arguments_hash != tool_call.arguments_hash:
            raise ConflictError(
                "Approval arguments_hash does not match the immutable Tool Call",
                details={
                    "expected_arguments_hash": tool_call.arguments_hash,
                    "provided_arguments_hash": payload.arguments_hash,
                },
            )
        run = self.session.get(Run, tool_call.run_id)
        step = self.session.get(RunStep, tool_call.run_step_id)
        if run is None or step is None or run.workflow_name != WORKFLOW_NAME:
            raise ConflictError("Tool Call is not attached to a resumable Agent Run")
        if run.output_summary.get("phase") != "WAITING_HUMAN":
            raise ConflictError("Agent Run is not waiting for human input")

        now = datetime.now(UTC)
        approval = ToolApproval(
            tool_call_id=tool_call.id,
            decision=payload.decision.value,
            arguments_hash=payload.arguments_hash,
            reviewer=payload.reviewer,
            rationale=payload.rationale,
            client_request_id=payload.client_request_id,
            request_hash=request_hash,
            created_at=now,
        )
        tool_call.approval = approval
        self.session.add(approval)

        adapter = _DiscoveryToolAdapter(
            session=self.session,
            study_id=run.study_id,
            run_id=run.id,
            retrieval=None,
            tool_call_id=tool_call.id,
        )
        graph_state: DiscoveryWorkflowState = {
            "phase": "resume",
            "run_id": str(run.id),
            "goal": str(run.input_snapshot["goal"]),
            "claim_revision_id": str(run.input_snapshot["claim_revision_id"]),
            "claim_statement": str(run.input_snapshot["claim_statement"]),
            "proposed_tool_name": tool_call.tool_name,
            "proposed_tool_arguments": tool_call.arguments,
            "approval_decision": payload.decision.value,
        }
        resumed = compile_discovery_graph(port=adapter).invoke(graph_state)
        finalize_step = self.session.scalar(
            select(RunStep).where(
                RunStep.run_id == run.id,
                RunStep.name == "finalize",
            )
        )
        if finalize_step is None:
            raise RuntimeError("Agent Run is missing the finalize step")

        next_summary = dict(run.output_summary)
        next_summary.pop("pending_tool_call_id", None)
        if payload.decision is ToolApprovalDecision.APPROVE:
            result = dict(resumed["tool_result"])
            tool_call.status = ToolCallStatus.SUCCEEDED.value
            tool_call.result = result
            tool_call.result_hash = canonical_json_hash(result)
            tool_call.completed_at = now
            step.status = RunStepStatus.SUCCEEDED.value
            step.completed_at = now
            step.output_summary = {
                **step.output_summary,
                "approval_id": str(approval.id),
                "decision": payload.decision.value,
                "result_hash": tool_call.result_hash,
            }
            finalize_step.status = RunStepStatus.SUCCEEDED.value
            finalize_step.started_at = now
            finalize_step.completed_at = now
            finalize_step.output_summary = {
                "artifact_type": result["artifact_type"],
                "external_system_written": False,
            }
            run.status = RunStatus.SUCCEEDED.value
            run.completed_at = now
            run.output_summary = {
                **next_summary,
                "phase": "COMPLETED",
                "execution_prevented": False,
                "tool_result": result,
                "approved_by": payload.reviewer,
            }
        else:
            tool_call.status = ToolCallStatus.REJECTED.value
            tool_call.completed_at = now
            step.status = RunStepStatus.CANCELLED.value
            step.completed_at = now
            step.output_summary = {
                **step.output_summary,
                "approval_id": str(approval.id),
                "decision": payload.decision.value,
                "execution_prevented": True,
            }
            finalize_step.status = RunStepStatus.SKIPPED.value
            finalize_step.completed_at = now
            finalize_step.output_summary = {"reason": "human_rejected_tool_call"}
            run.status = RunStatus.CANCELLED.value
            run.completed_at = now
            run.output_summary = {
                **next_summary,
                "phase": "REJECTED",
                "execution_prevented": True,
                "rejected_by": payload.reviewer,
            }
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(ToolApproval).where(
                    ToolApproval.client_request_id == payload.client_request_id
                )
            )
            if concurrent is None:
                raise
            self._assert_idempotent(concurrent.request_hash, request_hash)
        return self.get_run(run.id)

    def get_run(self, run_id: UUID) -> AgentRunRecord:
        run = self.session.scalar(
            select(Run)
            .options(
                selectinload(Run.steps),
                selectinload(Run.tool_calls).selectinload(ToolCall.approval),
            )
            .where(Run.id == run_id, Run.workflow_name == WORKFLOW_NAME)
        )
        if run is None:
            raise NotFoundError("agent_run", run_id)
        manifest_raw = run.output_summary.get("context_manifest_id")
        if not isinstance(manifest_raw, str):
            raise RuntimeError("Agent Run is missing its Context Manifest identity")
        manifest = RetrievalService(self.session).get_context_manifest(UUID(manifest_raw))
        return AgentRunRecord(run=run, manifest=manifest)

    def list_runs(
        self,
        study_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[AgentRunRecord], int]:
        if self.session.get(Study, study_id) is None:
            raise NotFoundError("study", study_id)
        runs = list(
            self.session.scalars(
                select(Run)
                .options(
                    selectinload(Run.steps),
                    selectinload(Run.tool_calls).selectinload(ToolCall.approval),
                )
                .where(Run.study_id == study_id, Run.workflow_name == WORKFLOW_NAME)
                .order_by(Run.created_at.desc(), Run.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        records = []
        for run in runs:
            manifest_raw = run.output_summary.get("context_manifest_id")
            if not isinstance(manifest_raw, str):
                continue
            records.append(
                AgentRunRecord(
                    run=run,
                    manifest=RetrievalService(self.session).get_context_manifest(
                        UUID(manifest_raw)
                    ),
                )
            )
        total = (
            self.session.scalar(
                select(func.count())
                .select_from(Run)
                .where(Run.study_id == study_id, Run.workflow_name == WORKFLOW_NAME)
            )
            or 0
        )
        return records, total

    def _reviewed_current_claim(
        self,
        study_id: UUID,
        claim_revision_id: UUID,
    ) -> tuple[ClaimRevision, Claim, ClaimReview]:
        row = self.session.execute(
            select(ClaimRevision, Claim)
            .join(Claim, Claim.id == ClaimRevision.claim_id)
            .where(ClaimRevision.id == claim_revision_id)
        ).one_or_none()
        if row is None:
            raise NotFoundError("claim_revision", claim_revision_id)
        revision, claim = row
        if claim.study_id != study_id:
            raise ConflictError("Claim Revision belongs to another Study")
        latest_revision = self.session.scalar(
            select(func.max(ClaimRevision.revision)).where(ClaimRevision.claim_id == claim.id)
        )
        latest_review = self.session.scalar(
            select(ClaimReview)
            .where(ClaimReview.claim_revision_id == revision.id)
            .order_by(ClaimReview.created_at.desc(), ClaimReview.id.desc())
            .limit(1)
        )
        if (
            latest_revision != revision.revision
            or claim.status != ClaimStatus.REVIEWED.value
            or latest_review is None
            or latest_review.decision != ReviewDecision.ACCEPT.value
            or revision.counterevidence_status == CounterevidenceStatus.NOT_RUN.value
        ):
            raise ConflictError(
                "Agent Run requires the current reviewed Claim Revision with "
                "counterevidence search",
                details={"claim_revision_id": str(revision.id)},
            )
        return revision, claim, latest_review

    @staticmethod
    def _new_steps(
        run: Run,
        input_snapshot: dict[str, Any],
        now: datetime,
    ) -> tuple[RunStep, RunStep, RunStep, RunStep, RunStep]:
        names = ("plan", "retrieve_context", "draft_hypothesis", "approval_gate", "finalize")
        steps = tuple(
            RunStep(
                run=run,
                name=name,
                ordinal=index,
                status=RunStepStatus.PENDING.value,
                input_snapshot={
                    "run_input_hash": canonical_json_hash(input_snapshot),
                    "step": name,
                },
                input_hash=canonical_json_hash(
                    {"run_input_hash": canonical_json_hash(input_snapshot), "step": name}
                ),
                output_summary={},
                error=None,
                started_at=None,
                completed_at=None,
                created_at=now,
            )
            for index, name in enumerate(names)
        )
        return steps  # type: ignore[return-value]

    @staticmethod
    def _policy_snapshot(tool_name: str) -> dict[str, Any]:
        definition = _tool_definition(tool_name)
        return {
            "policy_version": TOOL_POLICY_VERSION,
            "tool_name": tool_name,
            "tool_version": definition["version"],
            "server_allowlisted": True,
            "access_mode": definition["access_mode"],
            "risk_level": definition["risk_level"],
            "requires_approval": definition["requires_approval"],
            "approval_binding": "exact_arguments_sha256",
            "source_content_handling": "untrusted_data_only",
        }

    @staticmethod
    def _assert_idempotent(existing_hash: str | None, request_hash: str) -> None:
        if existing_hash != request_hash:
            raise ConflictError(
                "client_request_id was already used with a different payload",
                details={"reason": "idempotency_key_reuse"},
            )


def agent_run_response(record: AgentRunRecord) -> AgentRunRead:
    run = record.run
    manifest = record.manifest
    phase = run.output_summary.get("phase")
    if phase not in {"WAITING_HUMAN", "COMPLETED", "FAILED", "REJECTED"}:
        raise RuntimeError("Agent Run has an invalid phase")
    if run.client_request_id is None:
        raise RuntimeError("Agent Run has no client_request_id")
    return AgentRunRead(
        id=run.id,
        study_id=run.study_id,
        workflow_name=run.workflow_name,
        workflow_version=run.workflow_version,
        status=cast(
            Literal["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"],
            run.status,
        ),
        phase=phase,
        goal=str(run.input_snapshot["goal"]),
        claim_revision_id=UUID(str(run.input_snapshot["claim_revision_id"])),
        claim_statement=str(run.input_snapshot["claim_statement"]),
        context_manifest=ContextManifestReferenceRead(
            id=manifest.id,
            query=manifest.query,
            purpose=RetrievalPurpose(manifest.purpose),
            item_count=len(manifest.items),
            content_hash=manifest.content_hash,
            context_url=f"/v1/context-manifests/{manifest.id}",
        ),
        prompt_profile=dict(run.output_summary.get("prompt_profile", {})),
        plan=dict(run.output_summary.get("plan", {})),
        hypothesis=dict(run.output_summary.get("hypothesis", {})),
        output_summary=run.output_summary,
        error=run.error,
        input_hash=run.input_hash,
        client_request_id=run.client_request_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        steps=[
            RunStepRead.model_validate(step)
            for step in sorted(run.steps, key=lambda item: item.ordinal)
        ],
        tool_calls=[
            tool_call_response(call)
            for call in sorted(
                run.tool_calls,
                key=lambda item: (
                    0 if item.access_mode == "read" else 1,
                    str(item.id),
                ),
            )
        ],
    )


def tool_call_response(call: ToolCall) -> ToolCallRead:
    approval = call.approval
    return ToolCallRead(
        id=call.id,
        run_id=call.run_id,
        run_step_id=call.run_step_id,
        tool_name=call.tool_name,
        tool_version=call.tool_version,
        access_mode=cast(Literal["read", "write"], call.access_mode),
        risk_level=cast(Literal["low", "medium", "high"], call.risk_level),
        status=cast(
            Literal[
                "RUNNING",
                "APPROVAL_REQUIRED",
                "SUCCEEDED",
                "REJECTED",
                "FAILED",
            ],
            call.status,
        ),
        arguments=call.arguments,
        arguments_hash=call.arguments_hash,
        result=call.result,
        result_hash=call.result_hash,
        policy_snapshot=call.policy_snapshot,
        requires_approval=call.requires_approval,
        started_at=call.started_at,
        completed_at=call.completed_at,
        created_at=call.created_at,
        approval=(
            ToolApprovalRead(
                id=approval.id,
                decision=ToolApprovalDecision(approval.decision),
                arguments_hash=approval.arguments_hash,
                reviewer=approval.reviewer,
                rationale=approval.rationale,
                client_request_id=approval.client_request_id,
                created_at=approval.created_at,
            )
            if approval is not None
            else None
        ),
    )


def agent_run_list_response(
    records: list[AgentRunRecord],
    total: int,
) -> AgentRunList:
    return AgentRunList(items=[agent_run_response(record) for record in records], total=total)
