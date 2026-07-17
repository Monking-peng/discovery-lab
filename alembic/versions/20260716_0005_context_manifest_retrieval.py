"""Add rebuildable pgvector search projections and immutable Context Manifests."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0005"
down_revision: str | None = "20260716_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # The production retrieval path uses pgvector's cosine-distance operator.
    # The application has a deterministic Python fallback only for SQLite tests.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Early local 0003 installs predated the human-revision lineage columns that
    # were added while this prerelease was still unshipped. Converge those
    # databases without duplicating anything on a clean migration chain.
    op.execute("ALTER TABLE evidence_revisions ADD COLUMN IF NOT EXISTS parent_revision_id UUID")
    op.execute(
        "ALTER TABLE evidence_revisions ADD COLUMN IF NOT EXISTS client_request_id VARCHAR(200)"
    )
    op.execute("ALTER TABLE evidence_revisions ADD COLUMN IF NOT EXISTS request_hash VARCHAR(64)")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_evidence_revisions_parent_revision_id_evidence_revisions'
            ) THEN
                ALTER TABLE evidence_revisions
                ADD CONSTRAINT fk_evidence_revisions_parent_revision_id_evidence_revisions
                FOREIGN KEY (parent_revision_id) REFERENCES evidence_revisions(id)
                ON DELETE RESTRICT;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_evidence_revisions_client_request_id'
            ) THEN
                ALTER TABLE evidence_revisions
                ADD CONSTRAINT uq_evidence_revisions_client_request_id
                UNIQUE (client_request_id);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_evidence_revisions_request_hash_sha256_length'
            ) THEN
                ALTER TABLE evidence_revisions
                ADD CONSTRAINT ck_evidence_revisions_request_hash_sha256_length
                CHECK (request_hash IS NULL OR length(request_hash) = 64);
            END IF;
        END $$
        """
    )

    op.create_table(
        "evidence_search_projections",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_revision_id", sa.Uuid(), nullable=False),
        sa.Column("projection_text", sa.Text(), nullable=False),
        sa.Column("lexical_terms", JSONB, nullable=False),
        sa.Column("embedding", Vector(256), nullable=False),
        sa.Column("algorithm_name", sa.String(100), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False),
        sa.Column("evidence_content_hash", sa.String(64), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "length(evidence_content_hash) = 64",
            name="ck_search_projection_content_hash",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["studies.id"],
            name="fk_search_projection_study",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_revision_id"],
            ["evidence_revisions.id"],
            name="fk_search_projection_evidence_revision",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_search_projections"),
        sa.UniqueConstraint(
            "evidence_revision_id",
            name="uq_search_projection_evidence_revision",
        ),
    )
    op.create_index(
        "ix_evidence_search_projections_study",
        "evidence_search_projections",
        ["study_id"],
    )
    op.create_index(
        "ix_evidence_search_projections_embedding_hnsw",
        "evidence_search_projections",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "context_manifests",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("result_limit", sa.Integer(), nullable=False),
        sa.Column("profile_name", sa.String(100), nullable=False),
        sa.Column("profile_version", sa.String(50), nullable=False),
        sa.Column("lexical_algorithm", sa.String(100), nullable=False),
        sa.Column("vector_algorithm", sa.String(100), nullable=False),
        sa.Column("fusion_algorithm", sa.String(100), nullable=False),
        sa.Column("query_handling", sa.String(50), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "purpose IN ('support', 'counterevidence', 'explore')",
            name="ck_context_manifests_valid_purpose",
        ),
        sa.CheckConstraint(
            "result_limit > 0 AND result_limit <= 50",
            name="ck_context_manifests_valid_result_limit",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_context_manifests_content_hash_sha256_length",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_context_manifests_request_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["studies.id"],
            name="fk_context_manifests_study_id_studies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_context_manifests"),
        sa.UniqueConstraint("client_request_id", name="uq_context_manifests_client_request_id"),
    )
    op.create_index(
        "ix_context_manifests_study_created",
        "context_manifests",
        ["study_id", "created_at"],
    )

    op.create_table(
        "context_manifest_items",
        sa.Column("context_manifest_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("evidence_unit_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_review_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_content_hash", sa.String(64), nullable=False),
        sa.Column("source_content_hash", sa.String(64), nullable=False),
        sa.Column("context_url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("evidence_snapshot", JSONB, nullable=False),
        sa.Column("review_snapshot", JSONB, nullable=False),
        sa.Column("lexical_score", sa.Float(), nullable=False),
        sa.Column("vector_score", sa.Float(), nullable=False),
        sa.Column("hybrid_score", sa.Float(), nullable=False),
        sa.Column("lexical_rank", sa.Integer(), nullable=False),
        sa.Column("vector_rank", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ordinal > 0", name="ck_context_manifest_items_positive_ordinal"),
        sa.CheckConstraint(
            "lexical_score >= 0", name="ck_context_manifest_items_nonnegative_lexical_score"
        ),
        sa.CheckConstraint(
            "vector_score >= -1 AND vector_score <= 1",
            name="ck_context_manifest_items_vector_score_range",
        ),
        sa.CheckConstraint(
            "hybrid_score >= 0", name="ck_context_manifest_items_nonnegative_hybrid_score"
        ),
        sa.CheckConstraint(
            "lexical_rank > 0 AND vector_rank > 0",
            name="ck_context_manifest_items_positive_ranks",
        ),
        sa.CheckConstraint(
            "length(evidence_content_hash) = 64",
            name="ck_manifest_items_evidence_hash",
        ),
        sa.CheckConstraint(
            "length(source_content_hash) = 64",
            name="ck_manifest_items_source_hash",
        ),
        sa.ForeignKeyConstraint(
            ["context_manifest_id"],
            ["context_manifests.id"],
            name="fk_manifest_items_manifest",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_unit_id"],
            ["evidence_units.id"],
            name="fk_manifest_items_evidence_unit",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_revision_id"],
            ["evidence_revisions.id"],
            name="fk_manifest_items_evidence_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_manifest_items_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id"],
            ["source_revisions.id"],
            name="fk_manifest_items_source_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_review_id"],
            ["evidence_reviews.id"],
            name="fk_manifest_items_evidence_review",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_context_manifest_items"),
        sa.UniqueConstraint(
            "context_manifest_id",
            "ordinal",
            name="uq_context_manifest_items_manifest_ordinal",
        ),
        sa.UniqueConstraint(
            "context_manifest_id",
            "evidence_revision_id",
            name="uq_context_manifest_items_manifest_evidence_revision",
        ),
    )
    op.create_index(
        "ix_context_manifest_items_manifest",
        "context_manifest_items",
        ["context_manifest_id", "ordinal"],
    )

    for table in ("context_manifests", "context_manifest_items"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_immutable_revision_update()"
        )


def downgrade() -> None:
    for table in ("context_manifest_items", "context_manifests"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.drop_index("ix_context_manifest_items_manifest", table_name="context_manifest_items")
    op.drop_table("context_manifest_items")
    op.drop_index("ix_context_manifests_study_created", table_name="context_manifests")
    op.drop_table("context_manifests")
    op.drop_index(
        "ix_evidence_search_projections_embedding_hnsw",
        table_name="evidence_search_projections",
    )
    op.drop_index(
        "ix_evidence_search_projections_study",
        table_name="evidence_search_projections",
    )
    op.drop_table("evidence_search_projections")
    # Do not drop the shared vector extension; another application table may use it.
