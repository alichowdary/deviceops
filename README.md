# DeviceOps

DeviceOps is an incremental IoT fleet management and observability project.
Milestones 1A through 7 provide a local MQTT broker, a versioned device protocol,
a Python device simulator, a FastAPI ingestion service backed by PostgreSQL, a
Next.js fleet console with live updates and device-specific remote commands, and
a verified ESP32-S3 reference firmware project. Milestone 7 adds user
authentication, per-user device ownership, one-time device registration
credentials, authenticated device messages, and owner-isolated live updates.
Milestone 8 adds a persistent fleet activity feed, owner-scoped alert rules, and
durable active/resolved alert lifecycles evaluated from committed telemetry and
device status. Milestone 9 Phase 1 adds signed, retained device capability
manifests, latest-manifest persistence, an owner-scoped REST read, and realtime
update compatibility. Phase 2 makes Device Detail render its metric cards,
numeric charts, recent-sample columns, and existing protocol-v1 controls from
that manifest, including live capability changes.

The implemented flow is:

```text
Device (simulator or ESP32) -> MQTT -> Mosquitto -> FastAPI -> PostgreSQL
                                                    |
                                                    +-> REST snapshots/history -> Next.js
                                                    +-> WebSocket event deltas --^

Next.js -> REST command -> FastAPI -> MQTT -> Mosquitto -> Device
Next.js <- WebSocket update <- FastAPI <- MQTT acknowledgement <-+
```

FastAPI owns MQTT ingestion and publication and exposes REST and WebSocket
endpoints. The browser connects only to FastAPI and never connects to MQTT.
Backend setup is in
[`apps/api/README.md`](apps/api/README.md); frontend setup is in
[`apps/web/README.md`](apps/web/README.md).

## Web console

The frontend provides a compact fleet inventory at <http://localhost:3000> and
device detail pages at `/devices/{deviceId}`. It shows real API state, latest
telemetry, server-time history charts, and recent samples. REST supplies the
initial snapshot and history. New committed telemetry and device status events
arrive through FastAPI's `/ws` endpoint and update the console in place. The
device page renders only telemetry and existing command controls declared by the
device manifest, and updates persisted command status from acknowledgements. The
explicit Refresh control remains available. The `/events` page provides a persistent,
owner-scoped activity feed for registration, connectivity transitions, and
command lifecycle events without duplicating routine telemetry.
The `/alerts` page shows active and recently resolved alerts alongside per-device
metric threshold and offline-duration rule definitions. Alert state updates live,
persists across refreshes, and is also recorded in the Events feed.

```powershell
cd apps\web
npm install
npm run dev
```

## Device protocol and simulator

The version 1 MQTT topic and payload contract is in
[`contracts/mqtt.md`](contracts/mqtt.md). It defines telemetry, retained device
presence, capability discovery, commands, acknowledgements, and their delivery
semantics.

Installation, run, and observation instructions for the Python simulator are in
[`simulator/README.md`](simulator/README.md). Register a device through the API or
web console first. With the broker running and the simulator environment
installed, start that registered device with:

```powershell
cd simulator
.\.venv\Scripts\Activate.ps1
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id> --interval 5
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
```

## ESP32 reference firmware

The [`firmware/esp32`](firmware/esp32) PlatformIO project contains the verified
reference implementation for an ESP32-S3, a BME280 at address `0x76`, and the
board's WS2812 RGB LED. It publishes real environmental telemetry and implements
the same presence and command protocol as the simulator. See the
[`firmware/esp32/README.md`](firmware/esp32/README.md) for wiring, local secrets,
build, upload, and serial-monitor instructions. This firmware is one compatible
device implementation, not a requirement for every DeviceOps device.

## Local broker

Prerequisite: Docker Desktop must be running with Linux containers and the
`docker compose` command available. No global MQTT CLI tools are needed for the
broker smoke test. Run all commands from the repository root.

```powershell
docker compose config
docker compose up -d
docker compose ps
docker compose logs mosquitto
```

