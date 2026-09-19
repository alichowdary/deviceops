"""Focused persistence, validation, and ownership tests for alert rules."""

from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from deviceops_api.database import engine
from deviceops_api.models import AlertRule, Device, User
from deviceops_api.routes.alert_rules import (
    create_alert_rule,
    delete_alert_rule,
    get_alert_rule,
    list_alert_rules,
    update_alert_rule,
)
from deviceops_api.schemas import (
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleUpdate,
)


class AlertRuleTests(unittest.TestCase):
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
            email=f"rules-owner-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.other_user = User(
            email=f"rules-other-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.session.add_all([self.owner, self.other_user])
        self.session.flush()
        self.device = Device(
            device_id=f"dev-rules-owner-{suffix}",
            owner_id=self.owner.id,
            device_secret_hash="test-only-unused",
            status="unknown",
            capabilities={
                "telemetry": {
                    "temperature_c": {
                        "type": "number",
                        "label": "Temperature",
                        "unit": "°C",
                    },
                    "light_lux": {
                        "type": "number",
                        "label": "Ambient light",
                        "unit": "lux",
                    },
                    "sample_count": {
                        "type": "integer",
                        "label": "Sample count",
                        "unit": None,
                    },
                    "motion_detected": {
                        "type": "boolean",
                        "label": "Motion detected",
                        "unit": None,
                    },
                    "operating_mode": {
                        "type": "string",
                        "label": "Operating mode",
                        "unit": None,
                    },
                    "uptime_s": {
                        "type": "integer",
                        "label": "Uptime",
                        "unit": "s",
                    },
                }
            },
        )
        self.other_device = Device(
            device_id=f"dev-rules-other-{suffix}",
            owner_id=self.other_user.id,
            device_secret_hash="test-only-unused",
            status="unknown",
            capabilities={"telemetry": {}},
        )
        self.session.add_all([self.device, self.other_device])
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def _create_metric_rule(self, **overrides) -> AlertRule:
        values = {
            "device_id": self.device.device_id,
            "name": "Warm room",
            "rule_type": "metric_threshold",
            "severity": "warning",
            "enabled": True,
            "metric": "temperature_c",
            "operator": "gt",
            "threshold": 30,
        }
        values.update(overrides)
        return create_alert_rule(
            AlertRuleCreate.model_validate(values),
            self.session,
            self.owner,
        )

    def _list(self, user: User, **filters) -> list[AlertRule]:
        return list_alert_rules(
            session=self.session,
            current_user=user,
            device_id=filters.get("device_id"),
            enabled=filters.get("enabled"),
            rule_type=filters.get("rule_type"),
            severity=filters.get("severity"),
        )

    def test_create_metric_rule_and_public_shape(self) -> None:
        rule = self._create_metric_rule()

        self.assertEqual(rule.owner_id, self.owner.id)
        self.assertEqual(rule.metric, "temperature_c")
        self.assertEqual(rule.threshold, 30)
        self.assertEqual(
            get_alert_rule(rule.id, self.session, self.owner), rule
        )
        response = AlertRuleRead.model_validate(rule).model_dump()
        self.assertNotIn("owner_id", response)
        self.assertIsNotNone(response["created_at"])
        self.assertIsNotNone(response["updated_at"])

    def test_create_offline_rule(self) -> None:
        request = AlertRuleCreate(
            device_id=self.device.device_id,
            name="  Workshop offline  ",
            rule_type="device_offline",
            severity="critical",
            offline_after_seconds=5,
        )
        rule = create_alert_rule(
            request, self.session, self.owner
        )

        self.assertEqual(rule.name, "Workshop offline")
        self.assertEqual(rule.offline_after_seconds, 5)
        self.assertIsNone(rule.metric)
        self.assertTrue(rule.enabled)
        updated = update_alert_rule(
            rule.id,
            AlertRuleUpdate(offline_after_seconds=600),
            self.session,
            self.owner,
        )
        self.assertEqual(updated.offline_after_seconds, 600)

    def test_invalid_rule_inputs_are_rejected(self) -> None:
        invalid_payloads = [
            {
                "device_id": self.device.device_id,
                "rule_type": "metric_threshold",
                "metric": "temperature_c",
                "operator": "gt",
            },
            {
                "device_id": self.device.device_id,
                "rule_type": "metric_threshold",
                "metric": "temperature_c",
                "operator": "gt",
                "threshold": 30,
                "offline_after_seconds": 300,
            },
            {
                "device_id": self.device.device_id,
                "rule_type": "device_offline",
                "offline_after_seconds": 300,
                "metric": "humidity_pct",
            },
            {
                "device_id": self.device.device_id,
                "rule_type": "metric_threshold",
                "metric": "unsupported metric",
                "operator": "gt",
                "threshold": 1,
            },
            {
                "device_id": self.device.device_id,
                "rule_type": "metric_threshold",
                "metric": "temperature_c",
                "operator": "eq",
                "threshold": 1,
            },
            {
                "device_id": self.device.device_id,
                "rule_type": "metric_threshold",
                "metric": "temperature_c",
                "operator": "gt",
                "threshold": float("nan"),
            },
            {
                "device_id": self.device.device_id,
                "rule_type": "metric_threshold",
                "metric": "temperature_c",
                "operator": "gt",
                "threshold": float("inf"),
            },
            {
                "device_id": self.device.device_id,
                "rule_type": "device_offline",
                "offline_after_seconds": 4,
            },
            {
                "device_id": self.device.device_id,
                "rule_type": "device_offline",
                "offline_after_seconds": 300,
                "enabled": 1,
            },
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                AlertRuleCreate.model_validate(payload)

        for update in ({}, {"enabled": None}, {"device_id": self.device.device_id}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                AlertRuleUpdate.model_validate(update)

    def test_create_accepts_any_advertised_numeric_metric(self) -> None:
        number_rule = self._create_metric_rule(
            metric="light_lux", threshold=250.5
        )
        integer_rule = self._create_metric_rule(
            metric="sample_count", threshold=10
        )
        uptime_rule = self._create_metric_rule(
            metric="uptime_s", threshold=60
        )

        self.assertEqual(number_rule.metric, "light_lux")
        self.assertEqual(number_rule.threshold, 250.5)
        self.assertEqual(integer_rule.metric, "sample_count")
        self.assertEqual(uptime_rule.metric, "uptime_s")

    def test_create_rejects_non_numeric_unadvertised_and_missing_capabilities(self) -> None:
        for metric in ("motion_detected", "operating_mode", "not_advertised"):
            with self.subTest(metric=metric), self.assertRaises(HTTPException) as raised:
                self._create_metric_rule(metric=metric, threshold=1)
            self.assertEqual(raised.exception.status_code, 422)

        capabilities = self.device.capabilities
        self.device.capabilities = None
        self.session.commit()
        with self.assertRaises(HTTPException) as raised:
            self._create_metric_rule()
        self.assertEqual(raised.exception.status_code, 422)
        self.device.capabilities = capabilities
        self.session.commit()

    def test_existing_metric_rule_remains_editable_after_manifest_change(self) -> None:
        rule = self._create_metric_rule(metric="light_lux", threshold=250)
        self.device.capabilities = {"telemetry": {}}
        self.session.commit()

        updated = update_alert_rule(
            rule.id,
            AlertRuleUpdate(threshold=275),
            self.session,
            self.owner,
        )

        self.assertEqual(updated.metric, "light_lux")
        self.assertEqual(updated.threshold, 275)

    def test_list_is_owner_scoped_and_filters_work(self) -> None:
        metric = self._create_metric_rule(severity="warning")
        offline = create_alert_rule(
            AlertRuleCreate(
                device_id=self.device.device_id,
                rule_type="device_offline",
                severity="critical",
                enabled=False,
                offline_after_seconds=300,
            ),
            self.session,
            self.owner,
        )
        create_alert_rule(
            AlertRuleCreate(
                device_id=self.other_device.device_id,
                rule_type="device_offline",
                offline_after_seconds=600,
            ),
            self.session,
            self.other_user,
        )

        self.assertEqual({r.id for r in self._list(self.owner)}, {metric.id, offline.id})
        self.assertEqual(len(self._list(self.other_user)), 1)
        self.assertEqual(self._list(self.owner, enabled=False), [offline])
        self.assertEqual(
            self._list(self.owner, rule_type="metric_threshold"), [metric]
        )
        self.assertEqual(self._list(self.owner, severity="critical"), [offline])
        self.assertEqual(
            {r.id for r in self._list(self.owner, device_id=self.device.device_id)},
            {metric.id, offline.id},
        )

    def test_unowned_device_and_rule_access_return_not_found(self) -> None:
        with self.assertRaises(HTTPException) as create_error:
            create_alert_rule(
                AlertRuleCreate(
                    device_id=self.other_device.device_id,
                    rule_type="device_offline",
                    offline_after_seconds=300,
                ),
                self.session,
                self.owner,
            )
        self.assertEqual(create_error.exception.status_code, 404)
        with self.assertRaises(HTTPException) as metric_create_error:
            create_alert_rule(
                AlertRuleCreate(
                    device_id=self.other_device.device_id,
                    rule_type="metric_threshold",
                    metric="not_advertised",
                    operator="gt",
                    threshold=1,
                ),
                self.session,
                self.owner,
            )
        self.assertEqual(metric_create_error.exception.status_code, 404)
        with self.assertRaises(HTTPException) as filter_error:
            self._list(self.owner, device_id=self.other_device.device_id)
        self.assertEqual(filter_error.exception.status_code, 404)

        other_rule = create_alert_rule(
            AlertRuleCreate(
                device_id=self.other_device.device_id,
                rule_type="device_offline",
                offline_after_seconds=300,
            ),
            self.session,
            self.other_user,
        )
        for operation in (
            lambda: get_alert_rule(other_rule.id, self.session, self.owner),
            lambda: update_alert_rule(
                other_rule.id,
                AlertRuleUpdate(enabled=False),
                self.session,
                self.owner,
            ),
            lambda: delete_alert_rule(other_rule.id, self.session, self.owner),
        ):
            with self.assertRaises(HTTPException) as raised:
                operation()
            self.assertEqual(raised.exception.status_code, 404)

    def test_patch_enable_disable_and_delete(self) -> None:
        rule = self._create_metric_rule()
        updated = update_alert_rule(
            rule.id,
            AlertRuleUpdate(
                name="Too warm",
                severity="critical",
                operator="gte",
                threshold=32.5,
                enabled=False,
            ),
            self.session,
            self.owner,
        )
        self.assertEqual(updated.name, "Too warm")
        self.assertEqual(updated.severity, "critical")
        self.assertEqual(updated.operator, "gte")
        self.assertEqual(updated.threshold, 32.5)
        self.assertFalse(updated.enabled)

        enabled = update_alert_rule(
            rule.id,
            AlertRuleUpdate(enabled=True),
            self.session,
            self.owner,
        )
        self.assertTrue(enabled.enabled)
        response = delete_alert_rule(rule.id, self.session, self.owner)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.session.get(AlertRule, rule.id))

    def test_patch_rejects_fields_for_wrong_rule_type(self) -> None:
        rule = self._create_metric_rule()
        with self.assertRaises(HTTPException) as raised:
            update_alert_rule(
                rule.id,
                AlertRuleUpdate(offline_after_seconds=300),
                self.session,
                self.owner,
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_deleting_device_cascades_alert_rules(self) -> None:
        rule = self._create_metric_rule()
        rule_id = rule.id
        self.session.delete(self.device)
        self.session.commit()
        self.session.expire_all()

        self.assertIsNone(
            self.session.scalar(select(AlertRule).where(AlertRule.id == rule_id))
        )


if __name__ == "__main__":
    unittest.main()
