"""Stateful generation of realistic, slowly changing device telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
import time
from typing import Any


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


@dataclass
class TelemetryGenerator:
    device_id: str
    _sequence: int = field(default=0, init=False)
    _temperature_c: float = field(default=24.7, init=False)
    _battery_pct: float = field(default=91.2, init=False)
    _rssi_dbm: int = field(default=-55, init=False)
    _started_at: float = field(default_factory=time.monotonic, init=False)

    def next_message(self) -> dict[str, Any]:
        """Return the next telemetry payload and advance the simulated state."""
        self._sequence += 1

        # Small random walks plus temperature mean reversion resemble a stable sensor.
        self._temperature_c += (24.5 - self._temperature_c) * 0.05
        self._temperature_c += random.uniform(-0.12, 0.12)
        self._temperature_c = _clamp(self._temperature_c, 18.0, 32.0)

        self._battery_pct = max(0.0, self._battery_pct - random.uniform(0.01, 0.04))
        self._rssi_dbm += random.randint(-2, 2)
        self._rssi_dbm = int(_clamp(self._rssi_dbm, -75, -40))

        sent_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

        return {
            "protocol_version": 1,
            "device_id": self.device_id,
            "sent_at": sent_at.replace("+00:00", "Z"),
            "sequence": self._sequence,
            "metrics": {
                "temperature_c": round(self._temperature_c, 1),
                "battery_pct": round(self._battery_pct, 2),
                "rssi_dbm": self._rssi_dbm,
                "uptime_s": int(time.monotonic() - self._started_at),
            },
        }


@dataclass
class PortableTelemetryGenerator:
    """Deterministic telemetry for a portable light and motion sensor."""

    device_id: str
    _sequence: int = field(default=0, init=False)
    _battery_pct: float = field(default=78.0, init=False)
    _started_at: float = field(default_factory=time.monotonic, init=False)

    def next_message(self) -> dict[str, Any]:
        self._sequence += 1

        temperature_c = 22.6 + ((self._sequence - 1) % 9) * 0.1
        self._battery_pct = max(0.0, self._battery_pct - 0.02)
        light_lux = 180.0 + ((self._sequence - 1) % 12) * 17.5
        motion_detected = self._sequence % 6 in {1, 2}
        rssi_dbm = -63 + ((self._sequence - 1) % 5)
        sent_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

        return {
            "protocol_version": 1,
            "device_id": self.device_id,
            "sent_at": sent_at.replace("+00:00", "Z"),
            "sequence": self._sequence,
            "metrics": {
                "temperature_c": round(temperature_c, 1),
                "battery_pct": round(self._battery_pct, 2),
                "light_lux": round(light_lux, 1),
                "motion_detected": motion_detected,
                "rssi_dbm": rssi_dbm,
                "uptime_s": int(time.monotonic() - self._started_at),
            },
        }


@dataclass
class AirQualityTelemetryGenerator:
    """Deterministic indoor air-quality telemetry with no legacy metrics."""

    device_id: str
    _sequence: int = field(default=0, init=False)

    def next_message(self) -> dict[str, Any]:
        self._sequence += 1

        cycle = (self._sequence - 1) % 24
        occupied = cycle < 16
        if occupied:
            co2_ppm = 520 + cycle * 48
            voc_index = 72 + cycle * 5
        else:
            recovery = cycle - 16
            co2_ppm = 1190 - recovery * 80
            voc_index = 142 - recovery * 8

        if co2_ppm < 800 and voc_index < 100:
            air_quality = "Good"
        elif co2_ppm < 1100 and voc_index < 140:
            air_quality = "Fair"
        else:
            air_quality = "Poor"

        sent_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        return {
            "protocol_version": 1,
            "device_id": self.device_id,
            "sent_at": sent_at.replace("+00:00", "Z"),
            "sequence": self._sequence,
            "metrics": {
                "co2_ppm": co2_ppm,
                "voc_index": voc_index,
                "occupied": occupied,
                "air_quality": air_quality,
            },
        }
