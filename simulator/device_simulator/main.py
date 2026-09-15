"""Command-line entry point for the DeviceOps MQTT device simulator."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
import json
import re
import sys
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from .telemetry import TelemetryGenerator


BROKER_HOST = "localhost"
BROKER_PORT = 1883
CONNECT_TIMEOUT_S = 10
RECENT_COMMAND_LIMIT = 100
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
COMMAND_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def positive_interval(value: str) -> float:
    interval = float(value)
    if interval <= 0:
        raise argparse.ArgumentTypeError("interval must be greater than zero")
    return interval


def device_id(value: str) -> str:
    if not DEVICE_ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "device ID must be 1-64 letters, digits, periods, underscores, or hyphens"
        )
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish simulated DeviceOps telemetry")
    parser.add_argument("--device-id", type=device_id, default="sim-001")
    parser.add_argument(
        "--interval",
        type=positive_interval,
        default=5.0,
        help="seconds between telemetry messages (default: 5)",
    )
    return parser.parse_args()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _validate_utc_timestamp(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must include a UTC offset")


def run(device_id_value: str, interval: float) -> int:
    telemetry_topic = f"deviceops/v1/devices/{device_id_value}/telemetry"
    status_topic = f"deviceops/v1/devices/{device_id_value}/status"
    command_topic = f"deviceops/v1/devices/{device_id_value}/commands"
    acknowledgement_topic = f"deviceops/v1/devices/{device_id_value}/command-acks"
    connected = threading.Event()
    subscribed = threading.Event()
    connection_error: list[str] = []

    generator = TelemetryGenerator(device_id_value)
    started_at = time.monotonic()
    state_changed = threading.Condition()
    reporting_interval = interval
    led_on = False
    last_metrics: dict[str, Any] | None = None
    recent_acknowledgements: OrderedDict[str, str] = OrderedDict()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=device_id_value,
        protocol=mqtt.MQTTv311,
    )
    client.will_set(status_topic, payload="offline", qos=1, retain=True)

    def publish_acknowledgement(
        command_id: str, status: str, result: dict[str, Any]
    ) -> None:
        payload = json.dumps(
            {
                "protocol_version": 1,
                "command_id": command_id,
                "device_id": device_id_value,
                "sent_at": _utc_timestamp(),
                "status": status,
                "result": result,
            },
            separators=(",", ":"),
        )
        with state_changed:
            recent_acknowledgements[command_id] = payload
            recent_acknowledgements.move_to_end(command_id)
            while len(recent_acknowledgements) > RECENT_COMMAND_LIMIT:
                recent_acknowledgements.popitem(last=False)

        published = client.publish(
            acknowledgement_topic, payload, qos=1, retain=False
        )
        if published.rc != mqtt.MQTT_ERR_SUCCESS:
            print(
                f"command {command_id}: acknowledgement publish failed: "
                f"{mqtt.error_string(published.rc)}",
                file=sys.stderr,
                flush=True,
            )

    def process_command(raw_payload: bytes) -> None:
        nonlocal led_on, reporting_interval

        try:
            decoded = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"Rejected malformed command JSON: {exc}", file=sys.stderr, flush=True)
            return

        if not isinstance(decoded, dict):
            print("Rejected command: payload must be an object", file=sys.stderr, flush=True)
            return

        command_id = decoded.get("command_id")
        if not isinstance(command_id, str) or not COMMAND_ID_PATTERN.fullmatch(command_id):
            print("Rejected command: command_id must be a UUID v4", file=sys.stderr, flush=True)
            return

        with state_changed:
            cached_acknowledgement = recent_acknowledgements.get(command_id)
        if cached_acknowledgement is not None:
            client.publish(
                acknowledgement_topic,
                cached_acknowledgement,
                qos=1,
                retain=False,
            )
            print(
                f"command {command_id}: duplicate delivery; resent cached acknowledgement",
                flush=True,
            )
            return

        try:
            protocol_version = decoded.get("protocol_version")
            if protocol_version != 1 or isinstance(protocol_version, bool):
                raise ValueError("protocol_version must be 1")
            if decoded.get("device_id") != device_id_value:
                raise ValueError("device_id does not match this device")
            _validate_utc_timestamp(decoded.get("issued_at"), "issued_at")

            command_type = decoded.get("type")
            arguments = decoded.get("arguments")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")

            if command_type == "set_led":
                if set(arguments) != {"on"} or not isinstance(arguments.get("on"), bool):
                    raise ValueError("set_led requires exactly {'on': boolean}")
                with state_changed:
                    led_on = arguments["on"]
                print(
                    f"command {command_id}: LED {'ON' if led_on else 'OFF'}",
                    flush=True,
                )
                result = {"on": led_on}
            elif command_type == "set_reporting_interval":
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
                with state_changed:
                    reporting_interval = float(requested_interval)
                    state_changed.notify_all()
                print(
                    f"command {command_id}: reporting interval -> "
                    f"{reporting_interval:g}s",
                    flush=True,
                )
                result = {"interval_s": reporting_interval}
            elif command_type == "request_diagnostics":
                if arguments:
                    raise ValueError("request_diagnostics arguments must be empty")
                with state_changed:
                    result = {
                        "led_on": led_on,
                        "reporting_interval_s": reporting_interval,
                        "uptime_s": int(time.monotonic() - started_at),
                        "telemetry": dict(last_metrics) if last_metrics else None,
                    }
                print(f"command {command_id}: diagnostics collected", flush=True)
            else:
                raise ValueError("unsupported command type")
        except ValueError as exc:
            error = str(exc)
            print(f"command {command_id}: failed: {error}", file=sys.stderr, flush=True)
            publish_acknowledgement(command_id, "failed", {"error": error})
            return

        publish_acknowledgement(command_id, "succeeded", result)

    def on_connect(
        connected_client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            connection_error.append(str(reason_code))
        else:
            result, _message_id = connected_client.subscribe(command_topic, qos=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                connection_error.append(
                    f"command subscription failed: {mqtt.error_string(result)}"
                )
            else:
                connected_client.publish(status_topic, "online", qos=1, retain=True)
        connected.set()

    def on_subscribe(
        _client: mqtt.Client,
        _userdata: object,
        _message_id: int,
        reason_codes: list[mqtt.ReasonCode],
        _properties: mqtt.Properties | None,
    ) -> None:
        if any(reason_code.is_failure for reason_code in reason_codes):
            connection_error.append("broker rejected command subscription")
        subscribed.set()

    def on_message(
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            process_command(message.payload)
        except Exception as exc:
            print(
                f"Unexpected command processing error: {exc}",
                file=sys.stderr,
                flush=True,
            )

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    print(
        f"Connecting {device_id_value} to mqtt://{BROKER_HOST}:{BROKER_PORT} ...",
        flush=True,
    )
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
    except OSError as exc:
        print(
            f"Could not connect to MQTT broker at {BROKER_HOST}:{BROKER_PORT}: {exc}",
            file=sys.stderr,
        )
        print("Start it with: docker compose up -d", file=sys.stderr)
        return 1

    client.loop_start()
    if not connected.wait(CONNECT_TIMEOUT_S):
        client.loop_stop()
        client.disconnect()
        print(
            f"Timed out connecting to MQTT broker at {BROKER_HOST}:{BROKER_PORT}",
            file=sys.stderr,
        )
        return 1

    if not connection_error and not subscribed.wait(CONNECT_TIMEOUT_S):
        connection_error.append("timed out subscribing to command topic")

    if connection_error:
        client.loop_stop()
        client.disconnect()
        print(f"MQTT setup failed: {connection_error[0]}", file=sys.stderr)
        return 1

    print(
        f"Connected; status=online, interval={interval:g}s; "
        f"subscribed to {command_topic} (QoS 1)",
        flush=True,
    )
    return_code = 0

    try:
        while True:
            payload = generator.next_message()
            with state_changed:
                last_metrics = dict(payload["metrics"])
            encoded_payload = json.dumps(payload, separators=(",", ":"))
            result = client.publish(
                telemetry_topic,
                encoded_payload,
                qos=0,
                retain=False,
            )
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(
                    f"telemetry publish failed: {mqtt.error_string(result.rc)}"
                )

            metrics = payload["metrics"]
            print(
                f"telemetry seq={payload['sequence']} "
                f"temp={metrics['temperature_c']:.1f}C "
                f"battery={metrics['battery_pct']:.2f}% "
                f"rssi={metrics['rssi_dbm']}dBm "
                f"uptime={metrics['uptime_s']}s"
            )
            with state_changed:
                state_changed.wait(timeout=reporting_interval)
    except KeyboardInterrupt:
        print("\nShutdown requested; publishing status=offline ...")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return_code = 1

    offline = client.publish(status_topic, "offline", qos=1, retain=True)
    try:
        offline.wait_for_publish(timeout=5)
        if not offline.is_published():
            raise RuntimeError("timed out waiting for the MQTT acknowledgement")
    except RuntimeError as exc:
        print(f"Could not confirm offline status: {exc}", file=sys.stderr)
        return_code = 1

    client.disconnect()
    client.loop_stop()
    print("Disconnected cleanly; status=offline (QoS 1, retained)")
    return return_code


def main() -> None:
    args = parse_args()
    raise SystemExit(run(args.device_id, args.interval))
