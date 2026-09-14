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
| Commands (reserved) | `deviceops/v1/devices/{device_id}/commands` |
| Command acknowledgements (reserved) | `deviceops/v1/devices/{device_id}/command-acks` |

The commands and command acknowledgement topics are reserved for a later
milestone. Their payloads and behavior are not defined or implemented yet.

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

## Device time and server time

`sent_at` records when the device says it produced a reading. Device clocks may
be wrong. The future backend will add its own server-side `received_at` timestamp
and use server time for last-seen and lifecycle decisions rather than trusting
the device clock.
