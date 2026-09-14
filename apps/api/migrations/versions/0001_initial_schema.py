"""Create devices and telemetry tables.

Revision ID: 0001
Revises:
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="unknown", nullable=False
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('unknown', 'online', 'offline')", name="ck_devices_status"
        ),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_table(
        "telemetry",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("battery_pct", sa.Float(), nullable=False),
        sa.Column("rssi_dbm", sa.Integer(), nullable=False),
        sa.Column("uptime_s", sa.BigInteger(), nullable=False),
        sa.Column(
            "additional_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_telemetry_sequence_positive"),
        sa.CheckConstraint(
            "battery_pct >= 0 AND battery_pct <= 100",
            name="ck_telemetry_battery_range",
        ),
        sa.CheckConstraint("uptime_s >= 0", name="ck_telemetry_uptime_nonnegative"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_telemetry_device_received_at",
        "telemetry",
        ["device_id", "received_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_device_received_at", table_name="telemetry")
    op.drop_table("telemetry")
    op.drop_table("devices")
