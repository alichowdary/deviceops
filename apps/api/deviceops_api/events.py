"""Creation and client-safe serialization of persistent fleet events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypeAlias

from sqlalchemy.orm import Session

from .models import DeviceEvent


EventType: TypeAlias = Literal[
    "device_registered",
    "device_online",
    "device_offline",
    "command_issued",
    "command_succeeded",
    "command_failed",
]
EventSeverity: TypeAlias = Literal["info", "success", "warning", "error"]

EVENT_SEVERITY: dict[EventType, EventSeverity] = {
    "device_registered": "info",
    "device_online": "success",
    "device_offline": "warning",
    "command_issued": "info",
    "command_succeeded": "success",
    "command_failed": "error",
}


def _utc_isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def create_device_event(
    session: Session,
    *,
    owner_id: int,
    device_id: str,
    event_type: EventType,
    occurred_at: datetime,
    details: dict[str, Any] | None = None,
) -> DeviceEvent:
    """Add and flush one event inside the caller's domain transaction."""
    event = DeviceEvent(
        owner_id=owner_id,
        device_id=device_id,
        event_type=event_type,
        severity=EVENT_SEVERITY[event_type],
        occurred_at=occurred_at,
        details=details or {},
    )
    session.add(event)
    session.flush([event])
    return event


def event_created_message(
    event: DeviceEvent,
    *,
    received_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a browser event without exposing owner routing metadata."""
    return {
        "type": "event_created",
        "received_at": _utc_isoformat(received_at or datetime.now(timezone.utc)),
        "data": {
            "id": event.id,
            "device_id": event.device_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "occurred_at": _utc_isoformat(event.occurred_at),
            "details": event.details,
        },
    }
