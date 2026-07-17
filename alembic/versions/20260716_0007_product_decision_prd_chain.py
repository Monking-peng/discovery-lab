"""Add immutable Hypothesis, Experiment, Decision, and cited PRD artifacts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0007"
down_revision: str | None = "20260716_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def _identity_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    hypothesis_id, hypothesis_created = _identity_columns()
    op.create_table(
        "hypotheses",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("claim_revision_id", sa.Uuid(), nullable=False),
        sa.Column("context_manifest_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("expected_outcome", sa.Text(), nullable=False),
        sa.Column("falsification_criterion", sa.Text(), nullable=False),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        hypothesis_id,
        hypothesis_created,
        sa.CheckConstraint("status = 'DRAFT'", name="ck_hypotheses_valid_status"),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_hypotheses_content_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"], ["studies.id"], name="fk_hypotheses_study_id_studies", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_hypotheses_run_id_runs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["claims.id"], name="fk_hypotheses_claim_id_claims", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["claim_revision_id"],
            ["claim_revisions.id"],
            name="fk_hypotheses_claim_revision_id_claim_revisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["context_manifest_id"],
            ["context_manifests.id"],
            name="fk_hypotheses_context_manifest_id_context_manifests",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hypotheses"),
        sa.UniqueConstraint("run_id", name="uq_hypotheses_run_id"),
    )
    op.create_index("ix_hypotheses_study_created", "hypotheses", ["study_id", "created_at"])

    experiment_id, experiment_created = _identity_columns()
    op.create_table(
        "experiments",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("hypothesis_id", sa.Uuid(), nullable=False),
        sa.Column("tool_call_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("target_cohort", sa.Text(), nullable=False),
        sa.Column("primary_metric", sa.Text(), nullable=False),
        sa.Column("success_threshold", sa.Text(), nullable=False),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        experiment_id,
        experiment_created,
        sa.CheckConstraint("status = 'DRAFT'", name="ck_experiments_valid_status"),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_experiments_content_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"], ["studies.id"], name="fk_experiments_study_id_studies", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["hypothesis_id"],
            ["hypotheses.id"],
            name="fk_experiments_hypothesis_id_hypotheses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_call_id"],
            ["tool_calls.id"],
            name="fk_experiments_tool_call_id_tool_calls",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_experiments"),
        sa.UniqueConstraint("hypothesis_id", name="uq_experiments_hypothesis_id"),
        sa.UniqueConstraint("tool_call_id", name="uq_experiments_tool_call_id"),
    )
    op.create_index("ix_experiments_study_created", "experiments", ["study_id", "created_at"])

    decision_id, decision_created = _identity_columns()
    op.create_table(
        "product_decisions",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("observed_result", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        decision_id,
        decision_created,
        sa.CheckConstraint(
            "decision IN ('PROCEED', 'ITERATE', 'STOP')",
            name="ck_product_decisions_valid_decision",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_product_decisions_content_hash_sha256_length",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_product_decisions_request_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["studies.id"],
            name="fk_product_decisions_study_id_studies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name="fk_product_decisions_experiment_id_experiments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_decisions"),
        sa.UniqueConstraint(
            "client_request_id",
            name="uq_product_decisions_client_request_id",
        ),
    )
    op.create_index(
        "ix_product_decisions_experiment_created",
        "product_decisions",
        ["experiment_id", "created_at"],
    )
    op.create_index(
        "ix_product_decisions_study_created",
        "product_decisions",
        ["study_id", "created_at"],
    )

    prd_id, prd_created = _identity_columns()
    op.create_table(
        "prd_artifacts",
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sections", JSONB, nullable=False),
        sa.Column("citations", JSONB, nullable=False),
        sa.Column("publication_blockers", JSONB, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        prd_id,
        prd_created,
        sa.CheckConstraint("status = 'DRAFT'", name="ck_prd_artifacts_valid_status"),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_prd_artifacts_content_hash_sha256_length",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_prd_artifacts_request_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["studies.id"],
            name="fk_prd_artifacts_study_id_studies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["product_decisions.id"],
            name="fk_prd_artifacts_decision_id_product_decisions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prd_artifacts"),
        sa.UniqueConstraint("client_request_id", name="uq_prd_artifacts_client_request_id"),
    )
    op.create_index(
        "ix_prd_artifacts_decision_created",
        "prd_artifacts",
        ["decision_id", "created_at"],
    )
    op.create_index(
        "ix_prd_artifacts_study_created",
        "prd_artifacts",
        ["study_id", "created_at"],
    )

    for table in ("hypotheses", "experiments", "product_decisions", "prd_artifacts"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_immutable_revision_update()"
        )


def downgrade() -> None:
    for table in ("prd_artifacts", "product_decisions", "experiments", "hypotheses"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.drop_index("ix_prd_artifacts_study_created", table_name="prd_artifacts")
    op.drop_index("ix_prd_artifacts_decision_created", table_name="prd_artifacts")
    op.drop_table("prd_artifacts")
    op.drop_index("ix_product_decisions_study_created", table_name="product_decisions")
    op.drop_index("ix_product_decisions_experiment_created", table_name="product_decisions")
    op.drop_table("product_decisions")
    op.drop_index("ix_experiments_study_created", table_name="experiments")
    op.drop_table("experiments")
    op.drop_index("ix_hypotheses_study_created", table_name="hypotheses")
    op.drop_table("hypotheses")
