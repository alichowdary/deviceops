"""Add users and nullable device ownership fields.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.add_column(
        "devices", sa.Column("owner_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "devices", sa.Column("device_secret_hash", sa.String(length=255), nullable=True)
    )
    op.create_foreign_key(
        "fk_devices_owner_id_users",
        "devices",
        "users",
        ["owner_id"],
        ["id"],
    )
    op.create_index("ix_devices_owner_id", "devices", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_devices_owner_id", table_name="devices")
    op.drop_constraint(
        "fk_devices_owner_id_users", "devices", type_="foreignkey"
    )
    op.drop_column("devices", "device_secret_hash")
    op.drop_column("devices", "owner_id")
    op.drop_table("users")
