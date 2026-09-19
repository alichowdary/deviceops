# DeviceOps web console

The frontend is a Next.js operations console. It loads device state, telemetry,
command history, device capabilities, persistent fleet events, rules, and alert
history through FastAPI's REST API, then receives new committed telemetry,
status, command, capability, event, and alert updates through one FastAPI
WebSocket. The browser does not
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

Open <http://localhost:3000>. Register or sign in with a DeviceOps account. The
access token is kept in memory and in browser `sessionStorage` for the current
tab; logout, an authenticated REST `401`, or a rejected WebSocket authentication
clears it. The fleet page then loads that user's devices and API health. Select a
device row to open `/devices/{deviceId}`. Device Detail loads the device's
capability manifest alongside its 100-sample telemetry and command snapshots.
Manifest order, labels, units, and value types drive metric cards and recent
sample columns; numeric capabilities with actual numeric samples also receive
charts. Additional metrics use the same path as first-class telemetry fields.
Only advertised `set_led`, `set_reporting_interval`, and `request_diagnostics`
controls appear. Reporting-interval inputs use the advertised numeric type and
bounds. Submitted commands remain pending until the acknowledgement arrives
through the WebSocket.

New telemetry and `capabilities_updated` messages update the same page live
without replacing telemetry or command history. A device without a manifest
still shows identity, status, timestamps, command history, and an explicitly
labeled legacy raw recent-samples table. It does not receive inferred metric
cards, charts, or remote controls.

The Events navigation item opens `/events`, a newest-first operational feed for
registration, connectivity transitions, command activity, and alert lifecycle
changes. Device, event
type, and severity filters apply to both the REST snapshot and live updates.
Persistent IDs deduplicate snapshot and WebSocket delivery. Routine telemetry
samples are not part of this page.

The Alerts navigation item opens `/alerts`, where authenticated users monitor
active alerts, inspect recently resolved history, and manage metric threshold and
device-offline rules for their own devices. Conditions and observed values are
human-readable. Persistent IDs deduplicate REST snapshots and live `alert_update`
messages. The existing create, edit, enable/disable, and delete controls remain
on the same dense operations page. External notifications are not implemented.

Authenticated users can select **Add device** from Fleet to generate a device ID
and one-time device secret. Copy both values before closing the credential
dialog; the plaintext secret cannot be retrieved again. A registered device that
has not connected yet appears as `Unknown` with `Never` for its seen timestamps.

If Node.js is not installed on Windows, run from the repository root with the
official Node image instead. Dependencies remain in a temporary container
volume and are removed when the container stops:

```powershell
docker run --rm -it -p 127.0.0.1:3000:3000 -v "${PWD}:/workspace" -v /workspace/apps/web/node_modules -w /workspace/apps/web node:24-alpine sh -lc "npm ci && npm run dev -- --hostname 0.0.0.0"
```

The small `Live`, `Connecting`, or `Reconnecting` label shows WebSocket state.
Each connection sends the current access token in the initial WebSocket message
and becomes live only after FastAPI replies with the authenticated control
message. After an ordinary disconnect, the client retries with exponential
backoff capped at ten seconds. Once the new connection authenticates, it reloads
the REST snapshot to fill the gap before continuing with WebSocket deltas.
Refresh remains available for an explicit snapshot reload. The browser never
accesses MQTT directly.

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

Register a device through the web console, then start one or more simulators with
their generated IDs and one-time secrets:

```powershell
cd simulator
.\.venv\Scripts\Activate.ps1
$env:DEVICEOPS_DEVICE_SECRET = Read-Host "Registered device secret"
python -m device_simulator --device-id <registered-device-id> --interval 5
Remove-Item Env:DEVICEOPS_DEVICE_SECRET
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
