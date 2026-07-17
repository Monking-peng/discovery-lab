"""Add append-only Evidence Reviews and revision-pinned Claims."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0003"
down_revision: str | None = "20260715_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "evidence_revisions",
        sa.Column("parent_revision_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "evidence_revisions",
        sa.Column("client_request_id", sa.String(200), nullable=True),
    )
    op.add_column(
        "evidence_revisions",
        sa.Column("request_hash", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_evidence_revisions_parent_revision_id_evidence_revisions",
        "evidence_revisions",
        "evidence_revisions",
        ["parent_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_evidence_revisions_client_request_id",
        "evidence_revisions",
        ["client_request_id"],
    )
    op.create_check_constraint(
        "ck_evidence_revisions_request_hash_sha256_length",
        "evidence_revisions",
        "request_hash IS NULL OR length(request_hash) = 64",
    )

    op.create_table(
        "evidence_reviews",
        sa.Column("evidence_unit_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_revision_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reviewer", sa.String(200), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "decision IN ('ACCEPT', 'REQUEST_CHANGES', 'REJECT')",
            name="ck_evidence_reviews_valid_decision",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_evidence_reviews_request_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_unit_id"],
            ["evidence_units.id"],
            name="fk_evidence_reviews_evidence_unit_id_evidence_units",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_revision_id"],
            ["evidence_revisions.id"],
            name="fk_evidence_reviews_evidence_revision_id_evidence_revisions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_reviews"),
        sa.UniqueConstraint("client_request_id", name="uq_evidence_reviews_client_request_id"),
    )
    op.create_index(
        "ix_evidence_reviews_revision_created",
        "evidence_reviews",
        ["evidence_revision_id", "created_at"],
    )

    op.create_table(
        "claims",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'REVIEWED', 'REJECTED', 'STALE', 'INVALIDATED')",
            name="ck_claims_valid_status",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["studies.id"],
            name="fk_claims_study_id_studies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claims"),
    )
    op.create_index("ix_claims_study_created", "claims", ["study_id", "created_at"])

    op.create_table(
        "claim_revisions",
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("base_revision_id", sa.Uuid(), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("topic_key", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("counterevidence_status", sa.String(32), nullable=False),
        sa.Column("counterevidence_summary", sa.Text(), nullable=True),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision > 0", name="ck_claim_revisions_positive_revision"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_claim_revisions_confidence_range",
        ),
        sa.CheckConstraint(
            "counterevidence_status IN ('NOT_RUN', 'SEARCHED_NONE_FOUND', 'FOUND')",
            name="ck_claim_revisions_valid_counterevidence_status",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_claim_revisions_content_hash_sha256_length",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_claim_revisions_request_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["base_revision_id"],
            ["claim_revisions.id"],
            name="fk_claim_revisions_base_revision_id_claim_revisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            name="fk_claim_revisions_claim_id_claims",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claim_revisions"),
        sa.UniqueConstraint("claim_id", "revision", name="uq_claim_revisions_claim_revision"),
        sa.UniqueConstraint("client_request_id", name="uq_claim_revisions_client_request_id"),
    )
    op.create_index(
        "ix_claim_revisions_claim_created",
        "claim_revisions",
        ["claim_id", "created_at"],
    )

    op.create_table(
        "claim_evidence_edges",
        sa.Column("claim_revision_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_unit_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_revision_id", sa.Uuid(), nullable=False),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.Column("relation_confirmed", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "relation IN ('supports', 'contradicts', 'contextualizes', 'insufficient_for')",
            name="ck_claim_evidence_edges_valid_relation",
        ),
        sa.CheckConstraint(
            "relevance >= 0 AND relevance <= 1",
            name="ck_claim_evidence_edges_relevance_range",
        ),
        sa.ForeignKeyConstraint(
            ["claim_revision_id"],
            ["claim_revisions.id"],
            name="fk_claim_evidence_edges_claim_revision_id_claim_revisions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_revision_id"],
            ["evidence_revisions.id"],
            name="fk_claim_evidence_edges_evidence_revision_id_evidence_revisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_unit_id"],
            ["evidence_units.id"],
            name="fk_claim_evidence_edges_evidence_unit_id_evidence_units",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claim_evidence_edges"),
        sa.UniqueConstraint(
            "claim_revision_id",
            "evidence_revision_id",
            name="uq_claim_evidence_edges_claim_evidence_revision",
        ),
    )
    op.create_index(
        "ix_claim_evidence_edges_evidence_revision",
        "claim_evidence_edges",
        ["evidence_revision_id"],
    )

    op.create_table(
        "claim_reviews",
        sa.Column("claim_revision_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reviewer", sa.String(200), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence_review_snapshot", JSONB, nullable=False),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "decision IN ('ACCEPT', 'REQUEST_CHANGES', 'REJECT')",
            name="ck_claim_reviews_valid_decision",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_claim_reviews_request_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["claim_revision_id"],
            ["claim_revisions.id"],
            name="fk_claim_reviews_claim_revision_id_claim_revisions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claim_reviews"),
        sa.UniqueConstraint("client_request_id", name="uq_claim_reviews_client_request_id"),
    )
    op.create_index(
        "ix_claim_reviews_revision_created",
        "claim_reviews",
        ["claim_revision_id", "created_at"],
    )

    for table in (
        "evidence_reviews",
        "claim_revisions",
        "claim_evidence_edges",
        "claim_reviews",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_immutable_revision_update()"
        )


def downgrade() -> None:
    for table in (
        "claim_reviews",
        "claim_evidence_edges",
        "claim_revisions",
        "evidence_reviews",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.drop_index("ix_claim_reviews_revision_created", table_name="claim_reviews")
    op.drop_table("claim_reviews")
    op.drop_index("ix_claim_evidence_edges_evidence_revision", table_name="claim_evidence_edges")
    op.drop_table("claim_evidence_edges")
    op.drop_index("ix_claim_revisions_claim_created", table_name="claim_revisions")
    op.drop_table("claim_revisions")
    op.drop_index("ix_claims_study_created", table_name="claims")
    op.drop_table("claims")
    op.drop_index("ix_evidence_reviews_revision_created", table_name="evidence_reviews")
    op.drop_table("evidence_reviews")
    op.drop_constraint(
        "ck_evidence_revisions_request_hash_sha256_length",
        "evidence_revisions",
        type_="check",
    )
    op.drop_constraint(
        "uq_evidence_revisions_client_request_id",
        "evidence_revisions",
        type_="unique",
    )
    op.drop_constraint(
        "fk_evidence_revisions_parent_revision_id_evidence_revisions",
        "evidence_revisions",
        type_="foreignkey",
    )
    op.drop_column("evidence_revisions", "request_hash")
    op.drop_column("evidence_revisions", "client_request_id")
    op.drop_column("evidence_revisions", "parent_revision_id")
