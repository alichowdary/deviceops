# DeviceOps web console

The frontend is a read-only Next.js operations console. It loads device state
and recent telemetry through FastAPI's REST API, then receives new committed
telemetry and status events through one FastAPI WebSocket. The browser does not
connect to MQTT.

## Requirements

- Node.js 20.9 or newer
- npm
- The Milestone 2 infrastructure and FastAPI service running locally

## Install and configure

From the repository root:

```powershell
cd apps\web
npm install
```

The frontend defaults to `http://127.0.0.1:8000`. To use a different backend,
copy the committed example and edit the local value:

```powershell
Copy-Item .env.example .env.local
```

```text
NEXT_PUBLIC_DEVICEOPS_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_DEVICEOPS_WS_URL=ws://127.0.0.1:8000/ws
```

`.env.local` is ignored by Git. The API's local CORS allowlist accepts
`http://localhost:3000` and `http://127.0.0.1:3000` by default.

## Run the frontend

```powershell
npm run dev
```

Open <http://localhost:3000>. The fleet page loads persisted devices and API
health. Select a device row to open `/devices/{deviceId}`, where the latest
measurements, 100-sample telemetry charts, and recent samples are shown. New
events update fleet status, last-seen timestamps, current measurements, charts,
and the recent-samples table without polling or a page reload.

If Node.js is not installed on Windows, run from the repository root with the
official Node image instead. Dependencies remain in a temporary container
volume and are removed when the container stops:

```powershell
docker run --rm -it -p 127.0.0.1:3000:3000 -v "${PWD}:/workspace" -v /workspace/apps/web/node_modules -w /workspace/apps/web node:24-alpine sh -lc "npm ci && npm run dev -- --hostname 0.0.0.0"
```

The small `Live`, `Connecting`, or `Reconnecting` label shows WebSocket state.
After a disconnect, the client retries with exponential backoff capped at ten
seconds. When it reconnects, it reloads the REST snapshot to fill the gap before
continuing with WebSocket deltas. Refresh remains available for an explicit
snapshot reload. The browser never accesses MQTT directly.

## Run the full local demo

Use separate PowerShell terminals.

Start Mosquitto and PostgreSQL from the repository root:

```powershell
docker compose up -d
docker compose ps
```

Start FastAPI:

```powershell
cd apps\api
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m uvicorn deviceops_api.main:app --host 127.0.0.1 --port 8000
```

Start one or more simulators:

```powershell
cd simulator
.\.venv\Scripts\Activate.ps1
python -m device_simulator --device-id sim-001 --interval 5
```

Start the frontend:

```powershell
cd apps\web
npm run dev
```

Stop the development processes with Ctrl+C. From the repository root,
`docker compose down` stops Mosquitto and PostgreSQL while preserving database
data.

## Quality checks

```powershell
npm run lint
npm run typecheck
npm run build
```
