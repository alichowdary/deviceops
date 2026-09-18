"""Allow registered devices to exist before their first connection.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "devices",
        "first_seen_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "devices",
        "last_seen_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $deviceops$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM devices
                    WHERE first_seen_at IS NULL OR last_seen_at IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade revision 0005 while devices have NULL seen timestamps';
                END IF;
            END
            $deviceops$
            """
        )
    )
    op.alter_column(
        "devices",
        "last_seen_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "devices",
        "first_seen_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
