"""Allow capability-advertised numeric alert metrics.

Revision ID: 0012
Revises: 0011
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


METRIC_IDENTIFIER_CHECK = "metric IS NULL OR metric ~ '^[a-z][a-z0-9_]{0,63}$'"
FINITE_THRESHOLD_CHECK = (
    "threshold IS NULL OR threshold BETWEEN "
    "'-1.7976931348623157e308'::float8 AND "
    "'1.7976931348623157e308'::float8"
)
LEGACY_METRIC_CHECK = (
    "metric IS NULL OR metric IN ('temperature_c', 'humidity_pct', "
    "'pressure_hpa', 'battery_pct', 'rssi_dbm')"
)
LEGACY_THRESHOLD_CHECK = (
    "threshold IS NULL OR "
    "((metric = 'temperature_c' AND threshold BETWEEN -100 AND 200) OR "
    "(metric = 'humidity_pct' AND threshold BETWEEN 0 AND 100) OR "
    "(metric = 'pressure_hpa' AND threshold BETWEEN 0 AND 2000) OR "
    "(metric = 'battery_pct' AND threshold BETWEEN 0 AND 100) OR "
    "(metric = 'rssi_dbm' AND threshold BETWEEN -200 AND 0))"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_alert_rules_threshold_bounds", "alert_rules", type_="check"
    )
    op.drop_constraint("ck_alert_rules_metric", "alert_rules", type_="check")
    op.drop_constraint("ck_alerts_metric", "alerts", type_="check")
    op.alter_column(
        "alert_rules",
        "metric",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.alter_column(
        "alerts",
        "metric",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.create_check_constraint(
        "ck_alert_rules_metric", "alert_rules", METRIC_IDENTIFIER_CHECK
    )
    op.create_check_constraint(
        "ck_alert_rules_threshold_bounds",
        "alert_rules",
        FINITE_THRESHOLD_CHECK,
    )
    op.create_check_constraint(
        "ck_alerts_metric", "alerts", METRIC_IDENTIFIER_CHECK
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_alert_rules_threshold_bounds", "alert_rules", type_="check"
    )
    op.drop_constraint("ck_alert_rules_metric", "alert_rules", type_="check")
    op.drop_constraint("ck_alerts_metric", "alerts", type_="check")
    op.alter_column(
        "alert_rules",
        "metric",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=True,
    )
    op.alter_column(
        "alerts",
        "metric",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=True,
    )
    op.create_check_constraint(
        "ck_alert_rules_metric", "alert_rules", LEGACY_METRIC_CHECK
    )
    op.create_check_constraint(
        "ck_alert_rules_threshold_bounds",
        "alert_rules",
        LEGACY_THRESHOLD_CHECK,
    )
    op.create_check_constraint(
        "ck_alerts_metric", "alerts", LEGACY_METRIC_CHECK
    )
