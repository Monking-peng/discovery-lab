"""Add immutable Opportunity Drafts pinned to exact Claim Revisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0004"
down_revision: str | None = "20260716_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "opportunity_drafts",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("claim_revision_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("desired_outcome", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("assumptions", JSONB, nullable=False),
        sa.Column("risks", JSONB, nullable=False),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status = 'DRAFT'", name="ck_opportunity_drafts_valid_status"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_opportunity_drafts_confidence_range",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_opportunity_drafts_content_hash_sha256_length",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_opportunity_drafts_request_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["studies.id"],
            name="fk_opportunity_drafts_study_id_studies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            name="fk_opportunity_drafts_claim_id_claims",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claim_revision_id"],
            ["claim_revisions.id"],
            name="fk_opportunity_drafts_claim_revision_id_claim_revisions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_opportunity_drafts"),
        sa.UniqueConstraint("client_request_id", name="uq_opportunity_drafts_client_request_id"),
    )
    op.create_index(
        "ix_opportunity_drafts_study_created",
        "opportunity_drafts",
        ["study_id", "created_at"],
    )
    op.create_index(
        "ix_opportunity_drafts_claim_revision",
        "opportunity_drafts",
        ["claim_revision_id"],
    )
    op.execute(
        "CREATE TRIGGER trg_opportunity_drafts_immutable "
        "BEFORE UPDATE ON opportunity_drafts "
        "FOR EACH ROW EXECUTE FUNCTION reject_immutable_revision_update()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_opportunity_drafts_immutable ON opportunity_drafts")
    op.drop_index("ix_opportunity_drafts_claim_revision", table_name="opportunity_drafts")
    op.drop_index("ix_opportunity_drafts_study_created", table_name="opportunity_drafts")
    op.drop_table("opportunity_drafts")
