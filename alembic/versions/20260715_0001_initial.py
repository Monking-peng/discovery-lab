"""Create the provenance-first Source to Evidence schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "studies",
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("research_question", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_studies"),
    )
    op.create_table(
        "sources",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["study_id"], ["studies.id"], name="fk_sources_study_id_studies", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
    )
    op.create_index("ix_sources_study_created", "sources", ["study_id", "created_at"])
    op.create_table(
        "source_revisions",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(150), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("blob_uri", sa.Text(), nullable=False),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("byte_size >= 0", name="ck_source_revisions_nonnegative_byte_size"),
        sa.CheckConstraint("revision > 0", name="ck_source_revisions_positive_revision"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_source_revisions_sha256_length"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_revisions_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_revisions"),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_source_revisions_source_hash"),
        sa.UniqueConstraint("source_id", "revision", name="uq_source_revisions_source_revision"),
    )
    op.create_table(
        "segments",
        sa.Column("source_revision_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("locator", JSONB, nullable=False),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_segments_nonnegative_ordinal"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_segments_sha256_length"),
        sa.ForeignKeyConstraint(
            ["source_revision_id"],
            ["source_revisions.id"],
            name="fk_segments_source_revision_id_source_revisions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_segments"),
        sa.UniqueConstraint("source_revision_id", "ordinal", name="uq_segments_revision_ordinal"),
    )
    op.create_table(
        "evidence_units",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["studies.id"],
            name="fk_evidence_units_study_id_studies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_units"),
    )
    op.create_index("ix_evidence_units_study_created", "evidence_units", ["study_id", "created_at"])
    op.create_table(
        "runs",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_name", sa.String(100), nullable=False),
        sa.Column("workflow_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_snapshot", JSONB, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_summary", JSONB, nullable=False),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(input_hash) = 64", name="ck_runs_sha256_length"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_runs_source_id_sources", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["study_id"], ["studies.id"], name="fk_runs_study_id_studies", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
    )
    op.create_index("ix_runs_source_input_hash", "runs", ["source_id", "input_hash"])
    op.create_index("ix_runs_study_created", "runs", ["study_id", "created_at"])
    op.create_table(
        "run_steps",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_snapshot", JSONB, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_summary", JSONB, nullable=False),
        sa.Column("error", JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(input_hash) = 64", name="ck_run_steps_sha256_length"),
        sa.CheckConstraint("ordinal >= 0", name="ck_run_steps_nonnegative_ordinal"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_run_steps_run_id_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_steps"),
        sa.UniqueConstraint("run_id", "name", name="uq_run_steps_run_name"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_run_steps_run_ordinal"),
    )
    op.create_table(
        "evidence_revisions",
        sa.Column("evidence_unit_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision_id", sa.Uuid(), nullable=False),
        sa.Column("segment_id", sa.Uuid(), nullable=False),
        sa.Column("run_step_id", sa.Uuid(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(50), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("interpretation", sa.Text(), nullable=True),
        sa.Column("inference", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("locator", JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision > 0", name="ck_evidence_revisions_positive_revision"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_evidence_revisions_sha256_length"),
        sa.ForeignKeyConstraint(
            ["evidence_unit_id"],
            ["evidence_units.id"],
            name="fk_evidence_revisions_evidence_unit_id_evidence_units",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_step_id"],
            ["run_steps.id"],
            name="fk_evidence_revisions_run_step_id_run_steps",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["segments.id"],
            name="fk_evidence_revisions_segment_id_segments",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"],
            ["source_revisions.id"],
            name="fk_evidence_revisions_source_revision_id_source_revisions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_revisions"),
        sa.UniqueConstraint(
            "evidence_unit_id", "revision", name="uq_evidence_revisions_unit_revision"
        ),
    )
    op.create_index(
        "ix_evidence_revisions_source_revision", "evidence_revisions", ["source_revision_id"]
    )

    op.execute(
        """
        CREATE FUNCTION reject_immutable_revision_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% rows are immutable; create a new revision', TG_TABLE_NAME
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in ("source_revisions", "segments", "evidence_revisions"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_immutable_revision_update()"
        )


def downgrade() -> None:
    for table in ("evidence_revisions", "segments", "source_revisions"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_immutable_revision_update()")
    op.drop_index("ix_evidence_revisions_source_revision", table_name="evidence_revisions")
    op.drop_table("evidence_revisions")
    op.drop_table("run_steps")
    op.drop_index("ix_runs_study_created", table_name="runs")
    op.drop_index("ix_runs_source_input_hash", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_evidence_units_study_created", table_name="evidence_units")
    op.drop_table("evidence_units")
    op.drop_table("segments")
    op.drop_table("source_revisions")
    op.drop_index("ix_sources_study_created", table_name="sources")
    op.drop_table("sources")
    op.drop_table("studies")
