"""Focused persistence, evaluation, routing, and lifecycle tests for alerts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from deviceops_api.alert_evaluator import OfflineAlertEvaluator
from deviceops_api.alerts import (
    evaluate_metric_rules,
    evaluate_offline_rules,
    telemetry_metric_values,
)
from deviceops_api.database import engine
from deviceops_api.models import (
    Alert,
    AlertRule,
    Device,
    DeviceEvent,
    Telemetry,
    User,
)
from deviceops_api.routes.alert_rules import delete_alert_rule, update_alert_rule
from deviceops_api.routes.alerts import get_alert, list_alerts
from deviceops_api.schemas import AlertRead, AlertRuleUpdate


class AlertLifecycleTests(unittest.TestCase):
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
            email=f"alerts-owner-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.other_user = User(
            email=f"alerts-other-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.session.add_all([self.owner, self.other_user])
        self.session.flush()
        self.now = datetime.now(timezone.utc)
        self.device = Device(
            device_id=f"dev-alerts-owner-{suffix}",
            owner_id=self.owner.id,
            device_secret_hash="test-only-unused",
            status="online",
            first_seen_at=self.now,
            last_seen_at=self.now,
        )
        self.other_device = Device(
            device_id=f"dev-alerts-other-{suffix}",
            owner_id=self.other_user.id,
            device_secret_hash="test-only-unused",
            status="online",
            first_seen_at=self.now,
            last_seen_at=self.now,
        )
        self.never_connected = Device(
            device_id=f"dev-alerts-never-{suffix}",
            owner_id=self.owner.id,
            device_secret_hash="test-only-unused",
            status="unknown",
        )
        self.session.add_all(
            [self.device, self.other_device, self.never_connected]
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def _metric_rule(
        self,
        *,
        device: Device | None = None,
        owner: User | None = None,
        name: str = "Warm room",
        metric: str = "temperature_c",
        threshold: float = 30,
    ) -> AlertRule:
        rule = AlertRule(
            owner_id=(owner or self.owner).id,
            device_id=(device or self.device).device_id,
            name=name,
            rule_type="metric_threshold",
            severity="warning",
            enabled=True,
            metric=metric,
            operator="gt",
            threshold=threshold,
        )
        self.session.add(rule)
        self.session.commit()
        return rule

    def _offline_rule(
        self,
        *,
        device: Device | None = None,
        owner: User | None = None,
    ) -> AlertRule:
        rule = AlertRule(
            owner_id=(owner or self.owner).id,
            device_id=(device or self.device).device_id,
            name="Device unavailable",
            rule_type="device_offline",
            severity="critical",
            enabled=True,
            offline_after_seconds=5,
        )
        self.session.add(rule)
        self.session.commit()
        return rule

    def _evaluate_metric(
        self, value: float | None, *, at_offset: int
    ) -> list:
        changes = evaluate_metric_rules(
            self.session,
            device_id=self.device.device_id,
            metrics={"temperature_c": value},
            observed_at=self.now + timedelta(seconds=at_offset),
        )
        self.session.commit()
        return changes

    def _alerts(self, rule_id: int) -> list[Alert]:
        return list(
            self.session.scalars(
                select(Alert).where(Alert.rule_id == rule_id).order_by(Alert.id)
            )
        )

    def _events(self, rule_id: int) -> list[DeviceEvent]:
        return list(
            self.session.scalars(
                select(DeviceEvent)
                .where(
                    DeviceEvent.device_id == self.device.device_id,
                    DeviceEvent.details["rule_id"].as_integer() == rule_id,
                )
                .order_by(DeviceEvent.id)
            )
        )

    def test_metric_alert_opens_once_resolves_and_can_open_again(self) -> None:
        rule = self._metric_rule()

        self.assertEqual(self._evaluate_metric(28, at_offset=1), [])
        opened = self._evaluate_metric(31, at_offset=2)
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].alert_message["data"]["status"], "active")
        self.assertNotIn("owner_id", json.dumps(opened[0].alert_message))

        self.assertEqual(self._evaluate_metric(32, at_offset=3), [])
        self.assertEqual(self._evaluate_metric(None, at_offset=4), [])
        self.assertEqual(self._alerts(rule.id)[0].status, "active")

        resolved = self._evaluate_metric(29, at_offset=5)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(
            resolved[0].alert_message["data"]["resolution_reason"],
            "condition_cleared",
        )
        reopened = self._evaluate_metric(31, at_offset=6)
        self.assertEqual(len(reopened), 1)

        alerts = self._alerts(rule.id)
        self.assertEqual([alert.status for alert in alerts], ["resolved", "active"])
        self.assertNotEqual(alerts[0].id, alerts[1].id)
        events = self._events(rule.id)
        self.assertEqual(
            [event.event_type for event in events],
            ["alert_opened", "alert_resolved", "alert_opened"],
        )
        self.assertEqual(
            [event.severity for event in events],
            ["warning", "success", "warning"],
        )

    def test_additional_numeric_metric_opens_resolves_and_missing_is_unchanged(self) -> None:
        self.device.capabilities = {
            "telemetry": {
                "co2_ppm": {
                    "type": "number",
                    "label": "CO₂",
                    "unit": "ppm",
                },
                "occupied": {"type": "boolean", "label": "Occupied"},
                "air_quality": {"type": "string", "label": "Air quality"},
            }
        }
        self.session.commit()
        rule = self._metric_rule(
            name="High CO2", metric="co2_ppm", threshold=1000
        )
        sample = Telemetry(
            device_id=self.device.device_id,
            sequence=1,
            sent_at=self.now,
            received_at=self.now,
            temperature_c=None,
            battery_pct=None,
            humidity_pct=None,
            pressure_hpa=None,
            rssi_dbm=None,
            uptime_s=None,
            additional_metrics={
                "co2_ppm": 1125,
                "occupied": True,
                "air_quality": "Poor",
            },
        )
        metrics = telemetry_metric_values(sample)
        self.assertEqual(metrics["co2_ppm"], 1125)
        self.assertIsNone(metrics["temperature_c"])

        opened = evaluate_metric_rules(
            self.session,
            device_id=self.device.device_id,
            metrics=metrics,
            observed_at=self.now + timedelta(seconds=1),
        )
        self.session.commit()
        self.assertEqual(len(opened), 1)
        self.assertEqual(self._alerts(rule.id)[0].status, "active")

        for incompatible in (
            {},
            {"co2_ppm": None},
            {"co2_ppm": "900"},
            {"co2_ppm": True},
            {"co2_ppm": float("nan")},
        ):
            with self.subTest(metrics=incompatible):
                changes = evaluate_metric_rules(
                    self.session,
                    device_id=self.device.device_id,
                    metrics=incompatible,
                    observed_at=self.now + timedelta(seconds=2),
                )
                self.session.commit()
                self.assertEqual(changes, [])
                self.assertEqual(self._alerts(rule.id)[0].status, "active")

        resolved = evaluate_metric_rules(
            self.session,
            device_id=self.device.device_id,
            metrics={"co2_ppm": 850},
            observed_at=self.now + timedelta(seconds=3),
        )
        self.session.commit()
        self.assertEqual(len(resolved), 1)
        self.assertEqual(self._alerts(rule.id)[0].status, "resolved")
        self.assertEqual(
            self._alerts(rule.id)[0].condition,
            "CO₂ > 1000 ppm",
        )

    def test_first_class_uptime_integer_metric_evaluates(self) -> None:
        rule = self._metric_rule(
            name="Long uptime", metric="uptime_s", threshold=60
        )
        sample = Telemetry(
            device_id=self.device.device_id,
            sequence=1,
            sent_at=self.now,
            received_at=self.now,
            temperature_c=22,
            battery_pct=None,
            humidity_pct=45,
            pressure_hpa=1013,
            rssi_dbm=-60,
            uptime_s=61,
            additional_metrics=None,
        )
        changes = evaluate_metric_rules(
            self.session,
            device_id=self.device.device_id,
            metrics=telemetry_metric_values(sample),
            observed_at=self.now + timedelta(seconds=1),
        )
        self.session.commit()

        self.assertEqual(len(changes), 1)
        self.assertEqual(self._alerts(rule.id)[0].observed_value, 61)

    def test_offline_duration_reconnect_and_never_connected_behavior(self) -> None:
        rule = self._offline_rule()
        self.device.status = "offline"
        self.device.offline_since = self.now
        self.device.last_seen_at = self.now
        self.session.commit()

        before = evaluate_offline_rules(
            self.session, observed_at=self.now + timedelta(seconds=4)
        )
        self.session.commit()
        self.assertEqual(before, [])
        opened = evaluate_offline_rules(
            self.session, observed_at=self.now + timedelta(seconds=5)
        )
        self.session.commit()
        self.assertEqual(len(opened), 1)
        repeated = evaluate_offline_rules(
            self.session, observed_at=self.now + timedelta(seconds=10)
        )
        self.session.commit()
        self.assertEqual(repeated, [])

        self.device.status = "online"
        self.device.offline_since = None
        self.session.commit()
        resolved = evaluate_offline_rules(
            self.session, observed_at=self.now + timedelta(seconds=11)
        )
        self.session.commit()
        self.assertEqual(len(resolved), 1)
        self.assertEqual(
            resolved[0].alert_message["data"]["resolution_reason"],
            "device_reconnected",
        )

        self.device.status = "offline"
        self.device.offline_since = self.now + timedelta(seconds=20)
        self.device.last_seen_at = self.device.offline_since
        self.session.commit()
        self.assertEqual(
            evaluate_offline_rules(
                self.session, observed_at=self.now + timedelta(seconds=24)
            ),
            [],
        )
        self.device.status = "online"
        self.device.offline_since = None
        self.session.commit()
        self.assertEqual(
            evaluate_offline_rules(
                self.session, observed_at=self.now + timedelta(seconds=25)
            ),
            [],
        )

        self._offline_rule(device=self.never_connected)
        self.assertEqual(
            evaluate_offline_rules(
                self.session, observed_at=self.now + timedelta(days=1)
            ),
            [],
        )
        self.session.commit()
        self.assertEqual(len(self._alerts(rule.id)), 1)

    def test_disable_reenable_edit_and_delete_preserve_history(self) -> None:
        rule = self._metric_rule()
        self._evaluate_metric(31, at_offset=1)

        with patch("deviceops_api.routes.alert_rules.publish_alert_changes"):
            disabled = update_alert_rule(
                rule.id,
                AlertRuleUpdate(enabled=False),
                self.session,
                self.owner,
            )
        self.assertFalse(disabled.enabled)
        first_alert = self._alerts(rule.id)[0]
        self.assertEqual(first_alert.status, "resolved")
        self.assertEqual(first_alert.resolution_reason, "rule_disabled")

        update_alert_rule(
            rule.id,
            AlertRuleUpdate(enabled=True),
            self.session,
            self.owner,
        )
        self._evaluate_metric(31, at_offset=2)
        self.assertEqual(len(self._alerts(rule.id)), 2)

        update_alert_rule(
            rule.id,
            AlertRuleUpdate(threshold=20),
            self.session,
            self.owner,
        )
        self._evaluate_metric(31, at_offset=3)
        self.assertEqual(len(self._alerts(rule.id)), 2)

        with patch("deviceops_api.routes.alert_rules.publish_alert_changes"):
            response = delete_alert_rule(
                rule.id, self.session, self.owner
            )
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.session.get(AlertRule, rule.id))
        self.session.expire_all()
        history = list(
            self.session.scalars(
                select(Alert)
                .where(Alert.device_id == self.device.device_id)
                .order_by(Alert.id)
            )
        )
        self.assertEqual(len(history), 2)
        self.assertTrue(all(alert.rule_id is None for alert in history))
        self.assertTrue(all(alert.status == "resolved" for alert in history))
        self.assertEqual(history[-1].resolution_reason, "rule_deleted")
        self.assertTrue(all(alert.rule_name == "Warm room" for alert in history))

    def test_rest_filters_owner_isolation_and_public_shape(self) -> None:
        active_rule = self._metric_rule()
        self._evaluate_metric(31, at_offset=1)
        resolved_rule = self._metric_rule(
            device=self.never_connected, name="Second rule"
        )
        resolved_rule.threshold = 10
        self.session.commit()
        evaluate_metric_rules(
            self.session,
            device_id=self.never_connected.device_id,
            metrics={"temperature_c": 12},
            observed_at=self.now + timedelta(seconds=2),
        )
        self.session.commit()
        evaluate_metric_rules(
            self.session,
            device_id=self.never_connected.device_id,
            metrics={"temperature_c": 5},
            observed_at=self.now + timedelta(seconds=3),
        )
        self.session.commit()

        other_rule = self._metric_rule(
            device=self.other_device,
            owner=self.other_user,
            name="Other owner",
        )
        evaluate_metric_rules(
            self.session,
            device_id=self.other_device.device_id,
            metrics={"temperature_c": 31},
            observed_at=self.now + timedelta(seconds=4),
        )
        self.session.commit()

        active = list_alerts(
            session=self.session,
            current_user=self.owner,
            limit=100,
            status="active",
            device_id=None,
            severity=None,
            rule_id=active_rule.id,
        )
        resolved = list_alerts(
            session=self.session,
            current_user=self.owner,
            limit=100,
            status="resolved",
            device_id=self.never_connected.device_id,
            severity="warning",
            rule_id=resolved_rule.id,
        )
        self.assertEqual(len(active), 1)
        self.assertEqual(len(resolved), 1)
        public = AlertRead.model_validate(active[0]).model_dump()
        self.assertNotIn("owner_id", public)
        self.assertEqual(get_alert(active[0].id, self.session, self.owner), active[0])

        other_alert = self.session.scalar(
            select(Alert).where(Alert.rule_id == other_rule.id)
        )
        self.assertIsNotNone(other_alert)
        with self.assertRaises(HTTPException) as raised:
            get_alert(other_alert.id, self.session, self.owner)
        self.assertEqual(raised.exception.status_code, 404)
        with self.assertRaises(HTTPException) as filtered:
            list_alerts(
                session=self.session,
                current_user=self.owner,
                limit=100,
                status=None,
                device_id=self.other_device.device_id,
                severity=None,
                rule_id=None,
            )
        self.assertEqual(filtered.exception.status_code, 404)


class OfflineEvaluatorTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_stop_is_idempotent_and_evaluates_without_long_sleep(self) -> None:
        called = threading.Event()
        evaluator = OfflineAlertEvaluator(interval_seconds=0.01)
        with patch(
            "deviceops_api.alert_evaluator.evaluate_offline_alerts_once",
            side_effect=called.set,
        ) as evaluate:
            await evaluator.start()
            first_task = evaluator._task
            await evaluator.start()
            self.assertIs(evaluator._task, first_task)
            self.assertTrue(await asyncio.to_thread(called.wait, 1))
            await evaluator.stop()
            await evaluator.stop()
        self.assertGreaterEqual(evaluate.call_count, 1)
        self.assertIsNone(evaluator._task)


if __name__ == "__main__":
    unittest.main()
