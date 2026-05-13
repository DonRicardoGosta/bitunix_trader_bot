"""strategies and audit events

Revision ID: 20260513_0002
Revises: 20260513_0001
Create Date: 2026-05-13

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260513_0002"
down_revision = "20260513_0001"
branch_labels = None
depends_on = None


audit_level = sa.Enum("DEBUG", "INFO", "WARNING", "ERROR", name="audit_level")
strategy_run_status = sa.Enum(
    "RUNNING", "SUCCESS", "NO_OP", "FAILED", name="strategy_run_status"
)


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("strategy_name", sa.String(64), nullable=True),
    )
    op.create_index("ix_orders_strategy_name", "orders", ["strategy_name"])
    op.create_index(
        "ix_orders_strategy_symbol_ts",
        "orders",
        ["strategy_name", "symbol", "created_at"],
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("level", audit_level, nullable=False, server_default="INFO"),
        sa.Column("event", sa.String(128), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("strategy_name", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_events_event_ts", "audit_events", ["event", "created_at"])
    op.create_index("ix_audit_events_level_ts", "audit_events", ["level", "created_at"])
    op.create_index("ix_audit_events_strategy_name", "audit_events", ["strategy_name"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    op.create_table(
        "strategy_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("strategy_name", sa.String(64), nullable=False),
        sa.Column(
            "status",
            strategy_run_status,
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column(
            "triggered_by", sa.String(32), nullable=False, server_default="scheduler"
        ),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_strategy_runs_strategy_name", "strategy_runs", ["strategy_name"])
    op.create_index(
        "ix_strategy_runs_name_ts", "strategy_runs", ["strategy_name", "started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_runs_name_ts", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_strategy_name", table_name="strategy_runs")
    op.drop_table("strategy_runs")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_strategy_name", table_name="audit_events")
    op.drop_index("ix_audit_events_level_ts", table_name="audit_events")
    op.drop_index("ix_audit_events_event_ts", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_orders_strategy_symbol_ts", table_name="orders")
    op.drop_index("ix_orders_strategy_name", table_name="orders")
    op.drop_column("orders", "strategy_name")
    strategy_run_status.drop(op.get_bind(), checkfirst=True)
    audit_level.drop(op.get_bind(), checkfirst=True)
