"""In-process WebSocket connection management and event broadcasting."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from typing import Any

from fastapi import WebSocket


logger = logging.getLogger(__name__)
LiveEvent = dict[str, Any]


class RealtimeHub:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, int] = {}
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[tuple[int, LiveEvent]] | None = None
        self._broadcast_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._broadcast_task is not None:
            return
        self._event_loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._broadcast_task = asyncio.create_task(
            self._broadcast_loop(), name="deviceops-websocket-broadcast"
        )
        logger.info("WebSocket event hub started")

    async def stop(self) -> None:
        self._event_loop = None

        task = self._broadcast_task
        self._broadcast_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        connections = tuple(self._connections)
        self._connections.clear()
        if connections:
            await asyncio.gather(
                *(connection.close(code=1001) for connection in connections),
                return_exceptions=True,
            )

        self._queue = None
        logger.info("WebSocket event hub stopped")

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        """Register an already accepted and authenticated connection."""
        self._connections[websocket] = user_id
        logger.info("WebSocket client connected; clients=%s", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)
        logger.info("WebSocket client disconnected; clients=%s", len(self._connections))

    def publish_from_thread(self, owner_id: int | None, event: LiveEvent) -> None:
        """Schedule a committed owner event onto the asyncio broadcast queue."""
        if type(owner_id) is not int or owner_id < 1:
            logger.warning("Dropped live event without a valid device owner")
            return
        event_loop = self._event_loop
        if event_loop is None or not event_loop.is_running():
            return
        try:
            event_loop.call_soon_threadsafe(self._enqueue, owner_id, event)
        except RuntimeError:
            logger.warning("Dropped live event while WebSocket hub was stopping")

    def _enqueue(self, owner_id: int, event: LiveEvent) -> None:
        queue = self._queue
        if queue is not None:
            queue.put_nowait((owner_id, event))

    async def _broadcast_loop(self) -> None:
        queue = self._queue
        if queue is None:
            return

        while True:
            owner_id, event = await queue.get()
            await self._broadcast(owner_id, event)

    async def _broadcast(self, owner_id: int, event: LiveEvent) -> None:
        connections = tuple(
            websocket
            for websocket, user_id in self._connections.items()
            if user_id == owner_id
        )
        if not connections:
            return

        results = await asyncio.gather(
            *(
                asyncio.wait_for(connection.send_json(event), timeout=2)
                for connection in connections
            ),
            return_exceptions=True,
        )
        for connection, result in zip(connections, results, strict=True):
            if isinstance(result, BaseException):
                self._connections.pop(connection, None)
                logger.warning(
                    "Removed failed WebSocket client during broadcast: %s", result
                )


realtime_hub = RealtimeHub()
