# Device simulator

This small Python process behaves like one registered DeviceOps device. It
connects to Mosquitto, publishes authenticated, gradually changing telemetry,
maintains an authenticated retained online/offline status, and publishes an
authenticated retained capability manifest after each connection. It also verifies
and executes the three version 1 commands documented in
[`../contracts/mqtt.md`](../contracts/mqtt.md).

## Install

From the repository root in PowerShell, create an isolated virtual environment
and install the simulator with its pinned Paho MQTT dependency:

```powershell
cd simulator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Paho MQTT 2.1.0 declares Python 3.7 or newer and provides a universal Python 3
wheel. This simulator is configured for Python 3.11 or newer and has been tested
in this repository with Python 3.14.5.

## Run

Start the broker from the repository root, then run the simulator from this
directory with the virtual environment activated. Register a device through the
API first. Supply its one-time plaintext secret through the
`DEVICEOPS_DEVICE_SECRET` environment variable; the simulator never prints it.
Using `Read-Host` avoids putting the secret in PowerShell command history:

```powershell
docker compose up -d
cd simulator
.\.venv\Scripts\Activate.ps1
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id>
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
```

`--device-id` is required. The telemetry interval defaults to five seconds, the
broker host to `localhost`, and the broker TCP port to `1883`. Override them with
standard CLI options:

```powershell
python -m device_simulator --device-id <registered-device-id> --interval 2.5 --broker-host localhost --broker-port 1883
```

Startup fails before connecting if `DEVICEOPS_DEVICE_SECRET` is absent or empty.
The secret is hashed locally to derive the MQTT signing key and is never sent in
an MQTT payload.

After connecting, the simulator subscribes to its device-specific command topic
with QoS 1. Supported commands turn its internal LED state on or off, change the
running telemetry interval within 1–60 seconds, and return diagnostics. State
changes and failures are printed in the simulator terminal. Acknowledgements use
QoS 1 and are not retained.

The MQTT callback and telemetry loop share LED, interval, and diagnostic state
through a condition lock. Changing the interval wakes the telemetry loop so the
new cadence takes effect immediately. The simulator caches the 100 most recent
acknowledgements for its process lifetime; duplicate QoS 1 deliveries resend the
same acknowledgement without repeating the side effect.

The simulator creates one random 16-byte MQTT session ID when the process starts
and uses it for its Last Will, status, telemetry, acknowledgements, and command
verification. Automatic reconnects within that process keep the same session ID;
restarting the simulator creates a new one.

Its capability manifest declares the telemetry it actually emits: temperature,
battery, RSSI, and uptime. It declares LED, reporting-interval, and diagnostics
commands, uses QoS 1 with retention, and is re-signed with the current session
and a fresh UTC `sent_at` after every successful command-topic subscription.

Press Ctrl+C for a clean shutdown. The simulator publishes an authenticated,
retained `offline` envelope before disconnecting. If the process or network
connection disappears without a clean disconnect, its authenticated MQTT Last
Will makes Mosquitto publish retained `offline`.

If the broker is unavailable, the simulator exits with an error and reminds you
how to start it.

## Observe messages

These commands use the MQTT tools inside the existing Mosquitto container:

```powershell
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/telemetry" -v
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/status" -v
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/capabilities" -v
```
