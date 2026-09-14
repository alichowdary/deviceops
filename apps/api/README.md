# DeviceOps API

The backend runs FastAPI and owns the MQTT subscriber. It validates version 1
device messages, stores device state and telemetry in PostgreSQL, provides a
small read-only REST API, and broadcasts newly committed device events at `/ws`.

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
keeps ingestion and connected browsers on the same event stream.

## Run a device

In another PowerShell terminal, use the simulator environment created in
Milestone 1B:

```powershell
cd simulator
.\.venv\Scripts\Activate.ps1
python -m device_simulator --device-id sim-001 --interval 5
```

## Query the API

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/devices
Invoke-RestMethod http://127.0.0.1:8000/api/devices/sim-001
Invoke-RestMethod "http://127.0.0.1:8000/api/devices/sim-001/telemetry?limit=100"
```

Telemetry is returned oldest-to-newest within the requested recent window. The
default limit is 100 and the maximum is 500. Unknown devices return HTTP 404.
Interactive OpenAPI documentation is at <http://127.0.0.1:8000/docs>.

## Live events

The web console opens `ws://127.0.0.1:8000/ws` after its initial REST snapshot.
The endpoint emits only events accepted by the existing MQTT validation and
successfully committed to PostgreSQL. It does not replay history; reconnecting
clients should fetch a fresh REST snapshot before applying new events.

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
    "rssi_dbm": -56,
    "uptime_s": 1290,
    "additional_metrics": null
  }
}
```

Status events use the same outer fields with a smaller payload:

```json
{
  "type": "device_status",
  "device_id": "sim-001",
  "received_at": "2026-09-14T21:20:52.874463Z",
  "data": { "status": "offline" }
}
```

Paho invokes MQTT callbacks on its network thread. After the synchronous
database transaction commits, the callback uses asyncio's thread-safe scheduler
to enqueue the event on FastAPI's event loop. One broadcaster task sends queued
events to every connected browser and removes clients whose sends fail or time
out. A slow or disconnected browser therefore does not stop MQTT ingestion or
delivery to other clients.

At the current scale, every connected browser receives every event and filters
unrelated device IDs locally. There are no rooms, replay log, or distributed
pub-sub layer. Selective subscriptions and distributed delivery can replace this
in-process broadcast if load or multi-process deployment later requires them.

WebSocket handshakes require an `Origin` in the same local allowlist used for
CORS. This is a local development boundary, not user authentication.

## Configuration

| Environment variable | Default |
| --- | --- |
| `DEVICEOPS_DATABASE_URL` | `postgresql+psycopg://deviceops:deviceops-local@127.0.0.1:5432/deviceops` |
| `DEVICEOPS_MQTT_HOST` | `localhost` |
| `DEVICEOPS_MQTT_PORT` | `1883` |
| `DEVICEOPS_MQTT_CLIENT_ID` | `deviceops-api` |
| `DEVICEOPS_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` |

The HTTP CORS and WebSocket origin allowlists are limited to the two expected
local Next.js origins. Supply a comma-separated list through
`DEVICEOPS_CORS_ORIGINS` if the local frontend uses a different origin.

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
