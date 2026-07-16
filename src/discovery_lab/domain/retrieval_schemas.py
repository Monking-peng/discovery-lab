from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from discovery_lab.domain.enums import RetrievalPurpose


class StrictRetrievalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RetrievalCreate(StrictRetrievalInput):
    query: str = Field(min_length=1, max_length=20_000)
    purpose: RetrievalPurpose
    limit: int = Field(default=10, ge=1, le=50)
    client_request_id: str = Field(min_length=1, max_length=200)


class EvidenceSnapshotRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_type: str
    quote: str
    observation: str | None
    interpretation: str | None
    inference: str | None
    locator: dict[str, Any]


class EvidenceReviewSnapshotRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str
    reviewer: str
    rationale: str | None
    created_at: datetime


class ContextManifestItemRead(BaseModel):
    id: UUID
    rank: int
    evidence_id: UUID
    evidence_revision_id: UUID
    source_id: UUID
    source_revision_id: UUID
    evidence_review_id: UUID
    evidence_content_hash: str
    source_content_hash: str
    context_url: str
    source_name: str
    evidence: EvidenceSnapshotRead
    review: EvidenceReviewSnapshotRead
    lexical_score: float
    vector_score: float
    hybrid_score: float
    lexical_rank: int
    vector_rank: int


class ContextManifestRead(BaseModel):
    id: UUID
    context_manifest_id: UUID
    study_id: UUID
    query: str
    purpose: RetrievalPurpose
    result_limit: int
    profile_name: str
    profile_version: str
    lexical_algorithm: str
    vector_algorithm: str
    vector_algorithm_description: str
    fusion_algorithm: str
    query_handling: str
    content_hash: str
    client_request_id: str
    created_at: datetime
    items: list[ContextManifestItemRead]
