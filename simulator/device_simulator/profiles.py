"""Small, explicit simulator device profiles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from .telemetry import (
    AirQualityTelemetryGenerator,
    PortableTelemetryGenerator,
    TelemetryGenerator,
)


class TelemetrySource(Protocol):
    def next_message(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SimulatorProfile:
    name: str
    telemetry: dict[str, dict[str, Any]]
    commands: dict[str, dict[str, Any]]
    generator_type: type[TelemetrySource]

    def build_manifest(self, device_id: str, sent_at: str) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            "capabilities_version": 1,
            "device_id": device_id,
            "sent_at": sent_at,
            "telemetry": deepcopy(self.telemetry),
            "commands": deepcopy(self.commands),
        }

    def create_generator(self, device_id: str) -> TelemetrySource:
        return self.generator_type(device_id)


DEFAULT_PROFILE = SimulatorProfile(
    name="default",
    telemetry={
        "temperature_c": {
            "type": "number",
            "label": "Temperature",
            "unit": "°C",
        },
        "battery_pct": {
            "type": "number",
            "label": "Battery",
            "unit": "%",
        },
        "rssi_dbm": {
            "type": "integer",
            "label": "RSSI",
            "unit": "dBm",
        },
        "uptime_s": {
            "type": "integer",
            "label": "Uptime",
            "unit": "s",
        },
    },
    commands={
        "set_led": {
            "label": "LED",
            "arguments": {"on": {"type": "boolean", "label": "On"}},
        },
        "set_reporting_interval": {
            "label": "Reporting interval",
            "arguments": {
                "interval_s": {
                    "type": "number",
                    "label": "Interval",
                    "unit": "s",
                    "min": 1,
                    "max": 60,
                }
            },
        },
        "request_diagnostics": {
            "label": "Request diagnostics",
            "arguments": {},
        },
    },
    generator_type=TelemetryGenerator,
)


PORTABLE_SENSOR_PROFILE = SimulatorProfile(
    name="portable-sensor",
    telemetry={
        "temperature_c": {
            "type": "number",
            "label": "Temperature",
            "unit": "°C",
        },
        "battery_pct": {
            "type": "number",
            "label": "Battery",
            "unit": "%",
        },
        "light_lux": {
            "type": "number",
            "label": "Ambient light",
            "unit": "lux",
        },
        "motion_detected": {
            "type": "boolean",
            "label": "Motion detected",
        },
        "rssi_dbm": {
            "type": "integer",
            "label": "RSSI",
            "unit": "dBm",
        },
        "uptime_s": {
            "type": "integer",
            "label": "Uptime",
            "unit": "s",
        },
    },
    commands={
        "request_diagnostics": {
            "label": "Request diagnostics",
            "arguments": {},
        },
    },
    generator_type=PortableTelemetryGenerator,
)


AIR_QUALITY_PROFILE = SimulatorProfile(
    name="air-quality",
    telemetry={
        "co2_ppm": {
            "type": "number",
            "label": "CO₂",
            "unit": "ppm",
        },
        "voc_index": {
            "type": "number",
            "label": "VOC index",
        },
        "occupied": {
            "type": "boolean",
            "label": "Occupied",
        },
        "air_quality": {
            "type": "string",
            "label": "Air quality",
        },
    },
    commands={
        "request_diagnostics": {
            "label": "Request diagnostics",
            "arguments": {},
        },
    },
    generator_type=AirQualityTelemetryGenerator,
)


PROFILES = {
    DEFAULT_PROFILE.name: DEFAULT_PROFILE,
    PORTABLE_SENSOR_PROFILE.name: PORTABLE_SENSOR_PROFILE,
    AIR_QUALITY_PROFILE.name: AIR_QUALITY_PROFILE,
}
PROFILE_NAMES = tuple(PROFILES)


def get_profile(name: str) -> SimulatorProfile:
    return PROFILES[name]
