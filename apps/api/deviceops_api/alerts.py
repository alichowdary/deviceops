"""Persistent alert evaluation, lifecycle changes, and safe realtime messages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .events import create_device_event, event_created_message
from .models import Alert, AlertRule, Device
from .realtime import realtime_hub


logger = logging.getLogger(__name__)

METRIC_LABELS = {
    "temperature_c": ("Temperature", "°C"),
    "humidity_pct": ("Humidity", "%"),
    "pressure_hpa": ("Pressure", "hPa"),
    "battery_pct": ("Battery", "%"),
    "rssi_dbm": ("Signal strength", "dBm"),
}
OPERATOR_LABELS = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}
OPEN_EVENT_SEVERITY = {
    "info": "info",
    "warning": "warning",
    "critical": "error",
}


@dataclass(frozen=True)
class AlertLifecycleChange:
    owner_id: int
    alert_message: dict[str, Any]
    event_message: dict[str, Any]


def _utc_isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_duration(seconds: int) -> str:
    if seconds % 86_400 == 0:
        value = seconds // 86_400
        return f"{value} {'day' if value == 1 else 'days'}"
    if seconds % 3_600 == 0:
        value = seconds // 3_600
        return f"{value} {'hour' if value == 1 else 'hours'}"
    if seconds % 60 == 0:
        value = seconds // 60
        return f"{value} {'minute' if value == 1 else 'minutes'}"
    return f"{seconds} {'second' if seconds == 1 else 'seconds'}"


def rule_condition(rule: AlertRule) -> str:
    if rule.rule_type == "device_offline":
        return f"Offline for {_format_duration(rule.offline_after_seconds or 0)}"
    label, unit = METRIC_LABELS[rule.metric or "temperature_c"]
    operator = OPERATOR_LABELS[rule.operator or "gt"]
    return f"{label} {operator} {rule.threshold:g} {unit}"


def alert_data(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "device_id": alert.device_id,
        "rule_id": alert.rule_id,
        "rule_name": alert.rule_name,
        "rule_type": alert.rule_type,
        "severity": alert.severity,
        "status": alert.status,
        "condition": alert.condition,
        "metric": alert.metric,
        "operator": alert.operator,
        "threshold": alert.threshold,
        "offline_after_seconds": alert.offline_after_seconds,
        "observed_value": alert.observed_value,
        "resolved_value": alert.resolved_value,
        "opened_at": _utc_isoformat(alert.opened_at),
        "resolved_at": (
            _utc_isoformat(alert.resolved_at)
            if alert.resolved_at is not None
            else None
        ),
        "resolution_reason": alert.resolution_reason,
        "created_at": _utc_isoformat(alert.created_at),
        "updated_at": _utc_isoformat(alert.updated_at),
    }


def alert_update_message(
    alert: Alert, *, received_at: datetime
) -> dict[str, Any]:
    return {
        "type": "alert_update",
        "received_at": _utc_isoformat(received_at),
        "data": alert_data(alert),
    }


def publish_alert_changes(changes: list[AlertLifecycleChange]) -> None:
    """Publish changes only after their surrounding transaction commits."""
    for change in changes:
        realtime_hub.publish_from_thread(
            change.owner_id, change.alert_message
        )
        realtime_hub.publish_from_thread(
            change.owner_id, change.event_message
        )


def _event_details(alert: Alert) -> dict[str, Any]:
    details: dict[str, Any] = {
        "alert_id": alert.id,
        "rule_id": alert.rule_id,
        "rule_name": alert.rule_name,
        "rule_type": alert.rule_type,
        "alert_severity": alert.severity,
        "condition": alert.condition,
        "metric": alert.metric,
    }
    if alert.observed_value is not None:
        details["observed_value"] = alert.observed_value
    if alert.resolved_value is not None:
        details["resolved_value"] = alert.resolved_value
    if alert.resolution_reason is not None:
        details["resolution_reason"] = alert.resolution_reason
    return details


def _lifecycle_change(
    session: Session,
    alert: Alert,
    *,
    event_type: str,
    occurred_at: datetime,
) -> AlertLifecycleChange:
    event = create_device_event(
        session,
        owner_id=alert.owner_id,
        device_id=alert.device_id,
        event_type=event_type,
        occurred_at=occurred_at,
        details=_event_details(alert),
        severity=(
            OPEN_EVENT_SEVERITY[alert.severity]
            if event_type == "alert_opened"
            else "success"
        ),
    )
    return AlertLifecycleChange(
        owner_id=alert.owner_id,
        alert_message=alert_update_message(alert, received_at=occurred_at),
        event_message=event_created_message(event, received_at=occurred_at),
    )


def _active_alert(session: Session, rule_id: int) -> Alert | None:
    return session.scalar(
        select(Alert)
        .where(Alert.rule_id == rule_id, Alert.status == "active")
        .with_for_update()
    )


def _open_alert(
    session: Session,
    rule: AlertRule,
    *,
    observed_at: datetime,
    observed_value: float | None,
) -> AlertLifecycleChange:
    alert = Alert(
        owner_id=rule.owner_id,
        device_id=rule.device_id,
        rule_id=rule.id,
        rule_name=rule.name,
        rule_type=rule.rule_type,
        severity=rule.severity,
        status="active",
        condition=rule_condition(rule),
        metric=rule.metric,
        operator=rule.operator,
        threshold=rule.threshold,
        offline_after_seconds=rule.offline_after_seconds,
        observed_value=observed_value,
        opened_at=observed_at,
    )
    session.add(alert)
    session.flush([alert])
    return _lifecycle_change(
        session,
        alert,
        event_type="alert_opened",
        occurred_at=observed_at,
    )


def _resolve_alert(
    session: Session,
    alert: Alert,
    *,
    resolved_at: datetime,
    reason: str,
    resolved_value: float | None = None,
    detach_rule: bool = False,
) -> AlertLifecycleChange:
    alert.status = "resolved"
    alert.resolved_at = resolved_at
    alert.resolution_reason = reason
    alert.resolved_value = resolved_value
    if detach_rule:
        alert.rule_id = None
    session.flush([alert])
    return _lifecycle_change(
        session,
        alert,
        event_type="alert_resolved",
        occurred_at=resolved_at,
    )


def resolve_active_rule_alert(
    session: Session,
    rule: AlertRule,
    *,
    resolved_at: datetime,
    reason: str,
    detach_rule: bool = False,
) -> AlertLifecycleChange | None:
    active = _active_alert(session, rule.id)
    if active is None:
        return None
    return _resolve_alert(
        session,
        active,
        resolved_at=resolved_at,
        reason=reason,
        detach_rule=detach_rule,
    )


def _metric_condition(operator: str, value: float, threshold: float) -> bool:
    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    return value <= threshold


def _reconcile_rule(
    session: Session,
    rule: AlertRule,
    *,
    violated: bool,
    observed_at: datetime,
    observed_value: float | None,
    resolution_reason: str,
) -> AlertLifecycleChange | None:
    active = _active_alert(session, rule.id)
    if violated:
        if active is not None:
            return None
        return _open_alert(
            session,
            rule,
            observed_at=observed_at,
            observed_value=observed_value,
        )
    if active is None:
        return None
    return _resolve_alert(
        session,
        active,
        resolved_at=observed_at,
        reason=resolution_reason,
        resolved_value=observed_value,
    )


def evaluate_metric_rules(
    session: Session,
    *,
    device_id: str,
    metrics: Mapping[str, float | int | None],
    observed_at: datetime,
) -> list[AlertLifecycleChange]:
    rules = session.scalars(
        select(AlertRule)
        .where(
            AlertRule.device_id == device_id,
            AlertRule.rule_type == "metric_threshold",
            AlertRule.enabled.is_(True),
        )
        .order_by(AlertRule.id)
        .with_for_update()
    ).all()
    changes: list[AlertLifecycleChange] = []
    for rule in rules:
        value = metrics.get(rule.metric or "")
        if value is None:
            continue
        numeric_value = float(value)
        violated = _metric_condition(
            rule.operator or "gt",
            numeric_value,
            rule.threshold or 0,
        )
        change = _reconcile_rule(
            session,
            rule,
            violated=violated,
            observed_at=observed_at,
            observed_value=numeric_value,
            resolution_reason="condition_cleared",
        )
        if change is not None:
            changes.append(change)
    return changes


def evaluate_offline_rules(
    session: Session,
    *,
    observed_at: datetime,
    device_id: str | None = None,
) -> list[AlertLifecycleChange]:
    statement = (
        select(AlertRule, Device)
        .join(Device, Device.device_id == AlertRule.device_id)
        .where(
            AlertRule.rule_type == "device_offline",
            AlertRule.enabled.is_(True),
        )
        .order_by(AlertRule.id)
        .with_for_update(of=AlertRule)
    )
    if device_id is not None:
        statement = statement.where(AlertRule.device_id == device_id)

    changes: list[AlertLifecycleChange] = []
    for rule, device in session.execute(statement):
        offline_seconds = rule.offline_after_seconds or 0
        eligible = (
            device.status == "offline"
            and device.first_seen_at is not None
            and device.last_seen_at is not None
            and device.offline_since is not None
        )
        violated = bool(
            eligible
            and (observed_at - device.offline_since).total_seconds()
            >= offline_seconds
        )
        reason = (
            "device_reconnected"
            if device.status == "online"
            else "condition_cleared"
        )
        change = _reconcile_rule(
            session,
            rule,
            violated=violated,
            observed_at=observed_at,
            observed_value=None,
            resolution_reason=reason,
        )
        if change is not None:
            changes.append(change)
    return changes


def evaluate_committed_metric_sample(
    *,
    device_id: str,
    metrics: Mapping[str, float | int | None],
    observed_at: datetime,
) -> list[AlertLifecycleChange]:
    try:
        with SessionLocal.begin() as session:
            changes = evaluate_metric_rules(
                session,
                device_id=device_id,
                metrics=metrics,
                observed_at=observed_at,
            )
    except Exception:
        logger.exception("Metric alert evaluation failed for device=%s", device_id)
        return []
    publish_alert_changes(changes)
    return changes


def evaluate_offline_alerts_once(
    *,
    observed_at: datetime | None = None,
    device_id: str | None = None,
) -> list[AlertLifecycleChange]:
    evaluation_time = observed_at or datetime.now(timezone.utc)
    try:
        with SessionLocal.begin() as session:
            changes = evaluate_offline_rules(
                session,
                observed_at=evaluation_time,
                device_id=device_id,
            )
    except Exception:
        logger.exception("Offline alert evaluation failed")
        return []
    publish_alert_changes(changes)
    return changes
