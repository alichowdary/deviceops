# DeviceOps API

The backend runs FastAPI and owns the MQTT subscriber. It validates version 1
device messages, stores device state, latest capability manifests, telemetry,
command history, and meaningful
fleet activity in PostgreSQL, publishes validated operator commands, and
broadcasts newly committed updates at `/ws`.

## Local setup

From the repository root, start Mosquitto and PostgreSQL:

```powershell
docker compose config
docker compose up -d
docker compose ps
```

The Compose defaults are deliberately local development credentials:
database `deviceops`, user `deviceops`, and password `deviceops-local`. PostgreSQL
is bound to `127.0.0.1:5432`, and its data persists in the `postgres_data` volume.
The values can be overridden with `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD`; set `DEVICEOPS_DATABASE_URL` to the matching SQLAlchemy URL
when overriding them.

Create an isolated backend environment and install its pinned dependencies:

```powershell
cd apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Apply the database migrations, then start FastAPI:

```powershell
python -m alembic upgrade head
python -m uvicorn deviceops_api.main:app --host 127.0.0.1 --port 8000
```

FastAPI starts the MQTT subscriber through its application lifespan and stops it
on shutdown. If MQTT is unavailable, the API remains available with a degraded
health response while Paho retries. Database migrations remain an explicit step
so schema changes are visible and reviewable.

Run one Uvicorn worker in this milestone. Because the MQTT subscriber currently
lives inside the API process, additional workers would also start subscribers.
The ingestion responsibility can be separated later if independent scaling is
needed. The WebSocket hub is also in process, so this single-worker constraint
keeps ingestion and connected browsers on the same event stream. The one-second
offline-alert evaluator also runs in this process; multi-worker coordination is
intentionally outside this local milestone.

## Run a device

In another PowerShell terminal, use the simulator environment created in
Milestone 1B. Register a device first, then supply its one-time plaintext secret
without placing it in shell history:

```powershell
cd simulator
.\.venv\Scripts\Activate.ps1
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id> --interval 5
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
```

## Query the API

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
$headers = @{ Authorization = "Bearer <access-token>" }
Invoke-RestMethod -Headers $headers http://127.0.0.1:8000/api/devices
Invoke-RestMethod -Headers $headers "http://127.0.0.1:8000/api/devices/<owned-device-id>"
Invoke-RestMethod -Headers $headers "http://127.0.0.1:8000/api/devices/<owned-device-id>/telemetry?limit=100"
Invoke-RestMethod -Headers $headers "http://127.0.0.1:8000/api/devices/<owned-device-id>/capabilities"
Invoke-RestMethod -Headers $headers "http://127.0.0.1:8000/api/devices/<owned-device-id>/commands?limit=20"
Invoke-RestMethod -Headers $headers "http://127.0.0.1:8000/api/events?limit=100"
Invoke-RestMethod -Headers $headers "http://127.0.0.1:8000/api/alert-rules"
Invoke-RestMethod -Headers $headers "http://127.0.0.1:8000/api/alerts?limit=100"
```

Telemetry is returned oldest-to-newest within the requested recent window. The
default limit is 100 and the maximum is 500. Unknown devices return HTTP 404.
Interactive OpenAPI documentation is at <http://127.0.0.1:8000/docs>.

## Device capabilities

The MQTT subscriber validates signed manifests from the retained QoS 1
`deviceops/v1/devices/{device_id}/capabilities` topic. A manifest must use the
current device session, match the topic device ID, stay within the protocol's
bounded schema, and advertise only the three existing command types. The latest
validated JSON is stored on `devices.capabilities`; server receipt time is stored
in `devices.capabilities_updated_at`. Republishing replaces the previous value
and does not create fleet Event history.

`GET /api/devices/{device_id}/capabilities` uses the existing owner-scoped 404
privacy boundary. A registered device that has never advertised returns
`{"capabilities":null,"updated_at":null}`. Accepted updates are broadcast on the
existing authenticated WebSocket as `capabilities_updated`, without `owner_id`.
The frontend currently recognizes and safely ignores this delta; dynamic device
detail rendering belongs to the next phase.

## Persistent fleet events

`GET /api/events` returns the authenticated user's newest events first. The
default limit is 100 and the maximum is 200. Optional `device_id`, `event_type`,
and `severity` query parameters narrow the feed. Filtering by an unknown or
unowned device returns the same HTTP 404 privacy boundary used by device routes.
Responses never include `owner_id`.

## Alert rule management

Authenticated users manage persistent rule definitions at:

