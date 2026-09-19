"""FastAPI-lifecycle-owned periodic evaluation of offline alert rules."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging

from .alerts import evaluate_offline_alerts_once


logger = logging.getLogger(__name__)
OFFLINE_EVALUATION_INTERVAL_SECONDS = 1.0


class OfflineAlertEvaluator:
    def __init__(self, interval_seconds: float = OFFLINE_EVALUATION_INTERVAL_SECONDS):
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._run(), name="deviceops-offline-alert-evaluator"
        )
        logger.info("Offline alert evaluator started")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        logger.info("Offline alert evaluator stopped")

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.to_thread(evaluate_offline_alerts_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected offline evaluator failure")
            await asyncio.sleep(self._interval_seconds)


offline_alert_evaluator = OfflineAlertEvaluator()
