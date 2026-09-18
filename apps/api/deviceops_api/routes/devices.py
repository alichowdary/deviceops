"""Read-only device and telemetry endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_database_session
from ..device_credentials import (
    generate_device_id,
    generate_device_secret,
    hash_device_secret,
)
from ..models import Device, Telemetry, User
from ..ownership import get_owned_device_or_404
from ..schemas import (
    DeviceRead,
    DeviceRegistrationCreate,
    DeviceRegistrationRead,
    TelemetryRead,
)
from ..security import get_current_user


router = APIRouter(prefix="/api/devices", tags=["devices"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "",
    response_model=DeviceRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
def register_device(
    _request: DeviceRegistrationCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> DeviceRegistrationRead:
    device_id = generate_device_id()
    device_secret = generate_device_secret()
    device = Device(
        device_id=device_id,
        owner_id=current_user.id,
        device_secret_hash=hash_device_secret(device_secret),
        status="unknown",
        first_seen_at=None,
        last_seen_at=None,
    )
    session.add(device)
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Device registration failed",
        ) from exc

    return DeviceRegistrationRead(
        device_id=device.device_id,
        device_secret=device_secret,
        status="unknown",
        created_at=device.created_at,
    )


@router.get("", response_model=list[DeviceRead])
def list_devices(session: DatabaseSession, current_user: CurrentUser) -> list[Device]:
    return list(
        session.scalars(
            select(Device)
            .where(Device.owner_id == current_user.id)
            .order_by(Device.device_id)
        )
    )


@router.get("/{device_id}", response_model=DeviceRead)
def get_device(
    device_id: str, session: DatabaseSession, current_user: CurrentUser
) -> Device:
    return get_owned_device_or_404(session, device_id, current_user.id)


@router.get("/{device_id}/telemetry", response_model=list[TelemetryRead])
def get_device_telemetry(
    device_id: str,
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Telemetry]:
    get_owned_device_or_404(session, device_id, current_user.id)

    newest_first = list(
        session.scalars(
            select(Telemetry)
            .where(Telemetry.device_id == device_id)
            .order_by(Telemetry.received_at.desc(), Telemetry.id.desc())
            .limit(limit)
        )
    )
    newest_first.reverse()
    return newest_first
