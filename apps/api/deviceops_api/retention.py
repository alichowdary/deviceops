"""Lifecycle-owned rolling retention for high-volume operational data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import DeviceEvent, Telemetry


logger = logging.getLogger(__name__)
RETENTION_DAYS = 3
RETENTION_INTERVAL_SECONDS = 60 * 60


@dataclass(frozen=True)
class RetentionResult:
    telemetry_deleted: int
    events_deleted: int


def cleanup_expired_data(session: Session, cutoff: datetime) -> RetentionResult:
    """Delete timestamped operational rows strictly older than ``cutoff``.

    The caller owns the transaction so both deletes commit or roll back together.
    """

    telemetry_result = session.execute(
        delete(Telemetry).where(Telemetry.received_at < cutoff)
    )
    event_result = session.execute(
        delete(DeviceEvent).where(DeviceEvent.occurred_at < cutoff)
    )
    return RetentionResult(
        telemetry_deleted=telemetry_result.rowcount or 0,
        events_deleted=event_result.rowcount or 0,
    )


def cleanup_expired_data_once() -> RetentionResult:
    """Run one atomic cleanup using the database server's current timestamp."""

    with SessionLocal.begin() as session:
        database_now = session.scalar(select(func.now()))
        if database_now is None:  # pragma: no cover - a healthy database returns now()
            raise RuntimeError("Database did not return its current timestamp")
        result = cleanup_expired_data(
            session, database_now - timedelta(days=RETENTION_DAYS)
        )

    if result.telemetry_deleted or result.events_deleted:
        logger.info(
            "Retention cleanup deleted %d telemetry rows and %d device event rows",
            result.telemetry_deleted,
            result.events_deleted,
        )
    return result


class RetentionCleaner:
    """Run retention immediately on startup and periodically thereafter."""

    def __init__(
        self,
        interval_seconds: float = RETENTION_INTERVAL_SECONDS,
        cleanup: Callable[[], RetentionResult] = cleanup_expired_data_once,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._cleanup = cleanup
        self._task: asyncio.Task[None] | None = None
        self._stop_requested: asyncio.Event | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_requested = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(), name="deviceops-retention-cleaner"
        )
        logger.info("Retention cleaner started")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            assert self._stop_requested is not None
            self._stop_requested.set()
            await task
        self._stop_requested = None
        logger.info("Retention cleaner stopped")

    async def _run(self) -> None:
        stop_requested = self._stop_requested
        assert stop_requested is not None
        while not stop_requested.is_set():
            try:
                await asyncio.to_thread(self._cleanup)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Retention cleanup failed; the next scheduled run will retry"
                )
            try:
                await asyncio.wait_for(
                    stop_requested.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                pass


retention_cleaner = RetentionCleaner()
