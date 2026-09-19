"""Profile-aware protocol-v1 simulator command execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .profiles import SimulatorProfile


@dataclass
class SimulatorCommandState:
    reporting_interval: float
    led_on: bool = False
    last_metrics: dict[str, Any] | None = None


def execute_command(
    profile: SimulatorProfile,
    command_type: object,
    arguments: dict[str, Any],
    state: SimulatorCommandState,
    uptime_s: int,
) -> dict[str, Any]:
    """Validate and execute one supported protocol-v1 command."""
    if not isinstance(command_type, str) or command_type not in profile.commands:
        raise ValueError(f"unsupported command for profile '{profile.name}'")

    if command_type == "set_led":
        if set(arguments) != {"on"} or not isinstance(arguments.get("on"), bool):
            raise ValueError("set_led requires exactly {'on': boolean}")
        state.led_on = arguments["on"]
        return {"on": state.led_on}

    if command_type == "set_reporting_interval":
        requested_interval = arguments.get("interval_s")
        if (
            set(arguments) != {"interval_s"}
            or isinstance(requested_interval, bool)
            or not isinstance(requested_interval, (int, float))
            or not 1 <= requested_interval <= 60
        ):
            raise ValueError(
                "set_reporting_interval requires exactly "
                "{'interval_s': number from 1 to 60}"
            )
        state.reporting_interval = float(requested_interval)
        return {"interval_s": state.reporting_interval}

    if arguments:
        raise ValueError("request_diagnostics arguments must be empty")
    result: dict[str, Any] = {}
    if "set_led" in profile.commands:
        result["led_on"] = state.led_on
    if "set_reporting_interval" in profile.commands:
        result["reporting_interval_s"] = state.reporting_interval
    result.update(
        {
            "uptime_s": uptime_s,
            "telemetry": dict(state.last_metrics) if state.last_metrics else None,
        }
    )
    return result
