# DeviceOps agent guidance

- DeviceOps is an IoT fleet management and observability platform.
- Make and verify focused changes without silently expanding their scope.
- The logical flow is: Devices -> MQTT broker -> FastAPI -> PostgreSQL/WebSockets -> Next.js.
- Local development uses Eclipse Mosquitto; production uses DeviceOps-managed Mosquitto on Fly.io at `mqtt.deviceops.net` with broker authentication and verified TLS.
- Browsers must not communicate directly with MQTT.
- The web console loads snapshots and history through REST, then receives new committed device events through FastAPI WebSockets.
- Operator commands go through FastAPI and MQTT; only a committed device acknowledgement can mark a command succeeded or failed.
- The device protocol lives in `contracts/mqtt.md`.
- Device IDs are stable identifiers, and the device protocol is versioned.
- Do not add infrastructure merely to make the project sound impressive.
- Avoid premature microservices and abstractions.
- Do not silently make significant architecture changes.
