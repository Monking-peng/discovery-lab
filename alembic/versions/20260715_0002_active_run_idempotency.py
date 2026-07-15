"""Prevent concurrent duplicate runs for one immutable input profile."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260715_0002"
down_revision: str | None = "20260715_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_runs_active_source_input_hash",
        "runs",
        ["source_id", "input_hash"],
        unique=True,
        postgresql_where="status IN ('RUNNING', 'SUCCEEDED')",
    )


def downgrade() -> None:
    op.drop_index("uq_runs_active_source_input_hash", table_name="runs")
