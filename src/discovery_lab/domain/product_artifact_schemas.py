from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FalsifiableHypothesisInput(StrictInput):
    statement: str = Field(min_length=1, max_length=20_000)
    expected_outcome: str = Field(min_length=1, max_length=5_000)
    falsification_criterion: str = Field(min_length=1, max_length=5_000)
    falsifiable: Literal[True]
    claim_revision_id: UUID
    context_manifest_id: UUID


class ApprovedExperimentDraftInput(StrictInput):
    title: str = Field(min_length=1, max_length=200)
    primary_metric: str = Field(min_length=1, max_length=500)
    success_threshold: str = Field(min_length=1, max_length=500)
    target_cohort: str = Field(min_length=1, max_length=500)
    claim_revision_id: UUID
    context_manifest_id: UUID
    hypothesis: FalsifiableHypothesisInput


class ProductDecisionCreate(StrictInput):
    decision: Literal["PROCEED", "ITERATE", "STOP"]
    observed_result: str = Field(min_length=1, max_length=20_000)
    rationale: str = Field(min_length=1, max_length=20_000)
    decided_by: str = Field(min_length=1, max_length=200)
    client_request_id: str = Field(min_length=1, max_length=200)


class PrdArtifactCreate(StrictInput):
    title: str = Field(min_length=1, max_length=240)
    client_request_id: str = Field(min_length=1, max_length=200)


class HypothesisRead(BaseModel):
    id: UUID
    study_id: UUID
    run_id: UUID
    claim_id: UUID
    claim_revision_id: UUID
    context_manifest_id: UUID
    status: Literal["DRAFT"]
    statement: str
    expected_outcome: str
    falsification_criterion: str
    provenance: dict[str, Any]
    content_hash: str
    created_at: datetime


class ExperimentRead(BaseModel):
    id: UUID
    study_id: UUID
    hypothesis_id: UUID
    tool_call_id: UUID
    status: Literal["DRAFT"]
    title: str
    target_cohort: str
    primary_metric: str
    success_threshold: str
    provenance: dict[str, Any]
    content_hash: str
    created_at: datetime


class ProductDecisionRead(BaseModel):
    id: UUID
    study_id: UUID
    experiment_id: UUID
    decision: Literal["PROCEED", "ITERATE", "STOP"]
    observed_result: str
    rationale: str
    decided_by: str
    content_hash: str
    client_request_id: str
    created_at: datetime


class PrdSectionRead(BaseModel):
    body: str
    citation_refs: list[str]


class ClaimRevisionCitationRead(BaseModel):
    kind: Literal["claim_revision"]
    citation_id: str
    claim_id: UUID
    revision_id: UUID
    revision: int
    statement: str
    summary: str | None
    content_hash: str
    review_id: UUID
    review_decision: Literal["ACCEPT"]
    review_reviewer: str
    context_url: str


class EvidenceRevisionCitationRead(BaseModel):
    kind: Literal["evidence_revision"]
    citation_id: str
    evidence_id: UUID
    revision_id: UUID
    source_id: UUID
    source_revision_id: UUID
    evidence_review_id: UUID
    review_decision: Literal["ACCEPT"]
    review_reviewer: str
    evidence_content_hash: str
    source_content_hash: str
    source_name: str
    quote: str
    observation: str | None
    locator: dict[str, Any]
    context_url: str


PrdCitationRead = Annotated[
    ClaimRevisionCitationRead | EvidenceRevisionCitationRead,
    Field(discriminator="kind"),
]


class PrdArtifactRead(BaseModel):
    id: UUID
    study_id: UUID
    decision_id: UUID
    title: str
    status: Literal["DRAFT"]
    publishable: Literal[False]
    sections: dict[str, PrdSectionRead]
    citations: list[PrdCitationRead]
    publication_blockers: list[str]
    content_hash: str
    client_request_id: str
    created_at: datetime


class ProductArtifactChainRead(BaseModel):
    hypothesis: HypothesisRead
    experiment: ExperimentRead
    decisions: list[ProductDecisionRead]
    prds: list[PrdArtifactRead]


class ProductArtifactBundleRead(BaseModel):
    study_id: UUID
    total_experiments: int
    items: list[ProductArtifactChainRead]
