# Device simulator

This small Python process behaves like one registered DeviceOps device. It
connects to the configured MQTT broker, publishes authenticated, gradually
changing telemetry,
maintains an authenticated retained online/offline status, and publishes an
authenticated retained capability manifest after each connection. Selectable
profiles let it represent materially different devices while keeping the
existing behavior as the default. It also verifies and executes the supported
version 1 commands documented in
[`../contracts/mqtt.md`](../contracts/mqtt.md).

## Install

Install Git and Python 3.11 or newer. Clone the repository, then create an
isolated virtual environment and install the simulator with its pinned Paho MQTT
dependency:

```powershell
git clone https://github.com/alichowdary/deviceops.git
cd deviceops\simulator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Paho MQTT 2.1.0 declares Python 3.7 or newer and provides a universal Python 3
wheel. This simulator is configured for Python 3.11 or newer and has been tested
in this repository with Python 3.14.5.

## Hosted quick start

1. Create an account at [deviceops.net](https://deviceops.net).
2. Open Fleet, select **Add device**, and copy the generated device ID and
   one-time DeviceOps secret before closing the dialog.
3. Complete the [installation](#install), then run the following commands from
   the repository root. `Read-Host` keeps the secret out of PowerShell history:

```powershell
cd simulator
.\.venv\Scripts\Activate.ps1
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id>
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
```

This default hosted mode connects to `mqtt.deviceops.net:443` with verified TLS.
The MQTT username and client ID are the registered device ID. The simulator
derives the broker password locally from the device secret; no separate MQTT
password is requested, stored, or printed.

`--device-id` is required. The `default` profile and five-second telemetry
interval are used unless overridden.

4. Keep the process running and open the new device in Fleet. Its status should
   become Online and telemetry should begin updating. Press Ctrl+C to publish a
   clean offline status, then remove the secret from the shell as shown above.

## Local and custom brokers

### Local mode

For reproducible local development, start the repository broker and select the
explicit anonymous plaintext local mode:

```powershell
docker compose up -d
cd simulator
.\.venv\Scripts\Activate.ps1
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id> --local --interval 2
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
```

The local Docker/Mosquitto stack remains anonymous plaintext MQTT at
`localhost:1883`. Local mode rejects broker overrides and MQTT credential
environment variables so it cannot silently become an authenticated remote
connection.

### Custom broker mode

Advanced operators can select `--custom`, provide an explicit broker host, and
optionally override the port, TLS, and paired MQTT credentials:

```powershell
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
$env:DEVICEOPS_MQTT_USERNAME = Read-Host "MQTT username"
$env:DEVICEOPS_MQTT_PASSWORD = Read-Host "MQTT password"
python -m device_simulator --device-id <registered-device-id> `
  --custom `
  --broker-host <your-mqtt-broker-host> `
  --broker-port 8883 --tls
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
Remove-Item Env:DEVICEOPS_MQTT_USERNAME
Remove-Item Env:DEVICEOPS_MQTT_PASSWORD
```

Custom mode defaults to port 1883 without TLS. `--tls` uses Python's system CA
trust store and verifies both the broker
certificate chain and hostname. Broker username/password authentication does
not replace the existing per-device HMAC envelope authentication. The simulator
never prints either password.

Choose the alternate portable sensor with `--profile portable-sensor`:

```powershell
python -m device_simulator --device-id <registered-device-id> --profile portable-sensor
```

To exercise a device with no historical first-class telemetry fields, use the
air-quality profile:

```powershell
python -m device_simulator --device-id <registered-device-id> --profile air-quality
```

The available profiles are:

- `default`: preserves the original simulator behavior. It emits temperature,
  battery, RSSI, and uptime, and supports LED, reporting-interval, and
  diagnostics commands.
- `portable-sensor`: emits temperature, battery, ambient light, motion state,
  RSSI, and uptime. It supports diagnostics only. Ambient light and motion are
  additional protocol metrics; motion is boolean and therefore is not charted
  by the capability-driven console.
- `air-quality`: emits only dynamic `co2_ppm`, `voc_index`, `occupied`, and
  `air_quality` metrics. It supports diagnostics only. CO₂ and VOC index are
  charted numeric values; occupied and air quality are displayed as boolean and
  string values without numeric charts. It deliberately emits none of the six
  historical first-class metric names.

Run `python -m device_simulator --help` to see all CLI options.

Startup fails before connecting if `DEVICEOPS_DEVICE_SECRET` is absent or empty,
if only one custom broker credential is configured, or if hosted/local/custom
options are combined ambiguously. Hosted mode rejects
`DEVICEOPS_MQTT_USERNAME` and `DEVICEOPS_MQTT_PASSWORD` because it always derives
the device's broker password from `DEVICEOPS_DEVICE_SECRET`.
The secret is hashed locally to derive the MQTT signing key and is never sent in
an MQTT payload.

After connecting, the simulator subscribes to its device-specific command topic
with QoS 1. The selected profile controls which commands are advertised and
accepted. An unadvertised command receives a normal failed acknowledgement
instead of changing simulator state. State changes and failures are printed in
the simulator terminal. Acknowledgements use QoS 1 and are not retained.

The MQTT callback and telemetry loop share LED, interval, and diagnostic state
through a condition lock. Changing the interval wakes the telemetry loop so the
new cadence takes effect immediately. The simulator caches the 100 most recent
acknowledgements for its process lifetime; duplicate QoS 1 deliveries resend the
same acknowledgement without repeating the side effect.

The simulator creates one random 16-byte MQTT session ID when the process starts
and uses it for its Last Will, status, telemetry, acknowledgements, and command
verification. Automatic reconnects within that process keep the same session ID;
restarting the simulator creates a new one.

Its capability manifest declares the telemetry and commands of the selected
profile, uses QoS 1 with retention, and is re-signed with the current session and
a fresh UTC `sent_at` after every successful command-topic subscription.

Press Ctrl+C for a clean shutdown. The simulator publishes an authenticated,
retained `offline` envelope before disconnecting. If the process or network
connection disappears without a clean disconnect, its authenticated MQTT Last
Will makes the broker publish retained `offline`.

If the broker is unavailable, the simulator exits with an error. Local mode also
reminds you how to start the Docker broker.

## Observe messages

These commands use the MQTT tools inside the existing Mosquitto container:

```powershell
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/telemetry" -v
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/status" -v
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/capabilities" -v
```
