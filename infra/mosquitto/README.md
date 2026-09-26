# Local Mosquitto broker

Most hosted DeviceOps users do not need this broker. Hosted devices connect to
the production service at `mqtt.deviceops.net`.

This local broker is for developers running the API and devices on their own
computer or local network. An MQTT broker is the message relay between devices
and FastAPI. The root `docker-compose.yml` runs Eclipse Mosquitto 2.1.2 on port
1883.

## Run the local broker

### Step 1 — Install and start Docker Desktop

Install Docker Desktop, open it, and wait until the Docker engine reports that
it is running. Verify from PowerShell:

```powershell
docker --version
```

### Step 2 — Start Mosquitto

Open PowerShell in the repository root—the folder containing
`docker-compose.yml`—and run:

```powershell
docker compose up -d mosquitto
```

Docker should create or start the `mosquitto` service in the background.

### Step 3 — Check the container

```powershell
docker compose ps mosquitto
```

The service should be listed as running, with local port 1883 published.

### Step 4 — View logs if needed

```powershell
docker compose logs mosquitto
```

Startup logs should show the listener opening without a configuration error.

### Step 5 — Stop the broker

From the repository root, run:

```powershell
docker compose stop mosquitto
```

Use `docker compose up -d mosquitto` again the next time it is needed.

## Local-only security boundary

This listener is intentionally anonymous, plaintext, and non-persistent. Use it
only on a trusted development machine and network. Never expose port 1883 to the
public internet. This is not the production broker configuration.

The local FastAPI defaults connect to `localhost:1883`. Here, `localhost` means
the same computer running Docker. Start the Python simulator with `--local`.

For an ESP32, enable `DEVICEOPS_LOCAL_MQTT` in the ignored
`firmware/esp32/include/secrets.h` and use the development computer's LAN IP. A
LAN IP identifies that computer on the local network; `localhost` on the ESP32
would mean the ESP32 itself. Signed DeviceOps envelopes remain required even
though local broker authentication is disabled.

Production uses the separate authenticated deployment documented in
[`../mosquitto-prod/README.md`](../mosquitto-prod/README.md).
