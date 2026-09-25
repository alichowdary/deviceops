# Local Mosquitto broker

This directory contains the MQTT broker configuration used only for local
DeviceOps development. The root `docker-compose.yml` runs Eclipse Mosquitto
2.1.2 and publishes port 1883 so simulators and LAN-connected reference hardware
can reach it.

```powershell
docker compose up -d mosquitto
docker compose ps mosquitto
docker compose logs mosquitto
```

The listener is intentionally anonymous, plaintext, and non-persistent. Use it
only on a trusted development machine/network. It is not the production broker
configuration and must not be exposed publicly.

The local FastAPI defaults already consume `localhost:1883`. Start a simulator
with `--local`. For an ESP32, explicitly enable `DEVICEOPS_LOCAL_MQTT` in the
ignored `firmware/esp32/include/secrets.h` and set the broker to the development
computer's LAN address. Signed DeviceOps envelopes remain required in local
mode even though transport-level broker authentication is disabled.

Production uses the separate authenticated deployment documented in
[`../mosquitto-prod/README.md`](../mosquitto-prod/README.md).
