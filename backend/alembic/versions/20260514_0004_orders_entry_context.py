"""orders entry_context JSON for strategy placement audit

Revision ID: 20260514_0004
Revises: 20260513_0003
Create Date: 2026-05-14

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260514_0004"
down_revision = "20260513_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("entry_context", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "entry_context")
