"""Small helpers for enforcing device ownership in REST routes."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Device


def get_owned_device_or_404(
    session: Session, device_id: str, owner_id: int
) -> Device:
    device = session.scalar(
        select(Device).where(
            Device.device_id == device_id,
            Device.owner_id == owner_id,
        )
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )
    return device
