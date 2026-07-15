from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class StudyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    research_question: str | None = Field(
        default=None,
        max_length=5_000,
        validation_alias=AliasChoices("research_question", "decision_question"),
    )


class StudyRead(BaseModel):
    id: UUID
    title: str
    description: str | None
    research_question: str | None
    decision_question: str
    status: str
    created_at: datetime
    updated_at: datetime
    source_count: int
    evidence_count: int


class StudyList(BaseModel):
    items: list[StudyRead]
    total: int


class SourceRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision: int
    filename: str
    mime_type: str
    byte_size: int
    content_hash: str
    provenance: dict[str, Any]
    created_at: datetime


class SourceRead(BaseModel):
    id: UUID
    source_id: UUID
    study_id: UUID
    name: str
    display_name: str
    type: str
    source_type: str
    status: str
    domain_status: str
    progress: int
    created_at: datetime
    updated_at: datetime
    revision: SourceRevisionRead


class SourceList(BaseModel):
    items: list[SourceRead]
    total: int


class RunStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    ordinal: int
    status: str
    input_snapshot: dict[str, Any]
    input_hash: str
    output_summary: dict[str, Any]
    error: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    source_id: UUID | None
    workflow_name: str
    workflow_version: str
    status: str
    input_snapshot: dict[str, Any]
    input_hash: str
    output_summary: dict[str, Any]
    error: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    steps: list[RunStepRead]


class RunList(BaseModel):
    items: list[RunRead]
    total: int


class EvidenceRead(BaseModel):
    id: UUID
    evidence_id: UUID
    evidence_revision_id: UUID
    revision: int
    study_id: UUID
    source_id: UUID
    source_name: str
    source_type: str
    source_revision_id: UUID
    segment_id: UUID
    run_step_id: UUID | None
    evidence_type: str
    quote: str
    observation: str | None
    interpretation: str | None
    inference: str | None
    review_status: str
    locator: dict[str, Any]
    locator_label: str
    content_hash: str
    provenance: dict[str, Any]
    kind: str
    title: str
    confidence: float
    relationship: str
    tags: list[str]
    created_at: datetime


class EvidenceList(BaseModel):
    items: list[EvidenceRead]
    total: int
    limit: int
    offset: int


class ContextSegment(BaseModel):
    id: UUID
    ordinal: int
    text: str
    locator: dict[str, Any]
    content_hash: str
    is_target: bool


class EvidenceSourceContext(BaseModel):
    source_id: UUID
    source_revision_id: UUID
    source_name: str
    filename: str
    mime_type: str
    source_content_hash: str


class IntegrityCheck(BaseModel):
    segment_hash_matches: bool
    evidence_hash_matches: bool
    quote_matches_segment: bool


class EvidenceContext(BaseModel):
    evidence_id: UUID
    source_name: str
    locator_label: str
    before: str
    highlight: str
    after: str
    evidence: EvidenceRead
    source: EvidenceSourceContext
    context_segments: list[ContextSegment]
    integrity: IntegrityCheck
