# DeviceOps production MQTT broker

This directory defines the future DeviceOps production MQTT broker. It is deliberately separate from `infra/mosquitto/` and the root `docker-compose.yml`: those remain the anonymous, plaintext local-development broker and are not changed by this package.

This package is prepared for deployment but has not been deployed.

## Architecture

Production clients will use raw MQTT over verified TLS (not MQTT over WebSockets and not HTTP):

```text
MQTT client
  -> TLS to mqtt.deviceops.net:443
  -> Fly Proxy (TLS termination)
  -> plaintext TCP on Fly's private network
  -> Mosquitto 2.1.2 on 0.0.0.0:1883
```

`fly.toml` exposes only external TCP port 443 and applies only Fly's `tls` handler. It does not expose ports 1883 or 8883 publicly and has no HTTP handler. Port 443 is compatible with Fly's normal shared IPv4 path; do not allocate a dedicated IPv4 for this app.

The deployment intentionally consists of one `shared-cpu-1x` Machine with 256 MB RAM in `iad` and one 1 GB Fly volume. It does not scale to zero because MQTT clients keep long-lived connections. This is a single-broker design: do not create a second Machine unless the persistence architecture is redesigned first, because Fly volumes are attached to individual Machines and are not replicated broker storage.

## First boot and Dynamic Security

The image loads the Dynamic Security plugin from `/usr/lib/mosquitto_dynamic_security.so`. Its mutable configuration is `/mosquitto/data/dynamic-security.json` on the persistent volume.

On first boot only, the entrypoint requires these Fly secrets/environment variables:

- `DEVICEOPS_DYNSEC_ADMIN_PASSWORD` (required, no default)
- `DEVICEOPS_DYNSEC_ADMIN_USERNAME` (optional; defaults to `deviceops-dynsec-admin`)

The entrypoint uses `mosquitto_ctrl dynsec init` to create the configuration atomically, sets ownership to the image's `mosquitto` user (UID/GID 1883), restricts the file to mode `0600`, unsets the bootstrap variables, and then starts the broker. It never prints the password and never enables shell tracing.

Later boots reuse the existing file even if the secret value changes or is absent. They never regenerate credentials or overwrite clients, groups, or roles. If the volume is empty and the password is absent, startup fails before Mosquitto can accept connections. Anonymous access is disabled in `mosquitto.conf`.

The same volume also stores `mosquitto.db`, including retained messages and durable MQTT session state. Mosquitto receives `SIGTERM` directly and writes persistence during graceful shutdown; one-minute periodic autosaves provide an additional safeguard.

## Future credential model (not implemented here)

Dynamic Security administration and the future FastAPI service identity must remain separate credentials.

For a device, the future MQTT username and client ID will both be its stable `device_id`. Device broker passwords should be derived without creating a second user-facing secret:

```text
signing_key = SHA256(device_secret)
broker_password = HMAC-SHA256(signing_key, "deviceops-broker-auth-v1")
```

FastAPI already stores the signing key and can later derive the same broker password. This milestone does not change registration, credential code, FastAPI, the simulator, or ESP32 firmware.

Future device roles should grant only the required per-device topics, using `%u` as a whole topic level:

- publish: `deviceops/v1/devices/%u/telemetry`
- publish: `deviceops/v1/devices/%u/status`
- publish: `deviceops/v1/devices/%u/capabilities`
- publish: `deviceops/v1/devices/%u/command-acks`
- receive/subscribe: `deviceops/v1/devices/%u/commands`

Do not replace those explicit permissions with unrestricted access to `deviceops/v1/devices/%u/#`. A future API service identity will subscribe across device telemetry/status/capabilities/ack topics and publish commands, but will not be a Dynamic Security administrator.

## Local build and authenticated smoke test

Use test-only credentials. A named Docker volume exercises the same persistence boundary as Fly without writing generated security state into the repository.

```powershell
Set-Location infra/mosquitto-prod
docker build -t deviceops-mosquitto-prod:test .
docker volume create deviceops-mosquitto-prod-test
docker run -d --name deviceops-mosquitto-prod-test `
  -p 127.0.0.1:18883:1883 `
  -v deviceops-mosquitto-prod-test:/mosquitto/data `
  -e DEVICEOPS_DYNSEC_ADMIN_USERNAME=test-admin `
  -e DEVICEOPS_DYNSEC_ADMIN_PASSWORD='<test-only-password>' `
  deviceops-mosquitto-prod:test
```

An anonymous connection must fail:

```powershell
docker run --rm eclipse-mosquitto:2.1.2-alpine `
  mosquitto_sub -h host.docker.internal -p 18883 -t '$SYS/broker/version' -C 1 -W 3
```

An authenticated Dynamic Security API query should list `test-admin`:

```powershell
docker run --rm -it eclipse-mosquitto:2.1.2-alpine `
  mosquitto_ctrl -h host.docker.internal -p 18883 -u test-admin dynsec listClients
```

The command prompts for the test admin password, keeping it out of shell history and process arguments. Local traffic is deliberately plaintext; production administration must use `mqtt.deviceops.net:443` with certificate verification.

Inspect status and logs without printing secrets:

```powershell
docker ps --filter name=deviceops-mosquitto-prod-test
docker logs deviceops-mosquitto-prod-test
docker exec deviceops-mosquitto-prod-test sh -c `
  'stat -c %a:%u:%g:%n /mosquitto/data/dynamic-security.json /mosquitto/data/mosquitto.db'
```

Remove the disposable container and test volume when finished:

```powershell
docker rm -f deviceops-mosquitto-prod-test
docker volume rm deviceops-mosquitto-prod-test
```

## Later Fly deployment

Do not run these commands until the broker cutover milestone is approved. From this directory:

```powershell
fly apps create deviceops-mqtt-prod
fly volumes create mosquitto_data --app deviceops-mqtt-prod --region iad --size 1
fly secrets set --stage --app deviceops-mqtt-prod `
  DEVICEOPS_DYNSEC_ADMIN_USERNAME=deviceops-dynsec-admin `
  DEVICEOPS_DYNSEC_ADMIN_PASSWORD='<generate-a-strong-unique-password>'
fly deploy --ha=false
```

`--ha=false` is intentional: it creates one Machine for the one volume. After deployment, verify `fly status --app deviceops-mqtt-prod` and `fly volumes list --app deviceops-mqtt-prod` before adding the future `mqtt.deviceops.net` certificate and DNS record. Do not change the existing HiveMQ production configuration until that later cutover is separately validated.

After the first boot and an authenticated admin check succeed, remove the bootstrap password from the Machine environment while retaining it in the operator's password manager. This restarts the Machine; the entrypoint must report that it reused the volume-backed configuration:

```powershell
fly secrets unset DEVICEOPS_DYNSEC_ADMIN_PASSWORD --app deviceops-mqtt-prod
fly logs --app deviceops-mqtt-prod
```

For an authenticated production smoke test, use a client that verifies the hostname and public CA chain, connect to `mqtt.deviceops.net` on port 443, and omit any insecure/TLS-skip-verification option. For example, `mosquitto_ctrl -h mqtt.deviceops.net -p 443 --tls-use-os-certs -u <admin-user> dynsec listClients` prompts for the password and queries the Dynamic Security control API without printing the secret.
