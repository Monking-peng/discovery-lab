from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from discovery_lab.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from discovery_lab.domain.enums import (
    ClaimStatus,
    CounterevidenceStatus,
    EvidenceReviewStatus,
    OpportunityStatus,
    RunStatus,
    RunStepStatus,
    SourceStatus,
    StudyStatus,
)

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Study(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "studies"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    research_question: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=StudyStatus.DRAFT.value, nullable=False)

    sources: Mapped[list[Source]] = relationship(
        back_populates="study", cascade="all, delete-orphan"
    )
    evidence_units: Mapped[list[EvidenceUnit]] = relationship(
        back_populates="study", cascade="all, delete-orphan"
    )
    runs: Mapped[list[Run]] = relationship(back_populates="study", cascade="all, delete-orphan")
    claims: Mapped[list[Claim]] = relationship(back_populates="study", cascade="all, delete-orphan")
    opportunity_drafts: Mapped[list[OpportunityDraft]] = relationship(
        back_populates="study", cascade="all, delete-orphan"
    )
    context_manifests: Mapped[list[ContextManifest]] = relationship(
        back_populates="study", cascade="all, delete-orphan"
    )


class Source(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "sources"

    study_id: Mapped[UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="upload", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=SourceStatus.UPLOADED.value, nullable=False
    )

    study: Mapped[Study] = relationship(back_populates="sources")
    revisions: Mapped[list[SourceRevision]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="SourceRevision.revision",
    )
    runs: Mapped[list[Run]] = relationship(back_populates="source")

    __table_args__ = (Index("ix_sources_study_created", "study_id", "created_at"),)


class SourceRevision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable snapshot of uploaded source bytes and their provenance."""

    __tablename__ = "source_revisions"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    blob_uri: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)

    source: Mapped[Source] = relationship(back_populates="revisions")
    segments: Mapped[list[Segment]] = relationship(
        back_populates="source_revision",
        cascade="all, delete-orphan",
        order_by="Segment.ordinal",
    )

    __table_args__ = (
        UniqueConstraint("source_id", "revision", name="uq_source_revisions_source_revision"),
        UniqueConstraint("source_id", "content_hash", name="uq_source_revisions_source_hash"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("byte_size >= 0", name="nonnegative_byte_size"),
        CheckConstraint("length(content_hash) = 64", name="sha256_length"),
    )


class Segment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable, addressable source text produced by deterministic parsing."""

    __tablename__ = "segments"

    source_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_revisions.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)

    source_revision: Mapped[SourceRevision] = relationship(back_populates="segments")
    evidence_revisions: Mapped[list[EvidenceRevision]] = relationship(back_populates="segment")

    __table_args__ = (
        UniqueConstraint("source_revision_id", "ordinal", name="uq_segments_revision_ordinal"),
        CheckConstraint("ordinal >= 0", name="nonnegative_ordinal"),
        CheckConstraint("length(content_hash) = 64", name="sha256_length"),
    )


class EvidenceUnit(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Stable identity for an evidence candidate across immutable revisions."""

    __tablename__ = "evidence_units"

    study_id: Mapped[UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )

    study: Mapped[Study] = relationship(back_populates="evidence_units")
    revisions: Mapped[list[EvidenceRevision]] = relationship(
        back_populates="evidence_unit",
        cascade="all, delete-orphan",
        order_by="EvidenceRevision.revision",
    )

    __table_args__ = (Index("ix_evidence_units_study_created", "study_id", "created_at"),)


class EvidenceRevision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable evidence content; review actions belong in a separate review record."""

    __tablename__ = "evidence_revisions"

    evidence_unit_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_units.id", ondelete="CASCADE"), nullable=False
    )
    parent_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("evidence_revisions.id", ondelete="RESTRICT")
    )
    source_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    segment_id: Mapped[UUID] = mapped_column(
        ForeignKey("segments.id", ondelete="RESTRICT"), nullable=False
    )
    run_step_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL")
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(50), default="source_excerpt", nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    observation: Mapped[str | None] = mapped_column(Text)
    interpretation: Mapped[str | None] = mapped_column(Text)
    inference: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(
        String(32), default=EvidenceReviewStatus.PROPOSED.value, nullable=False
    )
    locator: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    client_request_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str | None] = mapped_column(String(64))

    evidence_unit: Mapped[EvidenceUnit] = relationship(back_populates="revisions")
    parent_revision: Mapped[EvidenceRevision | None] = relationship(
        remote_side="EvidenceRevision.id",
        foreign_keys=[parent_revision_id],
    )
    source_revision: Mapped[SourceRevision] = relationship()
    segment: Mapped[Segment] = relationship(back_populates="evidence_revisions")
    run_step: Mapped[RunStep | None] = relationship(back_populates="evidence_revisions")
    reviews: Mapped[list[EvidenceReview]] = relationship(
        back_populates="evidence_revision",
        cascade="all, delete-orphan",
        order_by="EvidenceReview.created_at",
    )
    claim_edges: Mapped[list[ClaimEvidenceEdge]] = relationship(back_populates="evidence_revision")

    __table_args__ = (
        UniqueConstraint(
            "evidence_unit_id", "revision", name="uq_evidence_revisions_unit_revision"
        ),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("length(content_hash) = 64", name="sha256_length"),
        CheckConstraint(
            "request_hash IS NULL OR length(request_hash) = 64",
            name="request_hash_sha256_length",
        ),
        Index("ix_evidence_revisions_source_revision", "source_revision_id"),
    )