The first start downloads the official
[Eclipse Mosquitto image](https://hub.docker.com/_/eclipse-mosquitto), pinned to
`2.1.2-alpine` so the chosen version is explicit. Logs should show the configuration
loading, a listening socket on port `1883`, and Mosquitto running.

The broker is available to this computer at `127.0.0.1:1883`. Compose publishes
port `1883` on all host interfaces so a physical device on the local network can
reach it. It mounts
`infra/mosquitto/mosquitto.conf` read-only. Compose creates its default network;
we define no custom networks or data volumes, and broker persistence is disabled.
The official image itself creates anonymous volumes at `/mosquitto/data` and
`/mosquitto/log`; this configuration does not write broker state or log files there.

**Local development only:** anonymous broker access is intentionally insecure.
Clients that can reach the broker can publish and subscribe without credentials,
and traffic is unencrypted. The broker may be reachable from the LAN when the
host firewall permits it. DeviceOps authenticates version 1 device envelopes at
the application layer; broker authentication and TLS remain future work. Do not
use this configuration in production. There is no MQTT WebSocket listener.

## Manual MQTT smoke test

Open two PowerShell terminals in the repository root. Both clients run inside the
broker container; `127.0.0.1` in these commands refers to that container.

In **terminal 1**, start the subscriber:

```powershell
docker compose exec mosquitto mosquitto_sub -h 127.0.0.1 -p 1883 -t deviceops/v1/test -C 1 -W 60 -v -d
```

Wait until it prints `received SUBACK`, confirming the subscription is active.
Within 60 seconds, run the publisher in **terminal 2**:

```powershell
docker compose exec mosquitto mosquitto_pub -h 127.0.0.1 -p 1883 -t deviceops/v1/test -m hello-deviceops
```

Terminal 1 should print this line among the debug messages, then exit successfully:

```text
deviceops/v1/test hello-deviceops
```

`-C 1` exits after one message, `-W 60` sets a 60-second message wait limit,
`-v` prints the topic and payload, and `-d` shows the connection/subscription
handshake. The message is not retained: subscribe before publishing. If the
subscriber times out, start it again and publish after its SUBACK.

To separately check that Windows can reach the published TCP port:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 1883
```

Expect `TcpTestSucceeded : True`. This checks host port reachability; the
publish/subscribe test above verifies actual MQTT message delivery.

## Stop and troubleshooting

Stop the local infrastructure while preserving PostgreSQL data:

```powershell
docker compose down
```

Start again with `docker compose up -d`. Mosquitto state is not saved across restarts;
PostgreSQL data persists in its named volume. `docker compose down --volumes`
deliberately deletes the development database as well as container volumes.
After editing `mosquitto.conf`, run `docker compose restart mosquitto` to reload it.

- If Docker reports that it cannot connect to the daemon, start Docker Desktop,
  wait until its engine is running, and retry.
- If port `1883` is already allocated, stop the conflicting local service before
  starting this broker.
- If the container exits, inspect `docker compose logs mosquitto` and check the
  mounted configuration file. A valid Compose file alone does not prove that
  Mosquitto started successfully.

## What the test demonstrates

- **Publisher:** `mosquitto_pub` sends the payload `hello-deviceops`.
- **Subscriber:** `mosquitto_sub` asks to receive messages on `deviceops/v1/test`.
- **Broker:** Mosquitto accepts client connections and routes the publisher's
  message to subscribers whose subscriptions match its topic.
- **Topic:** `deviceops/v1/test` is the message's routing name. `deviceops/v1`
  establishes our planned versioned namespace; it is not a file or HTTP URL.
- **Port 1883:** the conventional TCP port for unencrypted MQTT, used by both
  clients to connect to the broker.

Milestone 6 supports battery-powered simulators and battery-free environmental
sensors through the same ingestion and console paths, and includes the verified
ESP32 reference firmware. Milestone 7 adds user authentication, ownership,
device registration credentials, authenticated MQTT envelopes, and isolated
realtime delivery. Milestone 8 adds persistent fleet Events, alert-rule
management, and automatic active/resolved alert lifecycles through REST and
owner-isolated WebSockets. Milestone 9 adds authenticated capability discovery
and a capability-driven Device Detail while retaining a read-only legacy sample
view for devices that have not advertised a manifest. External alert
notification delivery, broker-level MQTT authentication and TLS, OTA updates,
and cloud infrastructure remain future work.
