"""Command-line entry point for the DeviceOps MQTT device simulator."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time

import paho.mqtt.client as mqtt

from .telemetry import TelemetryGenerator


BROKER_HOST = "localhost"
BROKER_PORT = 1883
CONNECT_TIMEOUT_S = 10
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


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


def run(device_id_value: str, interval: float) -> int:
    telemetry_topic = f"deviceops/v1/devices/{device_id_value}/telemetry"
    status_topic = f"deviceops/v1/devices/{device_id_value}/status"
    connected = threading.Event()
    connection_error: list[str] = []

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=device_id_value,
        protocol=mqtt.MQTTv311,
    )
    client.will_set(status_topic, payload="offline", qos=1, retain=True)

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
            connected_client.publish(status_topic, "online", qos=1, retain=True)
        connected.set()

    client.on_connect = on_connect

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

    if connection_error:
        client.loop_stop()
        client.disconnect()
        print(f"MQTT connection rejected: {connection_error[0]}", file=sys.stderr)
        return 1

    print(f"Connected; status=online (QoS 1, retained), interval={interval:g}s")
    generator = TelemetryGenerator(device_id_value)
    return_code = 0

    try:
        while True:
            payload = generator.next_message()
            encoded_payload = json.dumps(payload, separators=(",", ":"))
            result = client.publish(
                telemetry_topic,
                encoded_payload,
                qos=0,
                retain=False,
            )
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"telemetry publish failed: {mqtt.error_string(result.rc)}")

            metrics = payload["metrics"]
            print(
                f"telemetry seq={payload['sequence']} "
                f"temp={metrics['temperature_c']:.1f}C "
                f"battery={metrics['battery_pct']:.2f}% "
                f"rssi={metrics['rssi_dbm']}dBm "
                f"uptime={metrics['uptime_s']}s"
            )
            time.sleep(interval)
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
