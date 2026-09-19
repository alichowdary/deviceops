"""Focused owner-scoped device naming and deletion tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
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
from deviceops_api.mqtt import MqttIngestor
from deviceops_api.mqtt_auth import create_authenticated_envelope
from deviceops_api.routes.devices import delete_device, update_device
from deviceops_api.schemas import DeviceRead, DeviceUpdate


class DeviceManagementTests(unittest.TestCase):
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
            email=f"device-owner-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.other_user = User(
            email=f"device-other-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.session.add_all([self.owner, self.other_user])
        self.session.flush()

        self.signing_key = hashlib.sha256(b"device-management-key").digest()
        self.session_id = "d" * 32
        self.device = Device(
            device_id=f"dev-managed-{suffix}",
            owner_id=self.owner.id,
            device_secret_hash=self.signing_key.hex(),
            mqtt_session_id=self.session_id,
            status="online",
        )
        self.other_device = Device(
            device_id=f"dev-other-{suffix}",
            owner_id=self.other_user.id,
            device_secret_hash=hashlib.sha256(b"other-key").hexdigest(),
            status="unknown",
        )
        self.session.add_all([self.device, self.other_device])
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def test_owner_can_rename_trim_clear_and_device_id_is_immutable(self) -> None:
        original_id = self.device.device_id
        self.assertIsNone(self.device.display_name)

        renamed = update_device(
            original_id,
            DeviceUpdate(display_name="  Workshop sensor  "),
            self.session,
            self.owner,
        )
        self.assertEqual(renamed.display_name, "Workshop sensor")
        self.assertEqual(renamed.device_id, original_id)
        self.assertEqual(
            DeviceRead.model_validate(renamed).display_name, "Workshop sensor"
        )

        cleared = update_device(
            original_id,
            DeviceUpdate(display_name=None),
            self.session,
            self.owner,
        )
        self.assertIsNone(cleared.display_name)
        self.assertEqual(cleared.device_id, original_id)

        blank = update_device(
            original_id,
            DeviceUpdate(display_name="   "),
            self.session,
            self.owner,
        )
        self.assertIsNone(blank.display_name)

    def test_display_name_validation_rejects_too_long_and_device_id(self) -> None:
        with self.assertRaises(ValidationError):
            DeviceUpdate(display_name="x" * 81)
        with self.assertRaises(ValidationError):
            DeviceUpdate.model_validate(
                {"display_name": "Renamed", "device_id": "replacement-id"}
            )

    def test_update_hides_other_and_unknown_devices(self) -> None:
        for device_id in (self.other_device.device_id, "missing-device"):
            with self.subTest(device_id=device_id):
                with self.assertRaises(HTTPException) as raised:
                    update_device(
                        device_id,
                        DeviceUpdate(display_name="Hidden"),
                        self.session,
                        self.owner,
                    )
                self.assertEqual(raised.exception.status_code, 404)

    def test_delete_hides_other_and_unknown_devices(self) -> None:
        for device_id in (self.other_device.device_id, "missing-device"):
            with self.subTest(device_id=device_id):
                with self.assertRaises(HTTPException) as raised:
                    delete_device(
                        device_id,
                        self.session,
                        self.owner,
                    )
                self.assertEqual(raised.exception.status_code, 404)
        self.assertIsNotNone(
            self.session.get(Device, self.other_device.device_id)
        )

    def test_owner_delete_cascades_and_old_mqtt_credential_is_rejected(self) -> None:
        now = datetime.now(timezone.utc)
        telemetry = Telemetry(
            device_id=self.device.device_id,
            sequence=1,
            sent_at=now,
            received_at=now,
            temperature_c=22.5,
            battery_pct=80.0,
            rssi_dbm=-55,
            uptime_s=10,
        )
        command = DeviceCommand(
            command_id=str(uuid4()),
            device_id=self.device.device_id,
            command_type="request_diagnostics",
            arguments={},
            status="pending",
            issued_at=now,
        )
        event = DeviceEvent(
            owner_id=self.owner.id,
            device_id=self.device.device_id,
            event_type="device_online",
            severity="success",
            occurred_at=now,
            details={},
        )
        rule = AlertRule(
            owner_id=self.owner.id,
            device_id=self.device.device_id,
            name="Too warm",
            rule_type="metric_threshold",
            severity="warning",
            enabled=True,
            metric="temperature_c",
            operator="gt",
            threshold=30,
        )
        self.session.add_all([telemetry, command, event, rule])
        self.session.flush()
        alert = Alert(
            owner_id=self.owner.id,
            device_id=self.device.device_id,
            rule_id=rule.id,
            rule_name=rule.name,
            rule_type=rule.rule_type,
            severity=rule.severity,
            status="active",
            condition="Temperature > 30 °C",
            metric="temperature_c",
            operator="gt",
            threshold=30,
            observed_value=31,
            opened_at=now,
        )
        self.session.add(alert)
        self.session.commit()
        child_ids = {
            Telemetry: telemetry.id,
            DeviceCommand: command.command_id,
            DeviceEvent: event.id,
            AlertRule: rule.id,
            Alert: alert.id,
        }

        telemetry_body = json.dumps(
            {
                "protocol_version": 1,
                "device_id": self.device.device_id,
                "sent_at": now.isoformat(),
                "sequence": 2,
                "metrics": {
                    "temperature_c": 23.0,
                    "battery_pct": 79.9,
                    "rssi_dbm": -54,
                    "uptime_s": 11,
                },
            }
        )
        topic = f"deviceops/v1/devices/{self.device.device_id}/telemetry"
        old_message = create_authenticated_envelope(
            telemetry_body,
            self.signing_key,
            "d2s",
            topic,
            self.session_id,
        ).encode()

        response = delete_device(
            self.device.device_id,
            self.session,
            self.owner,
        )
        self.assertEqual(response.status_code, 204)
        self.session.expire_all()
        self.assertIsNone(self.session.get(Device, self.device.device_id))
        for model, key in child_ids.items():
            with self.subTest(model=model.__name__):
                self.assertIsNone(self.session.get(model, key))
        self.session.commit()

        ingestor = MqttIngestor()
        with (
            patch("deviceops_api.mqtt.SessionLocal") as session_factory,
            patch("deviceops_api.mqtt.realtime_hub") as hub,
        ):
            session_factory.begin.side_effect = self._mqtt_transaction
            ingestor._process_message(topic, old_message)
        hub.publish_from_thread.assert_not_called()
        telemetry_count = self.session.scalar(
            select(func.count()).select_from(Telemetry).where(
                Telemetry.device_id == self.device.device_id
            )
        )
        self.assertEqual(telemetry_count, 0)

    @contextmanager
    def _mqtt_transaction(self):
        with self.session.begin():
            yield self.session


if __name__ == "__main__":
    unittest.main()
