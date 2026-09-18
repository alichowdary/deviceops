"""Authenticated owner-scoped fleet event feed."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_database_session
from ..events import EventSeverity, EventType
from ..models import DeviceEvent, User
from ..ownership import get_owned_device_or_404
from ..schemas import DeviceEventRead
from ..security import get_current_user


router = APIRouter(prefix="/api/events", tags=["events"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=list[DeviceEventRead])
def list_events(
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    device_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    event_type: Annotated[EventType | None, Query()] = None,
    severity: Annotated[EventSeverity | None, Query()] = None,
) -> list[DeviceEvent]:
    if device_id is not None:
        get_owned_device_or_404(session, device_id, current_user.id)

    statement = select(DeviceEvent).where(
        DeviceEvent.owner_id == current_user.id
    )
    if device_id is not None:
        statement = statement.where(DeviceEvent.device_id == device_id)
    if event_type is not None:
        statement = statement.where(DeviceEvent.event_type == event_type)
    if severity is not None:
        statement = statement.where(DeviceEvent.severity == severity)

    return list(
        session.scalars(
            statement.order_by(
                DeviceEvent.occurred_at.desc(), DeviceEvent.id.desc()
            ).limit(limit)
        )
    )
