from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from discovery_lab.domain.enums import RetrievalPurpose, ToolApprovalDecision
from discovery_lab.domain.schemas import RunStepRead


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentRetrievalInput(StrictInput):
    query: str = Field(min_length=1, max_length=4_000)
    purpose: RetrievalPurpose = RetrievalPurpose.SUPPORT
    limit: int = Field(default=5, ge=1, le=20)


class ExperimentDraftArguments(StrictInput):
    title: str = Field(min_length=1, max_length=200)
    primary_metric: str = Field(min_length=1, max_length=500)
    success_threshold: str = Field(min_length=1, max_length=500)
    target_cohort: str = Field(min_length=1, max_length=500)


class AgentRequestedAction(StrictInput):
    tool_name: Literal["create_experiment_draft"]
    arguments: ExperimentDraftArguments


class AgentRunCreate(StrictInput):
    goal: str = Field(min_length=1, max_length=2_000)
    claim_revision_id: UUID
    retrieval: AgentRetrievalInput
    requested_action: AgentRequestedAction
    client_request_id: str = Field(min_length=1, max_length=200)


class ToolApprovalCreate(StrictInput):
    decision: ToolApprovalDecision
    arguments_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=5_000)
    client_request_id: str = Field(min_length=1, max_length=200)


class ToolDefinitionRead(BaseModel):
    name: str
    version: str
    description: str
    access_mode: Literal["read", "write"]
    risk_level: Literal["low", "medium", "high"]
    requires_approval: bool
    server_allowlisted: bool
    mcp_exposed: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolRegistryRead(BaseModel):
    schema_version: Literal["tool-registry.v1"] = "tool-registry.v1"
    policy_version: Literal["tool-policy.v1"] = "tool-policy.v1"
    items: list[ToolDefinitionRead]


class ToolApprovalRead(BaseModel):
    id: UUID
    decision: ToolApprovalDecision
    arguments_hash: str
    reviewer: str
    rationale: str
    client_request_id: str
    created_at: datetime


class ToolCallRead(BaseModel):
    id: UUID
    run_id: UUID
    run_step_id: UUID
    tool_name: str
    tool_version: str
    access_mode: Literal["read", "write"]
    risk_level: Literal["low", "medium", "high"]
    status: Literal[
        "RUNNING",
        "APPROVAL_REQUIRED",
        "SUCCEEDED",
        "REJECTED",
        "FAILED",
    ]
    arguments: dict[str, Any]
    arguments_hash: str
    result: dict[str, Any] | None
    result_hash: str | None
    policy_snapshot: dict[str, Any]
    requires_approval: bool
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    approval: ToolApprovalRead | None


class ContextManifestReferenceRead(BaseModel):
    id: UUID
    query: str
    purpose: RetrievalPurpose
    item_count: int
    content_hash: str
    context_url: str


class AgentRunRead(BaseModel):
    id: UUID
    study_id: UUID
    workflow_name: str
    workflow_version: str
    status: Literal["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
    phase: Literal["WAITING_HUMAN", "COMPLETED", "FAILED", "REJECTED"]
    goal: str
    claim_revision_id: UUID
    claim_statement: str
    context_manifest: ContextManifestReferenceRead
    prompt_profile: dict[str, Any]
    plan: dict[str, Any]
    hypothesis: dict[str, Any]
    output_summary: dict[str, Any]
    error: dict[str, Any] | None
    input_hash: str
    client_request_id: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    steps: list[RunStepRead]
    tool_calls: list[ToolCallRead]


class AgentRunList(BaseModel):
    items: list[AgentRunRead]
    total: int
