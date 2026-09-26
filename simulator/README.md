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

## Quick start: connect your first simulated device

The normal path connects directly to hosted DeviceOps. MQTT is the lightweight
messaging protocol the simulator uses to exchange data and commands with
DeviceOps.

### Step 1 — Install prerequisites

Install [Git](https://git-scm.com/downloads) and Python 3.11 or newer. Open
PowerShell and confirm both commands work:

```powershell
git --version
python --version
```

The second command should report Python 3.11 or newer.

### Step 2 — Clone DeviceOps

Run:

```powershell
git clone https://github.com/alichowdary/deviceops.git
cd deviceops
```

`cd` means “change directory.” After these commands, PowerShell is working from
the downloaded repository folder.

### Step 3 — Create a DeviceOps account

Open [deviceops.net](https://deviceops.net), create an account, and sign in. Open
**Fleet** after authentication.

### Step 4 — Register a device

In Fleet, select **Add device**. You may give it a friendly name. Copy both the
generated Device ID and the one-time DeviceOps secret before closing the dialog.

The Device ID identifies this device. The secret proves that the simulator is
allowed to connect as that device. There is no second MQTT password to copy.

### Step 5 — Install the simulator

From the repository root, run:

```powershell
cd simulator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

`.venv` is an isolated Python environment for this project. Once activated,
Python packages installed in this terminal stay separate from other projects.

### Step 6 — Start the simulator

Run these commands from the `simulator` folder with `.venv` active:

```powershell
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id>
```

Text inside `<...>` is a placeholder. Replace it with your own value and do not
type the angle brackets. Here, replace `<registered-device-id>` with the Device
ID copied from Fleet. `Read-Host` asks for the secret privately instead of
placing it directly in your shell history.

Hosted mode connects to `mqtt.deviceops.net:443` with verified TLS. The
simulator derives its broker password locally from the DeviceOps secret.

### Step 7 — Confirm it worked

The terminal should report a successful MQTT connection and begin printing
telemetry. In Fleet, open the device and confirm that it becomes **Online** and
that readings begin appearing.

The `default` profile publishes every five seconds unless you choose another
interval.

### Step 8 — Stop the simulator

Press Ctrl+C for a clean shutdown, then remove the secret from this PowerShell
session:

```powershell
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
```

Removing the environment variable prevents a later command in the same terminal
from accidentally reusing the device secret.

## Local and custom brokers

### Local mode

For reproducible local development, open a new PowerShell terminal at the
repository root. Start the repository broker, then enter the simulator folder
and select the explicit anonymous plaintext local mode:

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

Run this from the `simulator` folder with `.venv` active:

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

From the repository root, these commands use the MQTT tools inside the existing
Mosquitto container:

```powershell
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/telemetry" -v
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/status" -v
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t "deviceops/v1/devices/+/capabilities" -v
```
