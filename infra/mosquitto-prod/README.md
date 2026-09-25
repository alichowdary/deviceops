# DeviceOps production MQTT broker

This directory defines the current DeviceOps-managed production broker. It is
separate from `infra/mosquitto/` and the root `docker-compose.yml`, which remain
the anonymous, plaintext local-development broker.

## Deployed architecture

- Fly.io app: `deviceops-mqtt-prod`
- Region: `iad`
- Broker: Eclipse Mosquitto 2.1.2
- Compute: one Machine
- Storage: one persistent 1 GB Fly volume
- Public endpoint: `mqtt.deviceops.net:443`
- Authentication: Mosquitto Dynamic Security

Production clients use raw MQTT over verified TLS:

```text
MQTT client
  -> verified TLS to mqtt.deviceops.net:443
  -> Fly Proxy TLS termination
  -> plaintext TCP on Fly's private network
  -> Mosquitto 2.1.2 on 0.0.0.0:1883
```

`fly.toml` exposes external TCP port 443 with Fly's `tls` handler. Ports 1883
and 8883 are not public and there is no HTTP handler. The actual deployment has
a dedicated public IPv4 intentionally assigned to the broker app.

The one-Machine/one-volume shape is a deliberate single-broker architecture.
The Machine does not scale to zero because MQTT clients hold long-lived
connections. Do not add a second Machine without redesigning persistence:
Fly volumes attach to individual Machines and are not replicated broker storage.
This deployment does not claim high availability or automated disaster recovery.

## Dynamic Security and persistence

The image loads the Dynamic Security plugin from
`/usr/lib/mosquitto_dynamic_security.so`. Mutable state is stored in
`/mosquitto/data/dynamic-security.json` on the persistent volume. The same
volume stores `mosquitto.db`, including retained messages and durable MQTT
session state.

On the first boot, the entrypoint used:

- `DEVICEOPS_DYNSEC_ADMIN_PASSWORD` (required for bootstrap)
- `DEVICEOPS_DYNSEC_ADMIN_USERNAME` (optional; defaults to `deviceops-dynsec-admin`)

It initialized the configuration atomically, assigned it to UID/GID 1883,
restricted it to mode `0600`, unset the bootstrap variables, and started the
broker without printing the password. Subsequent boots reuse the persisted
configuration and never regenerate clients, groups, or roles. The bootstrap
secrets were removed from the Machine environment after initialization.
Anonymous access is disabled.

Mosquitto receives `SIGTERM` directly and persists state during graceful
shutdown. One-minute periodic autosaves provide another write boundary, but the
single volume remains the only broker-state copy described by this deployment.

## Production identities and roles

Three credential classes remain separate:

1. Each device uses its stable `device_id` as MQTT username and client ID. Its
   password is deterministically derived from the one-time DeviceOps device
   secret, so users do not manage a second MQTT credential.
2. FastAPI uses a dedicated service identity for fleet-wide ingestion and
   command publishing. It is not a Dynamic Security administrator.
3. FastAPI provisioning uses a separate Dynamic Security administrator identity
   to create, update, and revoke device clients.

Device broker authentication is derived as follows:

```text
signing_key = SHA256(device_secret).digest()
broker_password = HMAC-SHA256(
    signing_key,
    "deviceops-broker-auth-v1"
).hexdigest()
```

FastAPI stores the signing key created during device registration and derives
the same broker password when it automatically provisions or revokes that
device's Dynamic Security client. Broker authentication is separate from the
DeviceOps HMAC authentication applied to MQTT message envelopes.

The production device role grants only the required per-device topics, using
`%u` as a whole topic level:

- publish: `deviceops/v1/devices/%u/telemetry`
- publish: `deviceops/v1/devices/%u/status`
- publish: `deviceops/v1/devices/%u/capabilities`
- publish: `deviceops/v1/devices/%u/command-acks`
- receive/subscribe: `deviceops/v1/devices/%u/commands`

Do not replace these permissions with unrestricted access to
`deviceops/v1/devices/%u/#`. The FastAPI service role subscribes across device
telemetry, status, capability, and acknowledgement topics and publishes commands.

## Local build and authenticated smoke test

Use test-only credentials. A named Docker volume exercises the production image's
persistence boundary without writing generated security state into the repository.

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

An authenticated Dynamic Security query should list `test-admin`:

```powershell
docker run --rm -it eclipse-mosquitto:2.1.2-alpine `
  mosquitto_ctrl -h host.docker.internal -p 18883 -u test-admin dynsec listClients
```

The command prompts for the test password, keeping it out of shell history and
process arguments. Local traffic is deliberately plaintext. Production clients
must connect to `mqtt.deviceops.net:443` with hostname and CA-chain verification.

Inspect status and persisted files without printing secrets:

```powershell
docker ps --filter name=deviceops-mosquitto-prod-test
docker logs deviceops-mosquitto-prod-test
docker exec deviceops-mosquitto-prod-test sh -c `
  'stat -c %a:%u:%g:%n /mosquitto/data/dynamic-security.json /mosquitto/data/mosquitto.db'
```

Remove the disposable local resources when finished:

```powershell
docker rm -f deviceops-mosquitto-prod-test
docker volume rm deviceops-mosquitto-prod-test
```

## Production verification and maintenance

Inspect the existing deployment without exposing secrets:

```powershell
fly status --app deviceops-mqtt-prod
fly volumes list --app deviceops-mqtt-prod
fly logs --app deviceops-mqtt-prod
```

For an authenticated broker check, use a client that verifies the hostname and
public CA chain. For example, this command prompts for the Dynamic Security admin
password and does not place it in the command line:

```powershell
mosquitto_ctrl -h mqtt.deviceops.net -p 443 --tls-use-os-certs `
  -u <admin-user> dynsec listClients
```

Do not reintroduce bootstrap secrets or print production credentials during
routine maintenance.
