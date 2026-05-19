"""tpsl_calibration_symbol_runs — per-coin backtest rows

Revision ID: 20260519_0006
Revises: 20260516_0005
Create Date: 2026-05-19

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260519_0006"
down_revision = "20260516_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tpsl_calibration_symbol_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "calibration_id",
            sa.Integer(),
            sa.ForeignKey("tpsl_calibrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("scan_rank", sa.Integer(), nullable=False),
        sa.Column("abs_change_24h_pct", sa.Numeric(12, 4), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("is_qualified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("kline_samples", sa.Integer(), nullable=True),
        sa.Column("best_variation_label", sa.String(length=32), nullable=True),
        sa.Column("best_tp_roi_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("best_sl_roi_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("best_win_rate_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("max_win_rate_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("best_total_trades", sa.Integer(), nullable=True),
        sa.Column("best_tp_wins", sa.Integer(), nullable=True),
        sa.Column("best_sl_losses", sa.Integer(), nullable=True),
        sa.Column("best_no_result", sa.Integer(), nullable=True),
        sa.Column("tp_move_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("sl_move_pct", sa.Numeric(12, 6), nullable=True),
        sa.Column("variations", sa.JSON(), nullable=True),
        sa.Column("fetch_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "calibration_id",
            "symbol",
            name="uq_tpsl_cal_symbol_runs_cal_symbol",
        ),
    )
    op.create_index(
        "ix_tpsl_calibration_symbol_runs_calibration_id",
        "tpsl_calibration_symbol_runs",
        ["calibration_id"],
    )
    op.create_index(
        "ix_tpsl_calibration_symbol_runs_symbol",
        "tpsl_calibration_symbol_runs",
        ["symbol"],
    )
    op.create_index(
        "ix_tpsl_cal_symbol_runs_cal_qualified",
        "tpsl_calibration_symbol_runs",
        ["calibration_id", "is_qualified"],
    )
    op.create_index(
        "ix_tpsl_cal_symbol_runs_cal_rank",
        "tpsl_calibration_symbol_runs",
        ["calibration_id", "scan_rank"],
    )
    op.create_index(
        "ix_tpsl_cal_symbol_runs_cal_best_wr",
        "tpsl_calibration_symbol_runs",
        ["calibration_id", "best_win_rate_pct"],
    )
    op.create_index(
        "ix_tpsl_cal_symbol_runs_symbol_cal",
        "tpsl_calibration_symbol_runs",
        ["symbol", "calibration_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tpsl_cal_symbol_runs_symbol_cal",
        table_name="tpsl_calibration_symbol_runs",
    )
    op.drop_index(
        "ix_tpsl_cal_symbol_runs_cal_best_wr",
        table_name="tpsl_calibration_symbol_runs",
    )
    op.drop_index(
        "ix_tpsl_cal_symbol_runs_cal_rank",
        table_name="tpsl_calibration_symbol_runs",
    )
    op.drop_index(
        "ix_tpsl_cal_symbol_runs_cal_qualified",
        table_name="tpsl_calibration_symbol_runs",
    )
    op.drop_index(
        "ix_tpsl_calibration_symbol_runs_symbol",
        table_name="tpsl_calibration_symbol_runs",
    )
    op.drop_index(
        "ix_tpsl_calibration_symbol_runs_calibration_id",
        table_name="tpsl_calibration_symbol_runs",
    )
    op.drop_table("tpsl_calibration_symbol_runs")
