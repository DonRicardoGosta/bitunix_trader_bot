"""initial schema

Revision ID: 20260513_0001
Revises:
Create Date: 2026-05-13

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260513_0001"
down_revision = None
branch_labels = None
depends_on = None


order_side = sa.Enum("BUY", "SELL", name="order_side")
order_type = sa.Enum("MARKET", "LIMIT", name="order_type")
order_status = sa.Enum(
    "NEW", "FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED", "EXPIRED",
    name="order_status",
)


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_order_id", sa.String(64), nullable=False, unique=True),
        sa.Column("bitunix_order_id", sa.String(64), nullable=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", order_side, nullable=False),
        sa.Column("type", order_type, nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("price", sa.Numeric(28, 12), nullable=True),
        sa.Column("leverage", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", order_status, nullable=False, server_default="NEW"),
        sa.Column("reduce_only", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("raw_response", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_orders_symbol", "orders", ["symbol"])
    op.create_index("ix_orders_bitunix_order_id", "orders", ["bitunix_order_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", order_side, nullable=False),
        sa.Column("entry_price", sa.Numeric(28, 12), nullable=False),
        sa.Column("mark_price", sa.Numeric(28, 12), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(28, 12), nullable=False),
        sa.Column("leverage", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_position_snapshots_symbol", "position_snapshots", ["symbol"])

    op.create_table(
        "market_ticks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("price", sa.Numeric(28, 12), nullable=False),
        sa.Column("volume", sa.Numeric(28, 12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_market_ticks_symbol_ts", "market_ticks", ["symbol", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_market_ticks_symbol_ts", table_name="market_ticks")
    op.drop_table("market_ticks")
    op.drop_index("ix_position_snapshots_symbol", table_name="position_snapshots")
    op.drop_table("position_snapshots")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_bitunix_order_id", table_name="orders")
    op.drop_index("ix_orders_symbol", table_name="orders")
    op.drop_table("orders")
    order_status.drop(op.get_bind(), checkfirst=True)
    order_type.drop(op.get_bind(), checkfirst=True)
    order_side.drop(op.get_bind(), checkfirst=True)
