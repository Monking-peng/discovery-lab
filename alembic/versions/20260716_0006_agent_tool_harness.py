"""Add persisted Agent Runs, Tool Calls, and exact HITL approvals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0006"
down_revision: str | None = "20260716_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("runs", sa.Column("client_request_id", sa.String(200), nullable=True))
    op.add_column("runs", sa.Column("request_hash", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_runs_client_request_id",
        "runs",
        ["client_request_id"],
    )
    op.create_check_constraint(
        "ck_runs_request_hash_sha256_length",
        "runs",
        "request_hash IS NULL OR length(request_hash) = 64",
    )

    op.create_table(
        "tool_calls",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("run_step_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_version", sa.String(50), nullable=False),
        sa.Column("access_mode", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("arguments", JSONB, nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("policy_snapshot", JSONB, nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "access_mode IN ('read', 'write')",
            name="ck_tool_calls_valid_access_mode",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_tool_calls_valid_risk_level",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'APPROVAL_REQUIRED', 'SUCCEEDED', 'REJECTED', 'FAILED')",
            name="ck_tool_calls_valid_status",
        ),
        sa.CheckConstraint(
            "length(arguments_hash) = 64",
            name="ck_tool_calls_arguments_hash_sha256_length",
        ),
        sa.CheckConstraint(
            "result_hash IS NULL OR length(result_hash) = 64",
            name="ck_tool_calls_result_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name="fk_tool_calls_run_id_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_step_id"],
            ["run_steps.id"],
            name="fk_tool_calls_run_step_id_run_steps",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tool_calls"),
    )
    op.create_index("ix_tool_calls_run_created", "tool_calls", ["run_id", "created_at"])
    op.create_index("ix_tool_calls_step", "tool_calls", ["run_step_id"])

    op.create_table(
        "tool_approvals",
        sa.Column("tool_call_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("reviewer", sa.String(200), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("client_request_id", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('APPROVE', 'REJECT')",
            name="ck_tool_approvals_valid_decision",
        ),
        sa.CheckConstraint(
            "length(arguments_hash) = 64",
            name="ck_tool_approvals_arguments_hash_sha256_length",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_tool_approvals_request_hash_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["tool_call_id"],
            ["tool_calls.id"],
            name="fk_tool_approvals_tool_call_id_tool_calls",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tool_approvals"),
        sa.UniqueConstraint("tool_call_id", name="uq_tool_approvals_tool_call_id"),
        sa.UniqueConstraint("client_request_id", name="uq_tool_approvals_client_request_id"),
    )
    op.create_index(
        "ix_tool_approvals_tool_call",
        "tool_approvals",
        ["tool_call_id", "created_at"],
    )

    op.execute(
        """
        CREATE FUNCTION reject_tool_call_contract_update() RETURNS trigger AS $$
        BEGIN
            IF NEW.tool_name IS DISTINCT FROM OLD.tool_name
               OR NEW.tool_version IS DISTINCT FROM OLD.tool_version
               OR NEW.access_mode IS DISTINCT FROM OLD.access_mode
               OR NEW.risk_level IS DISTINCT FROM OLD.risk_level
               OR NEW.arguments IS DISTINCT FROM OLD.arguments
               OR NEW.arguments_hash IS DISTINCT FROM OLD.arguments_hash
               OR NEW.policy_snapshot IS DISTINCT FROM OLD.policy_snapshot
               OR NEW.requires_approval IS DISTINCT FROM OLD.requires_approval THEN
                RAISE EXCEPTION 'tool call contract is immutable; create a new tool call'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_tool_calls_contract_immutable BEFORE UPDATE ON tool_calls "
        "FOR EACH ROW EXECUTE FUNCTION reject_tool_call_contract_update()"
    )
    op.execute(
        "CREATE TRIGGER trg_tool_approvals_immutable BEFORE UPDATE ON tool_approvals "
        "FOR EACH ROW EXECUTE FUNCTION reject_immutable_revision_update()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tool_approvals_immutable ON tool_approvals")
    op.execute("DROP TRIGGER IF EXISTS trg_tool_calls_contract_immutable ON tool_calls")
    op.execute("DROP FUNCTION IF EXISTS reject_tool_call_contract_update()")
    op.drop_index("ix_tool_approvals_tool_call", table_name="tool_approvals")
    op.drop_table("tool_approvals")
    op.drop_index("ix_tool_calls_step", table_name="tool_calls")
    op.drop_index("ix_tool_calls_run_created", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_constraint("ck_runs_request_hash_sha256_length", "runs", type_="check")
    op.drop_constraint("uq_runs_client_request_id", "runs", type_="unique")
    op.drop_column("runs", "request_hash")
    op.drop_column("runs", "client_request_id")