- `GET /api/alert-rules`
- `POST /api/alert-rules`
- `GET /api/alert-rules/{rule_id}`
- `PATCH /api/alert-rules/{rule_id}`
- `DELETE /api/alert-rules/{rule_id}`

The list endpoint accepts optional `device_id`, `enabled`, `rule_type`, and
`severity` filters. Every query is scoped to the authenticated owner. Unknown
and unowned devices or rules return the same HTTP 404 response, and `owner_id`
is never returned. A device and its rules are deleted together through the
database foreign-key cascade.

`metric_threshold` rules require one of `temperature_c`, `humidity_pct`,
`pressure_hpa`, `battery_pct`, or `rssi_dbm`; an operator (`gt`, `gte`, `lt`, or
`lte`); and a finite, metric-bounded threshold. They forbid
`offline_after_seconds`. `device_offline` rules require an offline duration from
5 through 604800 seconds and forbid metric, operator, and threshold fields.
Both types accept an optional trimmed 100-character name, severity `info`,
`warning`, or `critical`, and a strict boolean `enabled` value.

Metric threshold bounds are `-100..200` °C for temperature, `0..100` percent
for humidity and battery, `0..2000` hPa for pressure, and `-200..0` dBm for
RSSI. These broad bounds reject nonsensical configuration while leaving normal
device operating ranges to the user.

PATCH supports name, severity, enabled state, and the fields that belong to the
existing rule type. Device, rule type, and metric are immutable after creation.
Disabling a rule immediately resolves its active alert. Re-enabling makes it
eligible to open a new alert on the next evaluation. Deleting a rule resolves its
active alert before deletion and retains alert history with a null rule ID plus
the saved rule name, type, severity, and condition.

## Alert evaluation and history

`GET /api/alerts` returns the authenticated owner's newest alert instances. It
accepts `status`, `device_id`, `severity`, `rule_id`, and a `limit` from 1 through
200. `GET /api/alerts/{alert_id}` returns one owned instance. Cross-owner device,
rule, and alert lookups use privacy-preserving HTTP 404 responses; responses do
not include `owner_id`.

Accepted authenticated telemetry evaluates enabled metric rules after the
telemetry transaction commits. A true condition opens one alert, repeated true
samples retain that alert, and a later false value resolves it. A missing or null
metric leaves the current lifecycle unchanged. Evaluation runs in its own short
transaction, so an alert failure cannot roll back accepted telemetry.

Offline rules use persisted `offline_since` state and open only after a previously
connected device remains explicitly offline for the configured duration. Unknown
and never-connected devices do not alert. A one-second in-process task evaluates
threshold crossings without needing another MQTT message; reconnect status also
resolves an active offline alert immediately. The database partial unique index
on active `rule_id` prevents two active instances for one rule. Alert state and
lifecycle events commit in the same transaction. External email, SMS, push, and
webhook notifications are not implemented.

The persistent event types and severities are:

| Event type | Severity | Created when |
| --- | --- | --- |
| `device_registered` | `info` | An owned registration commits |
| `device_online` | `success` | Authenticated status transitions to online |
| `device_offline` | `warning` | Authenticated status transitions to offline |
| `command_issued` | `info` | A pending command commits |
| `command_succeeded` | `success` | The first valid ACK succeeds the command |
| `command_failed` | `error` | The first valid ACK fails the command |
| `alert_opened` | alert severity mapped to `info`/`warning`/`error` | A rule first becomes violated |
| `alert_resolved` | `success` | An alert clears or its rule is disabled/deleted |

Repeated effective status messages and duplicate command acknowledgements do not
create duplicate events. Telemetry samples are deliberately excluded. Event
details contain only safe operational command, status, and alert context;
credentials, authenticated MQTT envelopes, and ownership routing metadata are
not stored.

## User authentication

The standalone authentication API supports JSON registration and login requests
at `POST /api/auth/register` and `POST /api/auth/login`. Send the returned access
token as `Authorization: Bearer <token>` to `GET /api/auth/me` and the device,
telemetry, and command REST routes. Those routes return only devices owned by the
authenticated user. Unowned devices and devices owned by other users are hidden.
MQTT message authentication is described below. The WebSocket endpoint uses the
same access token with the initial-frame handshake described under Live events.

Register a new device with an empty JSON object:

```powershell
$registration = Invoke-RestMethod -Method Post -ContentType "application/json" `
  -Headers $headers -Body "{}" http://127.0.0.1:8000/api/devices
