"""tpsl calibrations

Revision ID: 20260513_0003
Revises: 20260513_0002
Create Date: 2026-05-13

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260513_0003"
down_revision = "20260513_0002"
branch_labels = None
depends_on = None


calibration_status = sa.Enum(
    "RUNNING", "SUCCESS", "FAILED", name="calibration_status"
)


def upgrade() -> None:
    op.create_table(
        "tpsl_calibrations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "status", calibration_status, nullable=False, server_default="RUNNING"
        ),
        sa.Column(
            "triggered_by", sa.String(32), nullable=False, server_default="scheduler"
        ),
        sa.Column("lookback_minutes", sa.Integer, nullable=False, server_default="120"),
        sa.Column("top_n", sa.Integer, nullable=False, server_default="20"),
        sa.Column("summary", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_tpsl_calibrations_status_ts",
        "tpsl_calibrations",
        ["status", "finished_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tpsl_calibrations_status_ts", table_name="tpsl_calibrations"
    )
    op.drop_table("tpsl_calibrations")
    calibration_status.drop(op.get_bind(), checkfirst=True)
