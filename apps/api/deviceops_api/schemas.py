"""MQTT validation and HTTP response schemas."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from .events import EventSeverity, EventType


DEVICE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PASSWORD_MAX_LENGTH = 128
ALERT_RULE_NAME_MAX_LENGTH = 100
ALERT_OFFLINE_MIN_SECONDS = 5
ALERT_OFFLINE_MAX_SECONDS = 604_800

AlertRuleType = Literal["metric_threshold", "device_offline"]
AlertMetric = Literal[
    "temperature_c",
    "humidity_pct",
    "pressure_hpa",
    "battery_pct",
    "rssi_dbm",
]
AlertOperator = Literal["gt", "gte", "lt", "lte"]
AlertSeverity = Literal["info", "warning", "critical"]

ALERT_METRIC_BOUNDS: dict[AlertMetric, tuple[float, float]] = {
    "temperature_c": (-100, 200),
    "humidity_pct": (0, 100),
    "pressure_hpa": (0, 2000),
    "battery_pct": (0, 100),
    "rssi_dbm": (-200, 0),
}


def _normalize_email(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("email must be a string")
    return value.strip().lower()


def _normalize_rule_name(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("name must be a string or null")
    normalized = value.strip()
    return normalized or None


def _validate_threshold_input(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("threshold must be a finite number")
    threshold = float(value)
    if not math.isfinite(threshold):
        raise ValueError("threshold must be a finite number")
    return threshold


def _validate_offline_seconds_input(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("offline_after_seconds must be an integer")
    return value


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


class DeviceEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    event_type: EventType
    severity: EventSeverity
    occurred_at: datetime
    details: dict[str, Any]


class AlertRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(pattern=DEVICE_ID_PATTERN, max_length=64)
    name: str | None = Field(default=None, max_length=ALERT_RULE_NAME_MAX_LENGTH)
    rule_type: AlertRuleType
    severity: AlertSeverity = "warning"
    enabled: StrictBool = True
    metric: AlertMetric | None = None
    operator: AlertOperator | None = None
    threshold: float | None = None
    offline_after_seconds: int | None = Field(
        default=None,
        ge=ALERT_OFFLINE_MIN_SECONDS,
        le=ALERT_OFFLINE_MAX_SECONDS,
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str | None:
        return _normalize_rule_name(value)

    @field_validator("threshold", mode="before")
    @classmethod
    def validate_finite_threshold(cls, value: object) -> float | None:
        return _validate_threshold_input(value)

    @field_validator("offline_after_seconds", mode="before")
    @classmethod
    def validate_offline_seconds(cls, value: object) -> int | None:
        return _validate_offline_seconds_input(value)

    @model_validator(mode="after")
    def validate_rule_shape(self) -> "AlertRuleCreate":
        if self.rule_type == "metric_threshold":
            if (
                self.metric is None
                or self.operator is None
                or self.threshold is None
                or self.offline_after_seconds is not None
            ):
                raise ValueError(
                    "metric_threshold requires metric, operator, and threshold "
                    "and forbids offline_after_seconds"
                )
            lower, upper = ALERT_METRIC_BOUNDS[self.metric]
            if not lower <= self.threshold <= upper:
                raise ValueError(
                    f"threshold for {self.metric} must be between "
                    f"{lower:g} and {upper:g}"
                )
        elif (
            self.offline_after_seconds is None
            or self.metric is not None
            or self.operator is not None
            or self.threshold is not None
        ):
            raise ValueError(
                "device_offline requires offline_after_seconds and forbids "
                "metric, operator, and threshold"
            )
        return self


class AlertRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=ALERT_RULE_NAME_MAX_LENGTH)
    severity: AlertSeverity | None = None
    enabled: StrictBool | None = None
    operator: AlertOperator | None = None
    threshold: float | None = None
    offline_after_seconds: int | None = Field(
        default=None,
        ge=ALERT_OFFLINE_MIN_SECONDS,
        le=ALERT_OFFLINE_MAX_SECONDS,
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str | None:
        return _normalize_rule_name(value)

    @field_validator("threshold", mode="before")
    @classmethod
    def validate_finite_threshold(cls, value: object) -> float | None:
        return _validate_threshold_input(value)

    @field_validator("offline_after_seconds", mode="before")
    @classmethod
    def validate_offline_seconds(cls, value: object) -> int | None:
        return _validate_offline_seconds_input(value)

    @model_validator(mode="after")
    def require_update_field(self) -> "AlertRuleUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one alert rule field is required")
        nullable_fields = self.model_fields_set - {"name"}
        if any(getattr(self, field_name) is None for field_name in nullable_fields):
            raise ValueError("only name may be set to null")
        return self


class AlertRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    name: str | None
    rule_type: AlertRuleType
    severity: AlertSeverity
    enabled: bool
    metric: AlertMetric | None
    operator: AlertOperator | None
    threshold: float | None
    offline_after_seconds: int | None
    created_at: datetime
    updated_at: datetime


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