```

DeviceOps generates the device ID and a high-entropy device secret. Save the
returned secret securely: its plaintext value is shown only in this creation
response. The database stores its SHA-256 digest. A registered device remains
`unknown` with null first/last-seen timestamps until authenticated device
firmware connects.

## Authenticated MQTT messages

MQTT payloads use a signed JSON envelope containing `auth_version`, a 32-character
lowercase hexadecimal `session_id`, the exact inner payload as the `body` string,
and a lowercase HMAC-SHA256 `signature`. Device-originated messages use direction
`d2s`; commands use `s2d`. The signature covers the direction, exact full topic,
session ID, and SHA-256 digest of the exact UTF-8 body.

The MQTT signing key is the raw SHA-256 digest of the generated device secret.
The database stores that digest as hexadecimal in `device_secret_hash`, so the
stored digest is credential-equivalent for MQTT authentication: anyone who can
read it can derive the HMAC key and impersonate the device. Hash storage prevents
recovering the original one-time secret, but it does not prevent impersonation
after a database compromise. Secret encryption or asymmetric device identities
are outside this checkpoint.

Authenticated `online` establishes the current device session. Telemetry,
capabilities, acknowledgements, and `offline` must use that session; this prevents a stale Last
Will from an older connection from marking a newer session offline. Registered,
owned devices with valid credentials are accepted. Unknown, unowned, unsigned,
malformed, or incorrectly signed messages are rejected without changing data.

Protocol version 1 has no general anti-replay mechanism. Captured authenticated
telemetry, acknowledgement, or status messages can be replayed, and replaying a
previously valid signed `online` message can re-establish its older session.
Session matching protects the normal delayed-Last-Will case after a newer session
is established. Stronger replay protection is deferred.

## Issue commands

The browser submits commands through FastAPI; it never receives MQTT access.
For example:

```powershell
$body = @{ type = "set_led"; arguments = @{ on = $true } } | ConvertTo-Json
Invoke-RestMethod -Method Post -ContentType "application/json" -Body $body `
  -Headers $headers `
  "http://127.0.0.1:8000/api/devices/<owned-device-id>/commands"
```

`POST /api/devices/{device_id}/commands` validates the request, creates a UUID,
commits a `pending` row, and publishes the command with QoS 1 and no retention.
It returns HTTP 201 while the command is still pending. Only a matching device
acknowledgement can change it to `succeeded` or `failed`.

`GET /api/devices/{device_id}/commands?limit=20` returns newest-first command
history. The limit range is 1–100. Automatic timeouts are intentionally absent:
an unacknowledged command remains pending, making the missing device evidence
visible without introducing a scheduler.

## Live events

The web console opens `ws://127.0.0.1:8000/ws` after its initial REST snapshot.
The connection must pass the existing Origin allowlist and authenticate within
five seconds of opening. Send exactly this initial text JSON frame using the
existing JWT from login (never put it in the URL query string):

```json
{"type":"authenticate","token":"<access-token>"}
```

After validating the JWT and checking that the user still exists, the server
replies with `{"type":"authenticated"}` and registers the connection for that
user. Invalid/missing authentication or a timeout closes the socket with code
`1008`; unauthenticated sockets receive no device events. Only events for devices
owned by the authenticated user are delivered. Ownership is internal routing
metadata and is not added to event JSON. Authentication is checked at connection
time; reconnects must authenticate again.

The frontend completes this handshake before treating the socket as live and
reloads its REST snapshot after an authenticated reconnect.

The endpoint emits MQTT deltas accepted by the existing validation and committed
to PostgreSQL. It also emits `event_created` after the corresponding persistent
fleet event commits. The socket does not replay history; reconnecting clients
fetch fresh REST snapshots before applying new deltas.

Alert lifecycle changes use the same owner-scoped socket:

```json
{
  "type": "alert_update",
  "received_at": "2026-09-19T12:00:00Z",
  "data": {
    "id": 17,
    "device_id": "dev-example",
    "rule_id": 4,
    "rule_name": "Warm room",
    "rule_type": "metric_threshold",
    "severity": "warning",
    "status": "active",
    "condition": "Temperature > 30 °C",
    "metric": "temperature_c",
    "operator": "gt",
    "threshold": 30,
    "offline_after_seconds": null,
    "observed_value": 31.4,
    "resolved_value": null,
    "opened_at": "2026-09-19T12:00:00Z",
    "resolved_at": null,
    "resolution_reason": null,
    "created_at": "2026-09-19T12:00:00Z",
    "updated_at": "2026-09-19T12:00:00Z"
  }
}
```

