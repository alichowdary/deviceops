# DeviceOps

DeviceOps will be an IoT fleet management and observability platform.
Milestones 1A through 2 provide a local MQTT broker, a versioned device protocol,
a Python device simulator, and a FastAPI ingestion service backed by PostgreSQL.
The browser application and firmware are not implemented yet.

The implemented flow is:

```text
Python simulator -> MQTT -> Mosquitto -> FastAPI -> PostgreSQL
```

FastAPI owns the MQTT subscriber and exposes read-only verification endpoints.
Setup and run instructions are in [`apps/api/README.md`](apps/api/README.md).

## Device protocol and simulator

The version 1 MQTT topic and payload contract is in
[`contracts/mqtt.md`](contracts/mqtt.md). It defines telemetry and retained device
presence behavior and reserves command topics without implementing commands.

Installation, run, and observation instructions for the Python simulator are in
[`simulator/README.md`](simulator/README.md). With the broker running and the
simulator environment installed, start the default `sim-001` device with:

```powershell
cd simulator
.\.venv\Scripts\Activate.ps1
python -m device_simulator --device-id sim-001 --interval 5
```

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

The broker is available to this computer at `127.0.0.1:1883`. Compose maps the
host's loopback port to port `1883` inside the container. It mounts
`infra/mosquitto/mosquitto.conf` read-only. Compose creates its default network;
we define no custom networks or data volumes, and broker persistence is disabled.
The official image itself creates anonymous volumes at `/mosquitto/data` and
`/mosquitto/log`; this configuration does not write broker state or log files there.

**Local development only:** anonymous MQTT access is intentionally insecure.
Clients that can reach the broker can publish and subscribe without credentials,
and traffic is unencrypted. The host port is bound to loopback, not the LAN.
Anonymous access will be replaced with authenticated device access in a later
milestone. Do not use this configuration in production. There is no MQTT
WebSocket listener.

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

Milestone 2 stops at MQTT ingestion, PostgreSQL persistence, and a read-only REST
API. WebSockets, Next.js, authentication, commands, alerts, firmware, and cloud
infrastructure remain future work.