class Run(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "runs"

    study_id: Mapped[UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    workflow_name: Mapped[str] = mapped_column(String(100), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.QUEUED.value, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, nullable=False
    )
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    study: Mapped[Study] = relationship(back_populates="runs")
    source: Mapped[Source | None] = relationship(back_populates="runs")
    steps: Mapped[list[RunStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunStep.ordinal"
    )

    __table_args__ = (
        CheckConstraint("length(input_hash) = 64", name="sha256_length"),
        Index("ix_runs_study_created", "study_id", "created_at"),
        Index("ix_runs_source_input_hash", "source_id", "input_hash"),
        Index(
            "uq_runs_active_source_input_hash",
            "source_id",
            "input_hash",
            unique=True,
            postgresql_where=sql_text("status IN ('RUNNING', 'SUCCEEDED')"),
            sqlite_where=sql_text("status IN ('RUNNING', 'SUCCEEDED')"),
        ),
    )


class RunStep(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "run_steps"

    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=RunStepStatus.PENDING.value, nullable=False
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, nullable=False
    )
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[Run] = relationship(back_populates="steps")
    evidence_revisions: Mapped[list[EvidenceRevision]] = relationship(back_populates="run_step")

    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_run_steps_run_ordinal"),
        UniqueConstraint("run_id", "name", name="uq_run_steps_run_name"),
        CheckConstraint("ordinal >= 0", name="nonnegative_ordinal"),
        CheckConstraint("length(input_hash) = 64", name="sha256_length"),
    )


class EvidenceReview(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only human decision for one exact immutable evidence revision."""

    __tablename__ = "evidence_reviews"

    evidence_unit_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_units.id", ondelete="CASCADE"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_revisions.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    client_request_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    evidence_revision: Mapped[EvidenceRevision] = relationship(back_populates="reviews")

    __table_args__ = (
        CheckConstraint(
            "decision IN ('ACCEPT', 'REQUEST_CHANGES', 'REJECT')",
            name="valid_decision",
        ),
        CheckConstraint("length(request_hash) = 64", name="request_hash_sha256_length"),
        Index("ix_evidence_reviews_revision_created", "evidence_revision_id", "created_at"),
    )


class Claim(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Stable claim identity; all authored content lives in immutable revisions."""

    __tablename__ = "claims"

    study_id: Mapped[UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default=ClaimStatus.PROPOSED.value, nullable=False
    )

    study: Mapped[Study] = relationship(back_populates="claims")
    revisions: Mapped[list[ClaimRevision]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ClaimRevision.revision",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PROPOSED', 'REVIEWED', 'REJECTED', 'STALE', 'INVALIDATED')",
            name="valid_status",
        ),
        Index("ix_claims_study_created", "study_id", "created_at"),
    )


class ClaimRevision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable statement and frozen Evidence Revision edge set."""

    __tablename__ = "claim_revisions"

    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    base_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("claim_revisions.id", ondelete="RESTRICT")
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    topic_key: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    counterevidence_status: Mapped[str] = mapped_column(
        String(32), default=CounterevidenceStatus.NOT_RUN.value, nullable=False
    )
    counterevidence_summary: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    claim: Mapped[Claim] = relationship(back_populates="revisions", foreign_keys=[claim_id])
    base_revision: Mapped[ClaimRevision | None] = relationship(
        remote_side="ClaimRevision.id", foreign_keys=[base_revision_id]
    )
    evidence_edges: Mapped[list[ClaimEvidenceEdge]] = relationship(
        back_populates="claim_revision",
        cascade="all, delete-orphan",
        order_by="ClaimEvidenceEdge.created_at",
    )
    reviews: Mapped[list[ClaimReview]] = relationship(
        back_populates="claim_revision",
        cascade="all, delete-orphan",
        order_by="ClaimReview.created_at",
    )

    __table_args__ = (
        UniqueConstraint("claim_id", "revision", name="uq_claim_revisions_claim_revision"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "counterevidence_status IN ('NOT_RUN', 'SEARCHED_NONE_FOUND', 'FOUND')",
            name="valid_counterevidence_status",
        ),
        CheckConstraint("length(content_hash) = 64", name="content_hash_sha256_length"),
        CheckConstraint("length(request_hash) = 64", name="request_hash_sha256_length"),
        Index("ix_claim_revisions_claim_created", "claim_id", "created_at"),
    )


class ClaimEvidenceEdge(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable relation from one Claim Revision to one Evidence Revision."""

    __tablename__ = "claim_evidence_edges"

    claim_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("claim_revisions.id", ondelete="CASCADE"), nullable=False
    )
    evidence_unit_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_units.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    relation_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)

    claim_revision: Mapped[ClaimRevision] = relationship(back_populates="evidence_edges")
    evidence_revision: Mapped[EvidenceRevision] = relationship(back_populates="claim_edges")

    __table_args__ = (
        UniqueConstraint(
            "claim_revision_id",
            "evidence_revision_id",
            name="uq_claim_evidence_edges_claim_evidence_revision",
        ),
        CheckConstraint(
            "relation IN ('supports', 'contradicts', 'contextualizes', 'insufficient_for')",
            name="valid_relation",
        ),
        CheckConstraint("relevance >= 0 AND relevance <= 1", name="relevance_range"),
        Index("ix_claim_evidence_edges_evidence_revision", "evidence_revision_id"),
    )


