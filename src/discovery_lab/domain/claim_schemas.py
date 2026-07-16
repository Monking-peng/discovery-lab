from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from discovery_lab.domain.enums import (
    ClaimEvidenceRelation,
    ClaimStatus,
    CounterevidenceStatus,
    ReviewDecision,
)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceReviewCreate(StrictInput):
    evidence_revision_id: UUID
    decision: ReviewDecision
    reviewer: str = Field(min_length=1, max_length=200)
    rationale: str | None = Field(default=None, max_length=10_000)
    client_request_id: str = Field(min_length=1, max_length=200)


class EvidenceReviewRead(BaseModel):
    id: UUID
    evidence_id: UUID
    evidence_revision_id: UUID
    decision: ReviewDecision
    reviewer: str
    rationale: str | None
    client_request_id: str
    created_at: datetime


class EvidenceRevisionAuthorCreate(StrictInput):
    base_revision_id: UUID
    observation: str = Field(min_length=1, max_length=20_000)
    interpretation: str | None = Field(default=None, max_length=20_000)
    inference: str | None = Field(default=None, max_length=20_000)
    confidence: float = Field(default=1.0, ge=0, le=1)
    tags: list[str] = Field(default_factory=list, max_length=50)
    editor: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=10_000)
    client_request_id: str = Field(min_length=1, max_length=200)


class EvidenceRevisionAuthoredRead(BaseModel):
    evidence_id: UUID
    evidence_revision_id: UUID
    parent_revision_id: UUID
    revision: int
    source_revision_id: UUID
    segment_id: UUID
    review_status: str
    content_hash: str
    provenance: dict[str, Any]
    client_request_id: str
    created_at: datetime


class ClaimEvidenceEdgeCreate(StrictInput):
    evidence_id: UUID
    evidence_revision_id: UUID
    relation: ClaimEvidenceRelation
    relation_confirmed: bool = False
    rationale: str = Field(min_length=1, max_length=10_000)
    relevance: float = Field(default=0.5, ge=0, le=1)


class ClaimContentInput(StrictInput):
    statement: str = Field(min_length=1, max_length=20_000)
    topic_key: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=20_000)
    rationale: str = Field(min_length=1, max_length=20_000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    counterevidence_status: CounterevidenceStatus = CounterevidenceStatus.NOT_RUN
    counterevidence_summary: str | None = Field(default=None, max_length=20_000)
    provenance: dict[str, Any] = Field(default_factory=dict)
    evidence_edges: list[ClaimEvidenceEdgeCreate] = Field(min_length=1, max_length=500)
    client_request_id: str = Field(min_length=1, max_length=200)


class ClaimCreate(ClaimContentInput):
    pass


class ClaimRevisionCreate(ClaimContentInput):
    base_revision_id: UUID


class ClaimReviewCreate(StrictInput):
    decision: ReviewDecision
    reviewer: str = Field(min_length=1, max_length=200)
    rationale: str | None = Field(default=None, max_length=10_000)
    client_request_id: str = Field(min_length=1, max_length=200)


class ClaimReviewRead(BaseModel):
    id: UUID
    claim_id: UUID
    claim_revision_id: UUID
    decision: ReviewDecision
    reviewer: str
    rationale: str | None
    evidence_review_snapshot: dict[str, str]
    client_request_id: str
    created_at: datetime


class ClaimEvidenceEdgeRead(BaseModel):
    id: UUID
    evidence_id: UUID
    evidence_revision_id: UUID
    source_id: UUID
    source_revision_id: UUID
    relation: ClaimEvidenceRelation
    relation_confirmed: bool
    rationale: str
    relevance: float
    context_url: str
    latest_evidence_review: EvidenceReviewRead | None


class ClaimRead(BaseModel):
    id: UUID
    claim_id: UUID
    study_id: UUID
    status: ClaimStatus
    revision_status: ClaimStatus
    is_current: bool
    revision_id: UUID
    claim_revision_id: UUID
    revision: int
    base_revision_id: UUID | None
    statement: str
    topic_key: str
    summary: str | None
    rationale: str
    confidence: float
    counterevidence_status: CounterevidenceStatus
    counterevidence_summary: str | None
    provenance: dict[str, Any]
    content_hash: str
    created_at: datetime
    evidence_edges: list[ClaimEvidenceEdgeRead]
    latest_review: ClaimReviewRead | None
    publication_blockers: list[str]


class ClaimList(BaseModel):
    items: list[ClaimRead]
    total: int
    limit: int
    offset: int
