"""MQTT validation and HTTP response schemas."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEVICE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class TelemetryMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    temperature_c: float = Field(allow_inf_nan=False)
    battery_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    rssi_dbm: int
    uptime_s: int = Field(ge=0)


class TelemetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    device_id: str = Field(pattern=DEVICE_ID_PATTERN, max_length=64)
    sent_at: datetime
    sequence: int = Field(ge=1)
    metrics: TelemetryMetrics

    @field_validator("sent_at")
    @classmethod
    def sent_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("sent_at must include a UTC offset")
        return value


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime


class TelemetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    sequence: int
    sent_at: datetime
    received_at: datetime
    temperature_c: float
    battery_pct: float
    rssi_dbm: int
    uptime_s: int
    additional_metrics: dict[str, Any] | None


class HealthRead(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]
    mqtt: Literal["up", "down"]
    mqtt_error: str | None = None
