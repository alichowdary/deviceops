"""Read-only device and telemetry endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_database_session
from ..models import Device, Telemetry
from ..schemas import DeviceRead, TelemetryRead


router = APIRouter(prefix="/api/devices", tags=["devices"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


@router.get("", response_model=list[DeviceRead])
def list_devices(session: DatabaseSession) -> list[Device]:
    return list(session.scalars(select(Device).order_by(Device.device_id)))


@router.get("/{device_id}", response_model=DeviceRead)
def get_device(device_id: str, session: DatabaseSession) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.get("/{device_id}/telemetry", response_model=list[TelemetryRead])
def get_device_telemetry(
    device_id: str,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Telemetry]:
    if session.get(Device, device_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

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