class ClaimReview(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only human decision bound to one exact Claim Revision."""

    __tablename__ = "claim_reviews"

    claim_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("claim_revisions.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence_review_snapshot: Mapped[dict[str, str]] = mapped_column(
        JSON_DOCUMENT, default=dict, nullable=False
    )
    client_request_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    claim_revision: Mapped[ClaimRevision] = relationship(back_populates="reviews")

    __table_args__ = (
        CheckConstraint(
            "decision IN ('ACCEPT', 'REQUEST_CHANGES', 'REJECT')",
            name="valid_decision",
        ),
        CheckConstraint("length(request_hash) = 64", name="request_hash_sha256_length"),
        Index("ix_claim_reviews_revision_created", "claim_revision_id", "created_at"),
    )


class OpportunityDraft(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable Opportunity proposal pinned to one exact Claim Revision.

    The first vertical slice intentionally has no publish transition. A draft can
    be evaluated and replayed, but cannot be represented as a published decision.
    """

    __tablename__ = "opportunity_drafts"

    study_id: Mapped[UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    claim_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("claim_revisions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default=OpportunityStatus.DRAFT.value, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    desired_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    study: Mapped[Study] = relationship(back_populates="opportunity_drafts")
    claim: Mapped[Claim] = relationship()
    claim_revision: Mapped[ClaimRevision] = relationship()

    __table_args__ = (
        CheckConstraint("status = 'DRAFT'", name="valid_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("length(content_hash) = 64", name="content_hash_sha256_length"),
        CheckConstraint("length(request_hash) = 64", name="request_hash_sha256_length"),
        Index("ix_opportunity_drafts_study_created", "study_id", "created_at"),
        Index("ix_opportunity_drafts_claim_revision", "claim_revision_id"),
    )


class EvidenceSearchProjection(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Rebuildable retrieval projection; never an evidence source of truth."""

    __tablename__ = "evidence_search_projections"

    study_id: Mapped[UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE", name="fk_search_projection_study"),
        nullable=False,
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "evidence_revisions.id",
            ondelete="CASCADE",
            name="fk_search_projection_evidence_revision",
        ),
        nullable=False,
        unique=True,
    )
    projection_text: Mapped[str] = mapped_column(Text, nullable=False)
    lexical_terms: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(256).with_variant(JSON(), "sqlite"), nullable=False
    )
    algorithm_name: Mapped[str] = mapped_column(String(100), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("CURRENT_TIMESTAMP"), nullable=False
    )

    __table_args__ = (
        CheckConstraint("length(evidence_content_hash) = 64", name="content_hash_sha256"),
        Index("ix_evidence_search_projections_study", "study_id"),
    )


class ContextManifest(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable record of a retrieval request and its exact ranked result set."""

    __tablename__ = "context_manifests"

    study_id: Mapped[UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    result_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(50), nullable=False)
    lexical_algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    vector_algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    fusion_algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    query_handling: Mapped[str] = mapped_column(String(50), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    study: Mapped[Study] = relationship(back_populates="context_manifests")
    items: Mapped[list[ContextManifestItem]] = relationship(
        back_populates="context_manifest",
        cascade="all, delete-orphan",
        order_by="ContextManifestItem.ordinal",
    )

    __table_args__ = (
        CheckConstraint(
            "purpose IN ('support', 'counterevidence', 'explore')", name="valid_purpose"
        ),
        CheckConstraint("result_limit > 0 AND result_limit <= 50", name="valid_result_limit"),
        CheckConstraint("length(content_hash) = 64", name="content_hash_sha256_length"),
        CheckConstraint("length(request_hash) = 64", name="request_hash_sha256_length"),
        Index("ix_context_manifests_study_created", "study_id", "created_at"),
    )


class ContextManifestItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Frozen exact Evidence/Source/Review revision and scores returned by retrieval."""

    __tablename__ = "context_manifest_items"

    context_manifest_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_manifests.id", ondelete="CASCADE", name="fk_manifest_items_manifest"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_unit_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "evidence_units.id", ondelete="RESTRICT", name="fk_manifest_items_evidence_unit"
        ),
        nullable=False,
    )
    evidence_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "evidence_revisions.id",
            ondelete="RESTRICT",
            name="fk_manifest_items_evidence_revision",
        ),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT", name="fk_manifest_items_source"),
        nullable=False,
    )
    source_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "source_revisions.id",
            ondelete="RESTRICT",
            name="fk_manifest_items_source_revision",
        ),
        nullable=False,
    )
    evidence_review_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "evidence_reviews.id",
            ondelete="RESTRICT",
            name="fk_manifest_items_evidence_review",
        ),
        nullable=False,
    )
    evidence_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    review_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    lexical_score: Mapped[float] = mapped_column(Float, nullable=False)
    vector_score: Mapped[float] = mapped_column(Float, nullable=False)
    hybrid_score: Mapped[float] = mapped_column(Float, nullable=False)
    lexical_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_rank: Mapped[int] = mapped_column(Integer, nullable=False)

    context_manifest: Mapped[ContextManifest] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint(
            "context_manifest_id", "ordinal", name="uq_context_manifest_items_manifest_ordinal"
        ),
        UniqueConstraint(
            "context_manifest_id",
            "evidence_revision_id",
            name="uq_context_manifest_items_manifest_evidence_revision",
        ),
        CheckConstraint("ordinal > 0", name="positive_ordinal"),
        CheckConstraint("lexical_score >= 0", name="nonnegative_lexical_score"),
        CheckConstraint("vector_score >= -1 AND vector_score <= 1", name="vector_score_range"),
        CheckConstraint("hybrid_score >= 0", name="nonnegative_hybrid_score"),
        CheckConstraint("lexical_rank > 0 AND vector_rank > 0", name="positive_ranks"),
        CheckConstraint("length(evidence_content_hash) = 64", name="evidence_hash_sha256"),
        CheckConstraint("length(source_content_hash) = 64", name="source_hash_sha256"),
        Index("ix_context_manifest_items_manifest", "context_manifest_id", "ordinal"),
    )


IMMUTABLE_MODELS = (
    SourceRevision,
    Segment,
    EvidenceRevision,
    EvidenceReview,
    ClaimRevision,
    ClaimEvidenceEdge,
    ClaimReview,
    OpportunityDraft,
    ContextManifest,
    ContextManifestItem,
)


def _reject_immutable_update(_mapper: object, _connection: object, target: object) -> None:
    raise ValueError(f"{type(target).__name__} records are immutable; create a new revision")


for _model in IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_immutable_update)
