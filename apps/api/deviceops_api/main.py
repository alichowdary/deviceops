"""FastAPI application with lifecycle-owned MQTT ingestion."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import database_is_reachable, engine
from .mqtt import mqtt_ingestor
from .realtime import realtime_hub
from .routes.commands import router as commands_router
from .routes.devices import router as devices_router
from .schemas import HealthRead


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await realtime_hub.start()
    mqtt_ingestor.start()
    try:
        yield
    finally:
        mqtt_ingestor.stop()
        await realtime_hub.stop()
        engine.dispose()


app = FastAPI(title="DeviceOps API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
)
app.include_router(devices_router)
app.include_router(commands_router)


@app.websocket("/ws")
async def websocket_events(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in settings.cors_origins:
        logging.getLogger(__name__).warning(
            "Rejected WebSocket connection from origin %r", origin
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await realtime_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        realtime_hub.disconnect(websocket)


@app.get("/health", response_model=HealthRead, tags=["health"])
def health() -> HealthRead:
    database_up = database_is_reachable()
    mqtt_up = mqtt_ingestor.connected
    return HealthRead(
        status="ok" if database_up and mqtt_up else "degraded",
        database="up" if database_up else "down",
        mqtt="up" if mqtt_up else "down",
        mqtt_error=mqtt_ingestor.last_error,
    )
