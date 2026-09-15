# DeviceOps MQTT protocol

This document specifies protocol version 1. Topic paths and JSON payloads are
part of the contract. Breaking changes require a new version namespace rather
than silently changing version 1 behavior.

## Device identity and topics

Each device has a stable `device_id`, such as `sim-001`, `sim-002`, or
`esp32-001`. It identifies the physical or simulated device and must not be a
mutable display name. Version 1 device IDs use letters, digits, periods,
underscores, and hyphens; they must not contain `/`, `+`, or `#`.

| Purpose | Topic |
| --- | --- |
| Telemetry | `deviceops/v1/devices/{device_id}/telemetry` |
| Presence/status | `deviceops/v1/devices/{device_id}/status` |
| Commands | `deviceops/v1/devices/{device_id}/commands` |
| Command acknowledgements | `deviceops/v1/devices/{device_id}/command-acks` |

Commands travel from FastAPI to a device. Acknowledgements travel from the
device back to FastAPI. Browsers never connect to MQTT.

## Telemetry

Telemetry is a UTF-8 JSON object:

```json
{
  "protocol_version": 1,
  "device_id": "sim-001",
  "sent_at": "2026-09-14T16:30:05.123Z",
  "sequence": 1,
  "metrics": {
    "temperature_c": 24.7,
    "battery_pct": 91.2,
    "rssi_dbm": -55,
    "uptime_s": 20
  }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `protocol_version` | integer | Must be `1`. |
| `device_id` | string | Must exactly match `{device_id}` in the topic. |
| `sent_at` | string | Device time as a UTC ISO-8601 timestamp ending in `Z`. |
| `sequence` | integer | Starts at `1` and increases once per telemetry message for the lifetime of the device process. |
| `metrics.temperature_c` | number | Temperature in degrees Celsius. |
| `metrics.battery_pct` | number | Remaining battery percentage from `0` to `100`. |
| `metrics.rssi_dbm` | integer | Wi-Fi received signal strength in dBm; values nearer zero are stronger. |
| `metrics.uptime_s` | integer | Monotonically increasing seconds since the device process started. |

Metrics stay under the `metrics` object so compatible sensors can be added
without mixing measurements with message metadata.

Telemetry uses QoS 0 and is not retained. It is frequent, and a later reading
supersedes a missed individual reading, so broker acknowledgement and retry are
not required for every sample.

## Presence/status

The status payload is the UTF-8 text `online` or `offline`. Status uses QoS 1 and
is retained so a new subscriber immediately receives the device's latest known
state rather than waiting for another transition.

Before connecting, a device configures a retained, QoS 1 Last Will of `offline`
on its status topic. After connecting, it publishes retained `online`. On a clean
shutdown, it explicitly publishes retained `offline` before disconnecting. If
the connection disappears unexpectedly, Mosquitto publishes the Last Will.

The retained status is useful connection evidence, but it is not a complete
lifecycle policy. Application-level offline timeouts belong to a later backend
milestone.

## Commands

Commands are UTF-8 JSON objects published with QoS 1 and `retain=false`:

```json
{
  "protocol_version": 1,
  "command_id": "246efa2b-798e-4c53-a53e-fe1853090044",
  "device_id": "sim-001",
  "issued_at": "2026-09-14T22:15:11.691858Z",
  "type": "set_led",
  "arguments": { "on": true }
}
```

`command_id` is a server-generated UUID v4 and ties the request to its
acknowledgement. `issued_at` is server UTC time. Version 1 supports only:

| Type | Arguments | Behavior |
| --- | --- | --- |
| `set_led` | `{ "on": true }` or `{ "on": false }` | Changes the device LED state. |
| `set_reporting_interval` | `{ "interval_s": 2 }` | Changes telemetry cadence; range 1–60 seconds. |
| `request_diagnostics` | `{}` | Returns concise current device state. |

Commands are not retained because a device reconnecting later must not execute
a stale side effect. QoS 1 asks the broker to deliver at least once while the
device is subscribed, but duplicate delivery remains possible.

## Command acknowledgements

After validating and executing a command, the device publishes a UTF-8 JSON
acknowledgement with QoS 1 and `retain=false`:

```json
{
  "protocol_version": 1,
  "command_id": "246efa2b-798e-4c53-a53e-fe1853090044",
  "device_id": "sim-001",
  "sent_at": "2026-09-14T22:15:11.706Z",
  "status": "succeeded",
  "result": { "on": true }
}
```

A command the device can identify but cannot validate produces
`status: "failed"` and a concise `result.error`. Acknowledgements are not retained
because command history belongs in PostgreSQL. FastAPI uses its own receipt time
for the authoritative `acknowledged_at`; device `sent_at` is retained only as
evidence.

QoS 1 can deliver the same command more than once. The simulator remembers the
100 most recent command IDs for its process lifetime and resends the cached
acknowledgement without executing a duplicate side effect. FastAPI also ignores
acknowledgements for commands already in a terminal state.

## Device time and server time

`sent_at` records when the device says it produced a reading. Device clocks may
be wrong. The future backend will add its own server-side `received_at` timestamp
and use server time for last-seen and lifecycle decisions rather than trusting
the device clock.
