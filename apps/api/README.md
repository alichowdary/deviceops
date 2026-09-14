# DeviceOps API

The Milestone 2 backend runs FastAPI and owns the MQTT subscriber. It validates
version 1 device messages, stores device state and telemetry in PostgreSQL, and
provides a small read-only REST API.

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
needed.

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

## Configuration

| Environment variable | Default |
| --- | --- |
| `DEVICEOPS_DATABASE_URL` | `postgresql+psycopg://deviceops:deviceops-local@127.0.0.1:5432/deviceops` |
| `DEVICEOPS_MQTT_HOST` | `localhost` |
| `DEVICEOPS_MQTT_PORT` | `1883` |
| `DEVICEOPS_MQTT_CLIENT_ID` | `deviceops-api` |
| `DEVICEOPS_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` |

The CORS allowlist is limited to the two expected local Next.js origins. Supply
a comma-separated list through `DEVICEOPS_CORS_ORIGINS` if the local frontend
uses a different origin.

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
