"""Add optional device display names.

Revision ID: 0011
Revises: 0010
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("display_name", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("devices", "display_name")
