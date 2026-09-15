"""Create the device command history table.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "commands",
        sa.Column("command_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("command_type", sa.String(length=32), nullable=False),
        sa.Column(
            "arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ack_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "command_type IN ('set_led', 'set_reporting_interval', "
            "'request_diagnostics')",
            name="ck_commands_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name="ck_commands_status",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("command_id"),
    )
    op.create_index(
        "ix_commands_device_issued_at",
        "commands",
        ["device_id", "issued_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_commands_device_issued_at", table_name="commands")
    op.drop_table("commands")
