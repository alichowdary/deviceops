"""MQTT validation and HTTP response schemas."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DEVICE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PASSWORD_MAX_LENGTH = 128


def _normalize_email(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("email must be a string")
    return value.strip().lower()


class UserRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> str:
        return _normalize_email(value)


class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_PATTERN)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> str:
        return _normalize_email(value)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class TokenRead(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class DeviceRegistrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceRegistrationRead(BaseModel):
    device_id: str
    device_secret: str
    status: Literal["unknown"]
    created_at: datetime


class TelemetryMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    temperature_c: float = Field(allow_inf_nan=False)
    battery_pct: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False
    )
    humidity_pct: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False
    )
    pressure_hpa: float | None = Field(default=None, allow_inf_nan=False)
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
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class TelemetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    sequence: int
    sent_at: datetime
    received_at: datetime
    temperature_c: float
    battery_pct: float | None
    humidity_pct: float | None
    pressure_hpa: float | None
    rssi_dbm: int
    uptime_s: int
    additional_metrics: dict[str, Any] | None


class HealthRead(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]
    mqtt: Literal["up", "down"]
    mqtt_error: str | None = None


CommandType = Literal["set_led", "set_reporting_interval", "request_diagnostics"]
CommandStatus = Literal["pending", "succeeded", "failed"]


class CommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: CommandType
    arguments: dict[str, Any]

    @model_validator(mode="after")
    def validate_arguments(self) -> "CommandCreate":
        if self.type == "set_led":
            if set(self.arguments) != {"on"} or not isinstance(
                self.arguments.get("on"), bool
            ):
                raise ValueError("set_led arguments must be exactly {'on': boolean}")
        elif self.type == "set_reporting_interval":
            interval = self.arguments.get("interval_s")
            if (
                set(self.arguments) != {"interval_s"}
                or isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not 1 <= interval <= 60
            ):
                raise ValueError(
                    "set_reporting_interval arguments must be exactly "
                    "{'interval_s': number from 1 to 60}"
                )
        elif self.arguments:
            raise ValueError("request_diagnostics arguments must be empty")
        return self


class CommandAckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    command_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    device_id: str = Field(pattern=DEVICE_ID_PATTERN, max_length=64)
    sent_at: datetime
    status: Literal["succeeded", "failed"]
    result: dict[str, Any]

    @field_validator("sent_at")
    @classmethod
    def sent_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("sent_at must include a UTC offset")
        return value


class CommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    command_id: str
    device_id: str
    type: CommandType = Field(validation_alias="command_type")
    arguments: dict[str, Any]
    status: CommandStatus
    issued_at: datetime
    acknowledged_at: datetime | None
    ack_sent_at: datetime | None
    result: dict[str, Any] | None
