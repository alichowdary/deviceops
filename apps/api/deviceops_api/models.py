"""Database models for DeviceOps users, devices, data, events, and rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_owner_id", "owner_id"),)

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    device_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mqtt_session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    capabilities_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    offline_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DeviceEvent(Base):
    __tablename__ = "device_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('device_registered', 'device_online', "
            "'device_offline', 'command_issued', 'command_succeeded', "
            "'command_failed', 'alert_opened', 'alert_resolved')",
            name="ck_device_events_type",
        ),
        CheckConstraint(
            "severity IN ('info', 'success', 'warning', 'error')",
            name="ck_device_events_severity",
        ),
        Index(
            "ix_device_events_owner_occurred_at",
            "owner_id",
            "occurred_at",
        ),
        Index(
            "ix_device_events_device_occurred_at",
            "device_id",
            "occurred_at",
        ),
        Index(
            "ix_device_events_owner_type_occurred_at",
            "owner_id",
            "event_type",
            "occurred_at",
        ),
        Index("ix_device_events_occurred_at", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('metric_threshold', 'device_offline')",
            name="ck_alert_rules_type",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_alert_rules_severity",
        ),
        CheckConstraint(
            "metric IS NULL OR metric ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="ck_alert_rules_metric",
        ),
        CheckConstraint(
            "operator IS NULL OR operator IN ('gt', 'gte', 'lt', 'lte')",
            name="ck_alert_rules_operator",
        ),
        CheckConstraint(
            "((rule_type = 'metric_threshold' AND metric IS NOT NULL AND "
            "operator IS NOT NULL AND threshold IS NOT NULL AND "
            "offline_after_seconds IS NULL) OR "
            "(rule_type = 'device_offline' AND metric IS NULL AND "
            "operator IS NULL AND threshold IS NULL AND "
            "offline_after_seconds IS NOT NULL))",
            name="ck_alert_rules_shape",
        ),
        CheckConstraint(
            "offline_after_seconds IS NULL OR "
            "offline_after_seconds BETWEEN 5 AND 604800",
            name="ck_alert_rules_offline_bounds",
        ),
        CheckConstraint(
            "threshold IS NULL OR threshold BETWEEN "
            "'-1.7976931348623157e308'::float8 AND "
            "'1.7976931348623157e308'::float8",
            name="ck_alert_rules_threshold_bounds",
        ),
        Index(
            "ix_alert_rules_owner_created_at", "owner_id", "created_at"
        ),
        Index("ix_alert_rules_device_id", "device_id"),
        Index("ix_alert_rules_owner_enabled", "owner_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    metric: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(8), nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    offline_after_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('metric_threshold', 'device_offline')",
            name="ck_alerts_rule_type",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_alerts_severity",
        ),
        CheckConstraint(
            "status IN ('active', 'resolved')",
            name="ck_alerts_status",
        ),
        CheckConstraint(
            "metric IS NULL OR metric ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="ck_alerts_metric",
        ),
        CheckConstraint(
            "operator IS NULL OR operator IN ('gt', 'gte', 'lt', 'lte')",
            name="ck_alerts_operator",
        ),
        CheckConstraint(
            "((rule_type = 'metric_threshold' AND metric IS NOT NULL AND "
            "operator IS NOT NULL AND threshold IS NOT NULL AND "
            "offline_after_seconds IS NULL) OR "
            "(rule_type = 'device_offline' AND metric IS NULL AND "
            "operator IS NULL AND threshold IS NULL AND "
            "offline_after_seconds IS NOT NULL))",
            name="ck_alerts_rule_shape",
        ),
        CheckConstraint(
            "((status = 'active' AND resolved_at IS NULL AND "
            "resolution_reason IS NULL) OR "
            "(status = 'resolved' AND resolved_at IS NOT NULL AND "
            "resolution_reason IS NOT NULL))",
            name="ck_alerts_lifecycle",
        ),
        Index(
            "ix_alerts_owner_status_opened_at",
            "owner_id",
            "status",
            "opened_at",
        ),
        Index("ix_alerts_device_opened_at", "device_id", "opened_at"),
        Index("ix_alerts_rule_opened_at", "rule_id", "opened_at"),
        Index(
            "uq_alerts_active_rule",
            "rule_id",
            unique=True,
            postgresql_where=text(
                "status = 'active' AND rule_id IS NOT NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("alert_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    condition: Mapped[str] = mapped_column(String(255), nullable=False)
    metric: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(8), nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    offline_after_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        Index("ix_telemetry_device_received_at", "device_id", "received_at"),
        Index("ix_telemetry_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    rssi_dbm: Mapped[int] = mapped_column(Integer, nullable=False)
    uptime_s: Mapped[int] = mapped_column(BigInteger, nullable=False)
    additional_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class DeviceCommand(Base):
    __tablename__ = "commands"
    __table_args__ = (
        Index("ix_commands_device_issued_at", "device_id", "issued_at"),
    )

    command_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ack_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
