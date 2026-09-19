"""FastAPI application with lifecycle-owned MQTT ingestion."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .database import database_is_reachable, engine
from .mqtt import mqtt_ingestor
from .realtime import realtime_hub
from .routes.alert_rules import router as alert_rules_router
from .routes.auth import router as auth_router
from .routes.commands import router as commands_router
from .routes.devices import router as devices_router
from .routes.events import router as events_router
from .schemas import HealthRead
from .security import AccessTokenError
from .websocket_auth import authenticate_websocket


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
WEBSOCKET_AUTH_TIMEOUT_SECONDS = 5


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
    allow_methods=["DELETE", "GET", "PATCH", "POST"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)
app.include_router(auth_router)
app.include_router(devices_router)
app.include_router(commands_router)
app.include_router(events_router)
app.include_router(alert_rules_router)


@app.websocket("/ws")
async def websocket_events(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in settings.cors_origins:
        logger.warning(
            "Rejected WebSocket connection from origin %r", origin
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        await websocket.accept()
        try:
            user_id = await asyncio.wait_for(
                authenticate_websocket(websocket),
                timeout=WEBSOCKET_AUTH_TIMEOUT_SECONDS,
            )
        except (AccessTokenError, TimeoutError, SQLAlchemyError) as exc:
            # Never log frame contents, JWTs, or exception details from decoding.
            reason = (
                "timeout"
                if isinstance(exc, TimeoutError)
                else "invalid authentication"
            )
            logger.warning("Rejected WebSocket authentication: %s", reason)
            with suppress(WebSocketDisconnect, RuntimeError, OSError):
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.send_json({"type": "authenticated"})
        await realtime_hub.connect(websocket, user_id)
        while True:
            if (await websocket.receive())["type"] == "websocket.disconnect":
                break
    except (WebSocketDisconnect, OSError, RuntimeError):
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
