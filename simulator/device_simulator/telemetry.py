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
