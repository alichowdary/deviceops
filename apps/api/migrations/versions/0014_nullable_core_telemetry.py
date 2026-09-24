"""Allow telemetry without historical first-class metrics.

Revision ID: 0014
Revises: 0013
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column_name, column_type in (
        ("temperature_c", sa.Float()),
        ("rssi_dbm", sa.Integer()),
        ("uptime_s", sa.BigInteger()),
    ):
        op.alter_column(
            "telemetry",
            column_name,
            existing_type=column_type,
            nullable=True,
        )


def downgrade() -> None:
    # PostgreSQL rejects this downgrade when nullable-era rows contain NULL.
    # That is intentional: do not fabricate sensor readings to force it.
    for column_name, column_type in (
        ("temperature_c", sa.Float()),
        ("rssi_dbm", sa.Integer()),
        ("uptime_s", sa.BigInteger()),
    ):
        op.alter_column(
            "telemetry",
            column_name,
            existing_type=column_type,
            nullable=False,
        )
