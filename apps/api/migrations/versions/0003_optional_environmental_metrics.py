"""Add optional battery, humidity, and pressure telemetry.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "telemetry",
        "battery_pct",
        existing_type=sa.Float(),
        nullable=True,
    )
    op.add_column("telemetry", sa.Column("humidity_pct", sa.Float(), nullable=True))
    op.add_column("telemetry", sa.Column("pressure_hpa", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_telemetry_humidity_range",
        "telemetry",
        "humidity_pct IS NULL OR (humidity_pct >= 0 AND humidity_pct <= 100)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_telemetry_humidity_range", "telemetry", type_="check"
    )
    op.drop_column("telemetry", "pressure_hpa")
    op.drop_column("telemetry", "humidity_pct")
    op.execute(
        sa.text("UPDATE telemetry SET battery_pct = 0 WHERE battery_pct IS NULL")
    )
    op.alter_column(
        "telemetry",
        "battery_pct",
        existing_type=sa.Float(),
        nullable=False,
    )
