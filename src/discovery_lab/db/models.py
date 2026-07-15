from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
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
    EvidenceReviewStatus,
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

    evidence_unit: Mapped[EvidenceUnit] = relationship(back_populates="revisions")
    source_revision: Mapped[SourceRevision] = relationship()
    segment: Mapped[Segment] = relationship(back_populates="evidence_revisions")
    run_step: Mapped[RunStep | None] = relationship(back_populates="evidence_revisions")

    __table_args__ = (
        UniqueConstraint(
            "evidence_unit_id", "revision", name="uq_evidence_revisions_unit_revision"
        ),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("length(content_hash) = 64", name="sha256_length"),
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


IMMUTABLE_MODELS = (SourceRevision, Segment, EvidenceRevision)


def _reject_immutable_update(_mapper: object, _connection: object, target: object) -> None:
    raise ValueError(f"{type(target).__name__} records are immutable; create a new revision")


for _model in IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_immutable_update)
