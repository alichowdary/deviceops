"""Authenticated owner-scoped alert lifecycle history endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_database_session
from ..models import Alert, User
from ..ownership import (
    get_owned_alert_or_404,
    get_owned_alert_rule_or_404,
    get_owned_device_or_404,
)
from ..schemas import AlertRead, AlertSeverity, AlertStatus
from ..security import get_current_user


router = APIRouter(prefix="/api/alerts", tags=["alerts"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=list[AlertRead])
def list_alerts(
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    status: Annotated[AlertStatus | None, Query()] = None,
    device_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    severity: Annotated[AlertSeverity | None, Query()] = None,
    rule_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[Alert]:
    if device_id is not None:
        get_owned_device_or_404(session, device_id, current_user.id)
    if rule_id is not None:
        get_owned_alert_rule_or_404(session, rule_id, current_user.id)

    statement = select(Alert).where(Alert.owner_id == current_user.id)
    if status is not None:
        statement = statement.where(Alert.status == status)
    if device_id is not None:
        statement = statement.where(Alert.device_id == device_id)
    if severity is not None:
        statement = statement.where(Alert.severity == severity)
    if rule_id is not None:
        statement = statement.where(Alert.rule_id == rule_id)

    return list(
        session.scalars(
            statement.order_by(Alert.opened_at.desc(), Alert.id.desc()).limit(
                limit
            )
        )
    )


@router.get("/{alert_id}", response_model=AlertRead)
def get_alert(
    alert_id: Annotated[int, Path(gt=0)],
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Alert:
    return get_owned_alert_or_404(session, alert_id, current_user.id)
