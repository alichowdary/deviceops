# Device simulator

This small Python process behaves like one DeviceOps device. It connects to the
local Mosquitto broker, publishes gradually changing telemetry, and maintains a
retained online/offline status. Its MQTT contract is documented in
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
directory with the virtual environment activated:

```powershell
docker compose up -d
cd simulator
.\.venv\Scripts\Activate.ps1
python -m device_simulator
```

The default device ID is `sim-001`, and the default interval is five seconds.
Override either with standard CLI options:

```powershell
python -m device_simulator --device-id sim-002 --interval 2.5
```

Press Ctrl+C for a clean shutdown. The simulator publishes retained `offline`
before disconnecting. If the process or network connection disappears without a
clean disconnect, its MQTT Last Will makes Mosquitto publish retained `offline`.

If the broker is unavailable, the simulator exits with an error and reminds you
how to start it.

## Observe messages

These commands use the MQTT tools inside the existing Mosquitto container:

```powershell
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/telemetry" -v
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/status" -v
```
