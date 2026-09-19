"""Add persistent alert lifecycle state and offline timing.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("offline_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE devices SET offline_since = last_seen_at "
        "WHERE status = 'offline' AND last_seen_at IS NOT NULL"
    )

    op.drop_constraint(
        "ck_device_events_type", "device_events", type_="check"
    )
    op.create_check_constraint(
        "ck_device_events_type",
        "device_events",
        "event_type IN ('device_registered', 'device_online', "
        "'device_offline', 'command_issued', 'command_succeeded', "
        "'command_failed', 'alert_opened', 'alert_resolved')",
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=True),
        sa.Column("rule_name", sa.String(length=100), nullable=True),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("condition", sa.String(length=255), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=True),
        sa.Column("operator", sa.String(length=8), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("offline_after_seconds", sa.Integer(), nullable=True),
        sa.Column("observed_value", sa.Float(), nullable=True),
        sa.Column("resolved_value", sa.Float(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_reason", sa.String(length=64), nullable=True),
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
            name="ck_alerts_rule_type",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_alerts_severity",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'resolved')",
            name="ck_alerts_status",
        ),
        sa.CheckConstraint(
            "metric IS NULL OR metric IN ('temperature_c', 'humidity_pct', "
            "'pressure_hpa', 'battery_pct', 'rssi_dbm')",
            name="ck_alerts_metric",
        ),
        sa.CheckConstraint(
            "operator IS NULL OR operator IN ('gt', 'gte', 'lt', 'lte')",
            name="ck_alerts_operator",
        ),
        sa.CheckConstraint(
            "((rule_type = 'metric_threshold' AND metric IS NOT NULL AND "
            "operator IS NOT NULL AND threshold IS NOT NULL AND "
            "offline_after_seconds IS NULL) OR "
            "(rule_type = 'device_offline' AND metric IS NULL AND "
            "operator IS NULL AND threshold IS NULL AND "
            "offline_after_seconds IS NOT NULL))",
            name="ck_alerts_rule_shape",
        ),
        sa.CheckConstraint(
            "((status = 'active' AND resolved_at IS NULL AND "
            "resolution_reason IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL AND "
            "resolution_reason IS NOT NULL))",
            name="ck_alerts_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["alert_rules.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_alerts_owner_status_opened_at",
        "alerts",
        ["owner_id", "status", "opened_at"],
        unique=False,
    )
    op.create_index(
        "ix_alerts_device_opened_at",
        "alerts",
        ["device_id", "opened_at"],
        unique=False,
    )
    op.create_index(
        "ix_alerts_rule_opened_at",
        "alerts",
        ["rule_id", "opened_at"],
        unique=False,
    )
    op.create_index(
        "uq_alerts_active_rule",
        "alerts",
        ["rule_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'active' AND rule_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_alerts_active_rule", table_name="alerts")
    op.drop_index("ix_alerts_rule_opened_at", table_name="alerts")
    op.drop_index("ix_alerts_device_opened_at", table_name="alerts")
    op.drop_index("ix_alerts_owner_status_opened_at", table_name="alerts")
    op.drop_table("alerts")

    op.drop_constraint(
        "ck_device_events_type", "device_events", type_="check"
    )
    op.create_check_constraint(
        "ck_device_events_type",
        "device_events",
        "event_type IN ('device_registered', 'device_online', "
        "'device_offline', 'command_issued', 'command_succeeded', "
        "'command_failed')",
    )
    op.drop_column("devices", "offline_since")
