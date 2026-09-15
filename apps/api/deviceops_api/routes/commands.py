"""Device-scoped command submission and history endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_database_session
from ..models import Device, DeviceCommand
from ..mqtt import MqttPublishError, mqtt_ingestor
from ..schemas import CommandCreate, CommandRead


router = APIRouter(prefix="/api/devices", tags=["commands"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


@router.post(
    "/{device_id}/commands",
    response_model=CommandRead,
    status_code=status.HTTP_201_CREATED,
)
def create_device_command(
    device_id: str, command_request: CommandCreate, session: DatabaseSession
) -> DeviceCommand:
    if session.get(Device, device_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

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
    session.commit()

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
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[DeviceCommand]:
    if session.get(Device, device_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    return list(
        session.scalars(
            select(DeviceCommand)
            .where(DeviceCommand.device_id == device_id)
            .order_by(DeviceCommand.issued_at.desc(), DeviceCommand.command_id.desc())
            .limit(limit)
        )
    )
