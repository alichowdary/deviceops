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
| Capabilities | `deviceops/v1/devices/{device_id}/capabilities` |
| Commands | `deviceops/v1/devices/{device_id}/commands` |
| Command acknowledgements | `deviceops/v1/devices/{device_id}/command-acks` |

Commands travel from FastAPI to a device. Acknowledgements travel from the
device back to FastAPI. Browsers never connect to MQTT.

## Authenticated envelope

Every MQTT payload is a UTF-8 JSON envelope. The `body` string contains the exact
existing payload described in the sections below:

```json
{
  "auth_version": 1,
  "session_id": "0123456789abcdef0123456789abcdef",
  "body": "<exact original MQTT payload as a UTF-8 string>",
  "signature": "<64 lowercase hexadecimal HMAC-SHA256 characters>"
}
```

The signing key is the raw SHA-256 digest of the device secret. Device-to-server
messages use direction `d2s`; server-to-device commands use `s2d`. The signature
is lowercase hexadecimal HMAC-SHA256 over this exact UTF-8 string:

```text
deviceops-auth-v1\n<direction>\n<topic>\n<session_id>\n<body_sha256_hex>
```

`topic` is the exact full MQTT topic, and `body_sha256_hex` is the lowercase
SHA-256 digest of the exact UTF-8 bytes of `body`. The device secret itself is
never sent over MQTT.

Each device process or boot uses a fresh, random 16-byte session ID encoded as 32
lowercase hexadecimal characters. A valid signed `online` message establishes
the backend's current session. Telemetry, capabilities, acknowledgements, and `offline` are
accepted only for that session. Commands are signed for that same current
session. This prevents a normally delayed Last Will from an older session from
overwriting a newer online state. The Python simulator keeps one session ID for
its process lifetime, including automatic reconnects, and creates a new one when
restarted.

Version 1 has no general anti-replay mechanism. A captured authenticated
telemetry, acknowledgement, or status envelope can be replayed. In particular,
replaying a previously valid signed `online` envelope can re-establish that older
session. Session matching still handles the common stale-Last-Will ordering case
after a newer session has been established. Stronger replay protection is
intentionally deferred.

### Interoperability test vector

The following fixed values are for implementation testing only. The secret must
never be used by a real device.

| Input | Exact value |
| --- | --- |
| Device secret | `deviceops-test-only-secret` |
| Session ID | `0123456789abcdef0123456789abcdef` |
| Direction | `d2s` |
| Topic | `deviceops/v1/devices/test-device/telemetry` |
| Body | `{"message":"hello-deviceops"}` |
| Derived signing key, SHA-256 hex | `d69100dd57af5ccdfb56800af1ca5bfa04b688994a8cebbfda34765c0f42d35a` |
| Body SHA-256 hex | `532c3453e5647433abfbf93581127aa79b85426b5a8e269dbda1822a37802f42` |
| HMAC-SHA256 signature | `65c72f03a11bb3fb66452ba74ad9ecf142e7da2a3c49449cd76f47530207c798` |

The exact UTF-8 HMAC input is:

```text
deviceops-auth-v1
d2s
deviceops/v1/devices/test-device/telemetry
0123456789abcdef0123456789abcdef
532c3453e5647433abfbf93581127aa79b85426b5a8e269dbda1822a37802f42
```

## Telemetry

The telemetry envelope body is this existing JSON object serialized as a string:

