"""Authenticated CRUD endpoints for owner-scoped alert rules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alerts import publish_alert_changes, resolve_active_rule_alert
from ..database import get_database_session
from ..models import AlertRule, Device, User
from ..ownership import (
    get_owned_alert_rule_or_404,
    get_owned_device_or_404,
)
from ..schemas import (
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleType,
    AlertRuleUpdate,
    AlertSeverity,
)
from ..security import get_current_user


router = APIRouter(prefix="/api/alert-rules", tags=["alert rules"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _validate_metric_capability(device: Device, metric: str) -> None:
    capabilities = device.capabilities
    if not isinstance(capabilities, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Metric threshold rules require advertised device capabilities",
        )
    telemetry = capabilities.get("telemetry")
    descriptor = telemetry.get(metric) if isinstance(telemetry, dict) else None
    if not isinstance(descriptor, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Metric '{metric}' is not advertised by this device",
        )
    if descriptor.get("type") not in {"number", "integer"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Metric '{metric}' is not numeric",
        )


@router.get("", response_model=list[AlertRuleRead])
def list_alert_rules(
    session: DatabaseSession,
    current_user: CurrentUser,
    device_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    enabled: Annotated[bool | None, Query()] = None,
    rule_type: Annotated[AlertRuleType | None, Query()] = None,
    severity: Annotated[AlertSeverity | None, Query()] = None,
) -> list[AlertRule]:
    if device_id is not None:
        get_owned_device_or_404(session, device_id, current_user.id)

    statement = select(AlertRule).where(
        AlertRule.owner_id == current_user.id
    )
    if device_id is not None:
        statement = statement.where(AlertRule.device_id == device_id)
    if enabled is not None:
        statement = statement.where(AlertRule.enabled == enabled)
    if rule_type is not None:
        statement = statement.where(AlertRule.rule_type == rule_type)
    if severity is not None:
        statement = statement.where(AlertRule.severity == severity)

    return list(
        session.scalars(
            statement.order_by(AlertRule.created_at.desc(), AlertRule.id.desc())
        )
    )


@router.post(
    "",
    response_model=AlertRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_alert_rule(
    request: AlertRuleCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AlertRule:
    device = get_owned_device_or_404(
        session, request.device_id, current_user.id
    )
    if request.rule_type == "metric_threshold":
        _validate_metric_capability(device, request.metric or "")
    rule = AlertRule(owner_id=current_user.id, **request.model_dump())
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.get("/{rule_id}", response_model=AlertRuleRead)
def get_alert_rule(
    rule_id: Annotated[int, Path(gt=0)],
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AlertRule:
    return get_owned_alert_rule_or_404(session, rule_id, current_user.id)


@router.patch("/{rule_id}", response_model=AlertRuleRead)
def update_alert_rule(
    rule_id: Annotated[int, Path(gt=0)],
    request: AlertRuleUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AlertRule:
    rule = get_owned_alert_rule_or_404(
        session, rule_id, current_user.id, for_update=True
    )
    was_enabled = rule.enabled
    changes = request.model_dump(exclude_unset=True)
    try:
        candidate = AlertRuleCreate.model_validate(
            {
                "device_id": rule.device_id,
                "name": changes.get("name", rule.name),
                "rule_type": rule.rule_type,
                "severity": changes.get("severity", rule.severity),
                "enabled": changes.get("enabled", rule.enabled),
                "metric": rule.metric,
                "operator": changes.get("operator", rule.operator),
                "threshold": changes.get("threshold", rule.threshold),
                "offline_after_seconds": changes.get(
                    "offline_after_seconds", rule.offline_after_seconds
                ),
            }
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid fields for this alert rule type",
        ) from exc
    validated = candidate.model_dump()
    for field_name in changes:
        setattr(rule, field_name, validated[field_name])

    lifecycle_changes = []
    if was_enabled and not rule.enabled:
        change = resolve_active_rule_alert(
            session,
            rule,
            resolved_at=datetime.now(timezone.utc),
            reason="rule_disabled",
        )
        if change is not None:
            lifecycle_changes.append(change)
    session.commit()
    session.refresh(rule)
    publish_alert_changes(lifecycle_changes)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    rule_id: Annotated[int, Path(gt=0)],
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    rule = get_owned_alert_rule_or_404(
        session, rule_id, current_user.id, for_update=True
    )
    lifecycle_changes = []
    change = resolve_active_rule_alert(
        session,
        rule,
        resolved_at=datetime.now(timezone.utc),
        reason="rule_deleted",
        detach_rule=True,
    )
    if change is not None:
        lifecycle_changes.append(change)
    session.delete(rule)
    session.commit()
    publish_alert_changes(lifecycle_changes)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
