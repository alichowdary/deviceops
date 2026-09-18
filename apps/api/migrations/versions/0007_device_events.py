"""Create the persistent owner-scoped device event feed.

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('device_registered', 'device_online', "
            "'device_offline', 'command_issued', 'command_succeeded', "
            "'command_failed')",
            name="ck_device_events_type",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'success', 'warning', 'error')",
            name="ck_device_events_severity",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_device_events_owner_occurred_at",
        "device_events",
        ["owner_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_device_events_device_occurred_at",
        "device_events",
        ["device_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_device_events_owner_type_occurred_at",
        "device_events",
        ["owner_id", "event_type", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_device_events_owner_type_occurred_at",
        table_name="device_events",
    )
    op.drop_index(
        "ix_device_events_device_occurred_at",
        table_name="device_events",
    )
    op.drop_index(
        "ix_device_events_owner_occurred_at",
        table_name="device_events",
    )
    op.drop_table("device_events")
