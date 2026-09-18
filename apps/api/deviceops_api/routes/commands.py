"""Device-scoped command submission and history endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_database_session
from ..events import create_device_event, event_created_message
from ..models import DeviceCommand, User
from ..mqtt import MqttPublishError, mqtt_ingestor
from ..ownership import get_owned_device_or_404
from ..schemas import CommandCreate, CommandRead
from ..security import get_current_user
from ..realtime import realtime_hub


router = APIRouter(prefix="/api/devices", tags=["commands"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/{device_id}/commands",
    response_model=CommandRead,
    status_code=status.HTTP_201_CREATED,
)
def create_device_command(
    device_id: str,
    command_request: CommandCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> DeviceCommand:
    get_owned_device_or_404(session, device_id, current_user.id)

    issued_at = datetime.now(timezone.utc)
    command = DeviceCommand(
        command_id=str(uuid4()),
        device_id=device_id,
        command_type=command_request.type,
        arguments=command_request.arguments,
        status="pending",
        issued_at=issued_at,
    )
    session.add(command)
    session.flush()
    event = create_device_event(
        session,
        owner_id=current_user.id,
        device_id=device_id,
        event_type="command_issued",
        occurred_at=issued_at,
        details={
            "command_id": command.command_id,
            "command_type": command.command_type,
            "arguments": command.arguments,
        },
    )
    session.commit()

    realtime_hub.publish_from_thread(
        current_user.id, event_created_message(event)
    )

    try:
        mqtt_ingestor.publish_command(command)
    except MqttPublishError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Command {command.command_id} was saved as pending but could not "
                f"be published: {exc}"
            ),
        ) from exc

    return command


@router.get("/{device_id}/commands", response_model=list[CommandRead])
def list_device_commands(
    device_id: str,
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[DeviceCommand]:
    get_owned_device_or_404(session, device_id, current_user.id)

    return list(
        session.scalars(
            select(DeviceCommand)
            .where(DeviceCommand.device_id == device_id)
            .order_by(DeviceCommand.issued_at.desc(), DeviceCommand.command_id.desc())
            .limit(limit)
        )
    )
