# DeviceOps

[![CI](https://github.com/alichowdary/deviceops/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alichowdary/deviceops/actions/workflows/ci.yml?query=branch%3Amain)

DeviceOps is a web platform for monitoring and controlling IoT devices from one
dashboard. Connected devices can send sensor readings, report whether they are
online, receive commands, and trigger alerts.

Behind the scenes, devices communicate with DeviceOps through MQTT, a
lightweight messaging protocol commonly used by IoT devices. FastAPI validates
and stores their data in PostgreSQL, while a Next.js web app shows the fleet in
real time.

- [Live product](https://deviceops.net)
- [Technical overview](https://deviceops.net/about)
- [MQTT protocol v1](contracts/mqtt.md)
- [Run a device](#run-a-device)

## Demo

<!-- Optional future demo video: add apps/web/public/videos/deviceops-demo.mp4 and point the screenshot link to it. -->

[![DeviceOps Air Sensor example with capability-driven telemetry, numeric charts, controls, and a successful command acknowledgement.](apps/web/public/images/air-sensor-capabilities.png)](https://deviceops.net/about)

_This Air Sensor example advertises only CO₂, VOC index, occupancy, and
air-quality telemetry._

## What DeviceOps can do

- See which devices are online, offline, or have not connected yet.
- View current sensor readings, historical charts, and recent samples.
- Send supported remote commands and track whether each device acknowledged
  success or failure.
- Create alerts for sensor thresholds or devices that remain offline.
- Use one dashboard with different device types; each device describes the
  readings and controls it supports.
- Connect without hardware through the Python simulator, or integrate an ESP32
  using the reusable `DeviceOpsClient` and reference application.

## Architecture

Devices exchange messages with an MQTT broker, which passes sensor data and
commands between devices and the backend. The browser does not connect to MQTT
directly. FastAPI validates each device message and stores accepted data in
PostgreSQL. The Next.js browser first loads saved data through REST, then
receives new committed updates through an authenticated WebSocket connection.

```text
Device / simulator -> mqtt.deviceops.net -> Mosquitto -> FastAPI -> PostgreSQL
                                                               |
Next.js browser <- REST snapshots and history -----------------+
                <- authenticated WebSocket updates
```

Commands use the reverse path and close only on a committed device ACK:

```text
Next.js -> REST -> FastAPI -> MQTT -> Device
Browser <- WebSocket <- FastAPI <- MQTT acknowledgement
```

### Production deployment

| Responsibility | Deployment |
| --- | --- |
| Web console and public site | Vercel at [deviceops.net](https://deviceops.net) |
| FastAPI backend | Fly.io app `deviceops-api-prod` |
| PostgreSQL | Supabase |
| MQTT broker | DeviceOps-managed Eclipse Mosquitto 2.1.2 on Fly.io |
| Device endpoint | `mqtt.deviceops.net:443`, broker authentication, verified TLS |

Local development uses Docker Compose, PostgreSQL, and an intentionally
anonymous plaintext Mosquitto listener. That listener is local-only and is not
the production broker.

## Capability-driven devices

Instead of assuming every device has the same sensors, each device tells
DeviceOps what data it sends and which controls it supports. This lets the same
dashboard work with different kinds of hardware without hard-coding a page for
every sensor.

Technically, a compatible DeviceOps v1 device publishes this description as a
signed, retained capability manifest. Its telemetry descriptors support
`number`, `integer`, `boolean`, and `string` values. The console uses the
manifest's labels, units, ordering, and types to create charts, columns,
controls, and alert choices.

The `air-quality` simulator profile demonstrates the model with `co2_ppm`,
`voc_index`, `occupied`, and `air_quality`. The verified simulator and reference
firmware implement the documented [MQTT v1 contract](contracts/mqtt.md); other
devices are compatible when they implement that contract.

## Device identity and security

When you register a device, DeviceOps gives it a unique ID and a one-time
secret. The device uses that secret to prove its identity when connecting and
sending data.

The device derives separate message-signing and broker credentials from the
secret locally, so users do not manage an additional MQTT password. FastAPI
stores the derived signing key and uses a separate Dynamic Security
administrator identity to provision or revoke the device's restricted
Mosquitto client. Hosted traffic uses verified TLS. DeviceOps messages are
authenticated with HMAC signatures and tied to a boot/process session.

## Run a device

### Hosted path: Python simulator

This is the quickest route and requires no hardware.

1. Create an account at [deviceops.net](https://deviceops.net).
2. In Fleet, add a device and save its device ID and one-time secret.
3. Install and run the simulator from the repository root:

```powershell
cd simulator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id>
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
```

Hosted mode connects to `mqtt.deviceops.net:443` with verified TLS. The device
ID is the MQTT username/client ID, and the simulator derives the broker password
locally from the one-time DeviceOps secret. See the
[simulator guide](simulator/README.md) for profiles and troubleshooting.

### Hosted path: ESP32-S3 reference hardware

The physical reference uses an ESP32-S3, BME280, and onboard WS2812 LED. Copy
`firmware/esp32/include/secrets.example.h` to the ignored `secrets.h`, enter the
Wi-Fi and registered-device values, then build and upload with PlatformIO. The
[firmware guide](firmware/esp32/README.md) covers wiring, exact commands,
expected output, and troubleshooting.

The reference application owns Wi-Fi, sensors, GPIO, conversions, capability
choices, telemetry cadence, and hardware command effects. The reusable
[`DeviceOpsClient`](firmware/esp32/lib/DeviceOpsClient/README.md) owns DeviceOps
protocol plumbing: time synchronization, verified hosted TLS, broker
authentication, topics, sessions, presence, signed envelopes, telemetry
sequencing, command validation, acknowledgements, reconnects, and persisted
reporting intervals.

## Local development

Requirements: Docker Desktop, Python 3.11+, Node.js 20.9+, and npm.

1. Start local infrastructure from the repository root:

   ```powershell
   docker compose up -d
   docker compose ps
   ```

2. Install, migrate, and start the API in a PowerShell terminal:

   ```powershell
   cd apps\api
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e .
   python -m alembic upgrade head
   python -m uvicorn deviceops_api.main:app --host 127.0.0.1 --port 8000
   ```

3. Install and start the web console in another terminal:

   ```powershell
   cd apps\web
   npm ci
   npm run dev
   ```

4. Open <http://localhost:3000>, create an account, and register a device.

5. Run the simulator in explicit local mode from another terminal:

   ```powershell
   cd simulator
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e .
   $env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
   python -m device_simulator --device-id <registered-device-id> --local
   Remove-Item Env:DEVICEOPS_DEVICE_SECRET
   ```

Detailed guides:

- [API and database](apps/api/README.md)
- [Web console](apps/web/README.md)
- [Python simulator](simulator/README.md)
- [ESP32 reference firmware](firmware/esp32/README.md)
- [Reusable ESP32 client](firmware/esp32/lib/DeviceOpsClient/README.md)
- [Local Mosquitto](infra/mosquitto/README.md)
- [Production Mosquitto](infra/mosquitto-prod/README.md)

## Repository map

| Path | Purpose |
| --- | --- |
| `apps/api` | FastAPI REST/WebSocket service, MQTT ingestion, alerts, retention, and migrations |
| `apps/web` | Next.js public site and authenticated operations console |
| `contracts` | Versioned MQTT topic and payload contract |
| `firmware/esp32` | Reusable client plus ESP32-S3/BME280 reference application |
| `simulator` | Python device simulator and capability profiles |
| `infra/mosquitto` | Anonymous plaintext local-development broker configuration |
| `infra/mosquitto-prod` | Current authenticated production broker deployment |

## Intentional boundaries

- Protocol v1 supports scalar telemetry, not arbitrary binary or structured
  visualization payloads.
- Commands use a fixed protocol vocabulary, not device-defined executable
  operations.
- External email, SMS, push, and webhook alert delivery is not implemented.
- OTA firmware updates are not implemented.
- One API process currently owns MQTT ingestion, realtime delivery, offline-rule
  evaluation, and retention cleanup. Multi-worker scaling requires coordination
  or separation of those responsibilities.
- HMAC and session validation protect integrity and normal stale-session
  ordering, but protocol v1 does not claim complete anti-replay protection.

## License

MIT — see [LICENSE](LICENSE).