The matching `alert_opened` or `alert_resolved` record also arrives as the
existing `event_created` message. Neither message contains `owner_id`.

Persistent event notifications use this shape:

```json
{
  "type": "event_created",
  "received_at": "2026-09-18T17:00:00Z",
  "data": {
    "id": 42,
    "device_id": "dev-example",
    "event_type": "device_online",
    "severity": "success",
    "occurred_at": "2026-09-18T17:00:00Z",
    "details": {
      "previous_status": "offline",
      "status": "online"
    }
  }
}
```

`owner_id` remains internal to WebSocket routing and never enters this JSON.

Telemetry events use this envelope:

```json
{
  "type": "telemetry",
  "device_id": "sim-001",
  "received_at": "2026-09-14T21:16:49.337777Z",
  "data": {
    "id": 2867,
    "sequence": 259,
    "sent_at": "2026-09-14T21:16:49.334000Z",
    "temperature_c": 24.7,
    "battery_pct": 84.75,
    "humidity_pct": null,
    "pressure_hpa": null,
    "rssi_dbm": -56,
    "uptime_s": 1290,
    "additional_metrics": null
  }
}
```

Battery, humidity, and pressure are nullable first-class measurements. The
simulator supplies battery, while a sensor device may omit battery and supply
humidity and pressure. Omitted measurements are returned as `null`; unknown
compatible measurements continue to use `additional_metrics`.

Status events use the same outer fields with a smaller payload:

```json
{
  "type": "device_status",
  "device_id": "sim-001",
  "received_at": "2026-09-14T21:20:52.874463Z",
  "data": { "status": "offline" }
}
```

Committed acknowledgements produce a command update:

```json
{
  "type": "command_update",
  "device_id": "sim-001",
  "received_at": "2026-09-14T22:15:11.709812Z",
  "data": {
    "command_id": "246efa2b-798e-4c53-a53e-fe1853090044",
    "type": "set_led",
    "status": "succeeded",
    "arguments": { "on": true },
    "issued_at": "2026-09-14T22:15:11.691858Z",
    "acknowledged_at": "2026-09-14T22:15:11.709812Z",
    "ack_sent_at": "2026-09-14T22:15:11.706000Z",
    "result": { "on": true }
  }
}
```

Paho invokes MQTT callbacks on its network thread. After the synchronous
database transaction commits, the callback uses asyncio's thread-safe scheduler
to enqueue the event on FastAPI's event loop. One broadcaster task sends queued
events to that device owner's connected browsers and removes clients whose sends
fail or time out. A slow or disconnected browser therefore does not stop MQTT
ingestion or delivery to other clients.

The device owner is captured from the accepted MQTT message's existing database
lookup. Delivery compares that owner with each connection's user ID, without
additional database lookups per socket. There is no replay log or distributed
pub-sub layer.

WebSocket handshakes require an `Origin` in the same local allowlist used for
CORS in addition to the JWT authentication above.

## Configuration

| Environment variable | Default |
| --- | --- |
| `DEVICEOPS_DATABASE_URL` | `postgresql+psycopg://deviceops:deviceops-local@127.0.0.1:5432/deviceops` |
| `DEVICEOPS_MQTT_HOST` | `localhost` |
| `DEVICEOPS_MQTT_PORT` | `1883` |
| `DEVICEOPS_MQTT_CLIENT_ID` | `deviceops-api` |
| `DEVICEOPS_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` |
| `DEVICEOPS_AUTH_SECRET` | `deviceops-local-development-secret-must-be-overridden` |
| `DEVICEOPS_AUTH_TOKEN_LIFETIME_SECONDS` | `86400` |

The HTTP CORS and WebSocket origin allowlists are limited to the two expected
local Next.js origins. Supply a comma-separated list through
`DEVICEOPS_CORS_ORIGINS` if the local frontend uses a different origin.
The default authentication secret is for local development only and must be
replaced with a strong secret supplied through `DEVICEOPS_AUTH_SECRET` before
deployment. Access tokens use HS256 and expire after 24 hours by default.

The backend uses one short synchronous SQLAlchemy session per HTTP request or
MQTT message. A malformed message is logged and rejected without stopping the
subscriber. The subscriber can be moved into a separate ingestion service later
if load or independent scaling requires it; that split is intentionally absent
from this milestone.

Stop FastAPI with Ctrl+C. Stop local infrastructure without deleting stored data:

```powershell
docker compose down
```

To deliberately reset the development database, remove its volume:

```powershell
docker compose down --volumes
```
