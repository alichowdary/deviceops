"""Small helpers for enforcing device ownership in REST routes."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Alert, AlertRule, Device


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


def get_owned_alert_rule_or_404(
    session: Session,
    rule_id: int,
    owner_id: int,
    *,
    for_update: bool = False,
) -> AlertRule:
    statement = select(AlertRule).where(
        AlertRule.id == rule_id,
        AlertRule.owner_id == owner_id,
    )
    if for_update:
        statement = statement.with_for_update()
    rule = session.scalar(statement)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found",
        )
    return rule


def get_owned_alert_or_404(
    session: Session, alert_id: int, owner_id: int
) -> Alert:
    alert = session.scalar(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.owner_id == owner_id,
        )
    )
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    return alert
