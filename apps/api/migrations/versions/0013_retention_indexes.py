"""Add global timestamp indexes for rolling retention.

Revision ID: 0013
Revises: 0012
"""

from typing import Sequence

from alembic import op


revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_telemetry_received_at",
        "telemetry",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        "ix_device_events_occurred_at",
        "device_events",
        ["occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_device_events_occurred_at", table_name="device_events")
    op.drop_index("ix_telemetry_received_at", table_name="telemetry")
