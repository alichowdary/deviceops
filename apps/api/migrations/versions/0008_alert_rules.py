"""Add owner-scoped alert rule definitions.

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("metric", sa.String(length=32), nullable=True),
        sa.Column("operator", sa.String(length=8), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("offline_after_seconds", sa.Integer(), nullable=True),
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
            "rule_type IN ('metric_threshold', 'device_offline')",
            name="ck_alert_rules_type",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_alert_rules_severity",
        ),
        sa.CheckConstraint(
            "metric IS NULL OR metric IN ('temperature_c', 'humidity_pct', "
            "'pressure_hpa', 'battery_pct', 'rssi_dbm')",
            name="ck_alert_rules_metric",
        ),
        sa.CheckConstraint(
            "operator IS NULL OR operator IN ('gt', 'gte', 'lt', 'lte')",
            name="ck_alert_rules_operator",
        ),
        sa.CheckConstraint(
            "((rule_type = 'metric_threshold' AND metric IS NOT NULL AND "
            "operator IS NOT NULL AND threshold IS NOT NULL AND "
            "offline_after_seconds IS NULL) OR "
            "(rule_type = 'device_offline' AND metric IS NULL AND "
            "operator IS NULL AND threshold IS NULL AND "
            "offline_after_seconds IS NOT NULL))",
            name="ck_alert_rules_shape",
        ),
        sa.CheckConstraint(
            "offline_after_seconds IS NULL OR "
            "offline_after_seconds BETWEEN 5 AND 604800",
            name="ck_alert_rules_offline_bounds",
        ),
        sa.CheckConstraint(
            "threshold IS NULL OR "
            "((metric = 'temperature_c' AND threshold BETWEEN -100 AND 200) OR "
            "(metric = 'humidity_pct' AND threshold BETWEEN 0 AND 100) OR "
            "(metric = 'pressure_hpa' AND threshold BETWEEN 0 AND 2000) OR "
            "(metric = 'battery_pct' AND threshold BETWEEN 0 AND 100) OR "
            "(metric = 'rssi_dbm' AND threshold BETWEEN -200 AND 0))",
            name="ck_alert_rules_threshold_bounds",
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
        "ix_alert_rules_owner_created_at",
        "alert_rules",
        ["owner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_alert_rules_device_id",
        "alert_rules",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_alert_rules_owner_enabled",
        "alert_rules",
        ["owner_id", "enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_rules_owner_enabled", table_name="alert_rules")
    op.drop_index("ix_alert_rules_device_id", table_name="alert_rules")
    op.drop_index(
        "ix_alert_rules_owner_created_at", table_name="alert_rules"
    )
    op.drop_table("alert_rules")
