"""Track the current authenticated MQTT session for each device.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices", sa.Column("mqtt_session_id", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("devices", "mqtt_session_id")