```json
{
  "protocol_version": 1,
  "device_id": "sim-001",
  "sent_at": "2026-09-14T16:30:05.123Z",
  "sequence": 1,
  "metrics": {
    "temperature_c": 23.01,
    "humidity_pct": 54.52,
    "pressure_hpa": 1025.31,
    "rssi_dbm": -51,
    "uptime_s": 12
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
| `metrics.battery_pct` | number, optional | Remaining battery percentage from `0` to `100`. Omit it for devices without a battery. |
| `metrics.humidity_pct` | number, optional | Relative humidity percentage from `0` to `100`. |
| `metrics.pressure_hpa` | number, optional | Atmospheric pressure in hectopascals. |
| `metrics.rssi_dbm` | integer | Wi-Fi received signal strength in dBm; values nearer zero are stronger. |
| `metrics.uptime_s` | integer | Monotonically increasing seconds since the device process started. |

`temperature_c`, `rssi_dbm`, and `uptime_s` are required in version 1.
`battery_pct`, `humidity_pct`, and `pressure_hpa` are first-class optional
measurements. Devices report the measurements they actually support and omit
unavailable optional measurements instead of publishing fabricated values. The
API represents an omitted first-class measurement as `null` in REST and
WebSocket responses.

Metrics stay under the `metrics` object so compatible sensors can be added
without mixing measurements with message metadata. Additional numeric or
structured measurements remain accepted and are stored in `additional_metrics`.
The additive capability manifest below now supplies the version 1 dynamic metric
definitions; it does not change the telemetry payload or topic.

Telemetry uses QoS 0 and is not retained. It is frequent, and a later reading
supersedes a missed individual reading, so broker acknowledgement and retry are
not required for every sample.

## Device capabilities

A device publishes its latest manifest to
`deviceops/v1/devices/{device_id}/capabilities` with QoS 1 and `retain=true`.
The body uses the normal authenticated `d2s` envelope and the current boot or
process session. A device republishes after each successful connection or
reconnection, after its signed `online` status establishes that session. FastAPI
accepts a retained delivery after restart only when its signature and session
match the device's current session; an older retained session cannot overwrite
the latest stored manifest.

```json
{
  "protocol_version": 1,
  "capabilities_version": 1,
  "device_id": "dev-example",
  "sent_at": "2026-09-19T12:00:00Z",
  "telemetry": {
    "temperature_c": {
      "type": "number",
      "label": "Temperature",
      "unit": "°C"
    },
    "uptime_s": {
      "type": "integer",
      "label": "Uptime",
      "unit": "s"
    }
  },
  "commands": {
    "set_led": {
      "label": "LED",
      "arguments": {
        "on": { "type": "boolean", "label": "On" }
      }
    }
  }
}
```

Both `protocol_version` and `capabilities_version` must be `1`; `device_id`
must match the topic; and `sent_at` must be UTC. `telemetry` and `commands` are
objects. Metric and argument names use lowercase safe identifiers beginning
with a letter and containing only letters, digits, and underscores. Labels are
1–80 characters and optional units are 1–24 characters. Supported value types
are `number`, `integer`, `boolean`, and `string`. Numeric command arguments may
include finite `min` and `max` values, with `min <= max`; integer descriptors
require integer bounds, and nonnumeric descriptors cannot have bounds. The
manifest body is limited to 16 KiB, 128 telemetry definitions, and 16 arguments
per command.

Version 1 command capabilities may be any subset of `set_led`,
`set_reporting_interval`, and `request_diagnostics`, using their existing
protocol-v1 argument shapes. This declaration does not enable arbitrary command
execution. Telemetry may declare the first-class metrics above or additional
safe names stored by ingestion in `additional_metrics`.

`device_id` remains the stable protocol identity. A future human-friendly
display name would be separate metadata and must not replace it.

## Presence/status

The status envelope body is exactly the text `online` or `offline`. The envelope
uses QoS 1 and is retained so a new subscriber immediately receives the device's
latest known state rather than waiting for another transition.

Before connecting, a device configures a retained, QoS 1 authenticated envelope
whose body is `offline` on its status topic. After connecting, it publishes a
retained authenticated `online` envelope using the same session ID. On a clean
shutdown, it explicitly publishes authenticated `offline` before disconnecting.
If the connection disappears unexpectedly, Mosquitto publishes the signed Last
Will.

The retained status is useful connection evidence, but it is not a complete
lifecycle policy. Application-level offline timeouts belong to a later backend
milestone.

## Commands

The command envelope body is this existing JSON object serialized as a string.
The outer envelope is published with QoS 1 and `retain=false`:

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

After validating and executing a command, the device publishes an authenticated
envelope whose body is this existing JSON acknowledgement. It uses QoS 1 and
`retain=false`:

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
be wrong. FastAPI adds its own server-side `received_at` timestamp and uses
server time for last-seen and lifecycle decisions rather than trusting the
device clock.
