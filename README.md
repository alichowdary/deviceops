# DeviceOps

[![CI](https://github.com/alichowdary/deviceops/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alichowdary/deviceops/actions/workflows/ci.yml?query=branch%3Amain)

DeviceOps is a hosted IoT fleet management and observability platform. Devices
connect over an authenticated, versioned MQTT protocol; FastAPI validates and
commits their data to PostgreSQL; and a Next.js console presents live fleet
state, telemetry, commands, events, and alerts.

- [Live product](https://deviceops.net)
- [Technical overview](https://deviceops.net/about)
- [MQTT protocol v1](contracts/mqtt.md)
- [Run a device](#run-a-device)

## Demo

<!-- Optional future demo video: add apps/web/public/videos/deviceops-demo.mp4 and point the screenshot link to it. -->

[![DeviceOps Air Sensor example with capability-driven telemetry, numeric charts, controls, and a successful command acknowledgement.](apps/web/public/images/air-sensor-capabilities.png)](https://deviceops.net/about)

_This Air Sensor example advertises only CO₂, VOC index, occupancy, and
air-quality telemetry._

## Why DeviceOps

- Per-user device ownership with one-time registration secrets.
- Per-device broker credentials plus HMAC-signed MQTT envelopes.
- Capability-driven scalar telemetry, charts, table columns, controls, and
  alert-rule choices.
- REST snapshots followed by authenticated WebSocket updates from committed
  backend state.
- Closed-loop commands that remain pending until the device sends a valid
  acknowledgement.
- Persistent fleet events and metric-threshold or offline-duration alerts.
- A reusable ESP32 `DeviceOpsClient`, a Python simulator, and an ESP32-S3 +
  BME280 reference application.

## Architecture

The browser never connects to MQTT. FastAPI owns MQTT ingestion and command
publishing, validates device messages, commits state, and then sends
owner-scoped updates to the console.

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

A compatible DeviceOps v1 device publishes a signed, retained capability
manifest. Telemetry descriptors support `number`, `integer`, `boolean`, and
`string` values. The console renders labels, units, ordering, charts, columns,
controls, and alert choices from that manifest rather than from a sensor-specific
schema.

The `air-quality` simulator profile demonstrates the model with `co2_ppm`,
`voc_index`, `occupied`, and `air_quality`. The verified simulator and reference
firmware implement the documented [MQTT v1 contract](contracts/mqtt.md); other
devices are compatible when they implement that contract.

## Device identity and security

Each registration creates a stable device ID and a one-time secret. The device
derives separate message-signing and broker credentials locally; users do not
manage an additional MQTT password. FastAPI stores the derived signing key and
uses a separate Dynamic Security administrator identity to provision or revoke
the device's restricted Mosquitto client. Hosted traffic uses verified TLS, and
DeviceOps messages are HMAC-authenticated and bound to a boot/process session.

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
