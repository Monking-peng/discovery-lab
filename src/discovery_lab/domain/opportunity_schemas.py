from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from discovery_lab.domain.enums import OpportunityStatus


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OpportunityDraftCreate(StrictInput):
    """Human-authored draft pinned to one exact, reviewed Claim Revision."""

    claim_id: UUID
    claim_revision_id: UUID
    title: str = Field(min_length=1, max_length=200)
    problem_statement: str = Field(min_length=1, max_length=20_000)
    desired_outcome: str = Field(min_length=1, max_length=20_000)
    next_step: str = Field(min_length=1, max_length=20_000)
    rationale: str | None = Field(default=None, max_length=20_000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    risks: list[str] = Field(default_factory=list, max_length=50)
    provenance: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str = Field(min_length=1, max_length=200)

    @field_validator("assumptions", "risks")
    @classmethod
    def normalize_bounded_notes(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in values:
            value = raw.strip()
            if not value:
                continue
            if len(value) > 500:
                raise ValueError("Assumptions and risks must be 500 characters or fewer")
            if value not in normalized:
                normalized.append(value)
        return normalized


class OpportunityDraftRead(BaseModel):
    id: UUID
    study_id: UUID
    claim_id: UUID
    claim_revision_id: UUID
    status: OpportunityStatus
    title: str
    problem_statement: str
    desired_outcome: str
    next_step: str
    rationale: str | None
    confidence: float
    assumptions: list[str]
    risks: list[str]
    provenance: dict[str, Any]
    content_hash: str
    client_request_id: str
    created_at: datetime
    claim_statement: str
    claim_context_url: str
    publishable: Literal[False]
    publication_blockers: list[str]


class OpportunityDraftList(BaseModel):
    items: list[OpportunityDraftRead]
    total: int
    limit: int
    offset: int
