"""app_runtime_settings key-value overrides

Revision ID: 20260516_0005
Revises: 20260514_0004
Create Date: 2026-05-16

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260516_0005"
down_revision = "20260514_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_runtime_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_runtime_settings")
