"""Focused rolling-retention persistence and worker tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deviceops_api.database import engine
from deviceops_api.models import (
    Alert,
    AlertRule,
    Device,
    DeviceCommand,
    DeviceEvent,
    Telemetry,
    User,
)
from deviceops_api.retention import (
    RetentionCleaner,
    RetentionResult,
    cleanup_expired_data,
)


class RetentionPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(
            bind=self.connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        suffix = uuid4().hex[:10]
        self.owner = User(
            email=f"retention-owner-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.other_user = User(
            email=f"retention-other-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.session.add_all([self.owner, self.other_user])
        self.session.flush()
        self.device = Device(
            device_id=f"dev-retention-owner-{suffix}",
            owner_id=self.owner.id,
            status="online",
        )
        self.other_device = Device(
            device_id=f"dev-retention-other-{suffix}",
            owner_id=self.other_user.id,
            status="online",
        )
        self.session.add_all([self.device, self.other_device])
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def _telemetry(
        self, device: Device, sequence: int, received_at: datetime
    ) -> Telemetry:
        return Telemetry(
            device_id=device.device_id,
            sequence=sequence,
            sent_at=received_at - timedelta(seconds=1),
            received_at=received_at,
            temperature_c=21.5,
            battery_pct=80,
            rssi_dbm=-50,
            uptime_s=sequence,
        )

    def _event(self, device: Device, occurred_at: datetime) -> DeviceEvent:
        return DeviceEvent(
            owner_id=device.owner_id,
            device_id=device.device_id,
            event_type="device_online",
            severity="success",
            occurred_at=occurred_at,
            details={},
        )

    def test_cleanup_deletes_only_expired_telemetry_and_events_globally(self) -> None:
        # Keep the test cutoff far before any local development data because
        # retention is deliberately global, even inside this rolled-back test.
        cutoff = datetime(2000, 1, 2, 12, tzinfo=timezone.utc)
        old = cutoff - timedelta(microseconds=1)
        new = cutoff + timedelta(microseconds=1)
        baseline_telemetry = self.session.scalar(
            select(func.count()).select_from(Telemetry)
        )
        baseline_events = self.session.scalar(
            select(func.count()).select_from(DeviceEvent)
        )
        rows = [
            self._telemetry(self.device, 1, old),
            self._telemetry(self.device, 2, cutoff),
            self._telemetry(self.device, 3, new),
            self._telemetry(self.other_device, 4, old),
            self._event(self.device, old),
            self._event(self.device, cutoff),
            self._event(self.device, new),
            self._event(self.other_device, old),
        ]
        self.session.add_all(rows)

        rule = AlertRule(
            owner_id=self.owner.id,
            device_id=self.device.device_id,
            name="Retained rule",
            rule_type="metric_threshold",
            severity="warning",
            enabled=True,
            metric="temperature_c",
            operator="gt",
            threshold=30,
        )
        self.session.add(rule)
        self.session.flush()
        alert = Alert(
            owner_id=self.owner.id,
            device_id=self.device.device_id,
            rule_id=rule.id,
            rule_name=rule.name,
            rule_type=rule.rule_type,
            severity=rule.severity,
            status="active",
            condition="Temperature > 30 C",
            metric=rule.metric,
            operator=rule.operator,
            threshold=rule.threshold,
            observed_value=31,
            opened_at=old,
        )
        command = DeviceCommand(
            command_id=str(uuid4()),
            device_id=self.device.device_id,
            command_type="set_led",
            arguments={"on": True},
            status="pending",
            issued_at=old,
        )
        self.session.add_all([alert, command])
        self.session.flush()

        result = cleanup_expired_data(self.session, cutoff)

        self.assertEqual(result, RetentionResult(2, 2))
        self.assertEqual(
            list(
                self.session.scalars(
                    select(Telemetry.sequence)
                    .where(
                        Telemetry.device_id.in_(
                            [self.device.device_id, self.other_device.device_id]
                        )
                    )
                    .order_by(Telemetry.sequence)
                )
            ),
            [2, 3],
        )
        remaining_event_times = list(
            self.session.scalars(
                select(DeviceEvent.occurred_at)
                .where(
                    DeviceEvent.device_id.in_(
                        [self.device.device_id, self.other_device.device_id]
                    )
                )
                .order_by(DeviceEvent.occurred_at)
            )
        )
        self.assertEqual(remaining_event_times, [cutoff, new])
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Telemetry)),
            baseline_telemetry + 2,
        )
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(DeviceEvent)),
            baseline_events + 2,
        )
        self.assertIsNotNone(self.session.get(User, self.owner.id))
        self.assertIsNotNone(self.session.get(Device, self.device.device_id))
        self.assertIsNotNone(self.session.get(AlertRule, rule.id))
        self.assertIsNotNone(self.session.get(Alert, alert.id))
        self.assertIsNotNone(self.session.get(DeviceCommand, command.command_id))

    def test_cleanup_with_no_expired_rows_is_harmless(self) -> None:
        cutoff = datetime(2000, 1, 2, 12, tzinfo=timezone.utc)
        self.session.add_all(
            [
                self._telemetry(self.device, 1, cutoff),
                self._event(self.device, cutoff + timedelta(seconds=1)),
            ]
        )
        self.session.flush()

        self.assertEqual(
            cleanup_expired_data(self.session, cutoff), RetentionResult(0, 0)
        )


class RetentionCleanerTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_is_logged_and_next_run_retries(self) -> None:
        retried = threading.Event()
        calls = 0

        def cleanup() -> RetentionResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("test-only cleanup failure")
            retried.set()
            return RetentionResult(0, 0)

        cleaner = RetentionCleaner(interval_seconds=0.001, cleanup=cleanup)
        with patch("deviceops_api.retention.logger.exception") as log_failure:
            await cleaner.start()
            self.assertTrue(await asyncio.to_thread(retried.wait, 1))
            await cleaner.stop()

        self.assertGreaterEqual(calls, 2)
        log_failure.assert_called_once_with(
            "Retention cleanup failed; the next scheduled run will retry"
        )
        self.assertIsNone(cleaner._task)


if __name__ == "__main__":
    unittest.main()
