"""Capability-driven telemetry validation, persistence, and API tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from deviceops_api.database import engine
from deviceops_api.models import Device, Telemetry, User
from deviceops_api.mqtt import MqttIngestor
from deviceops_api.mqtt_auth import create_authenticated_envelope
from deviceops_api.routes.devices import get_device_telemetry
from deviceops_api.schemas import TelemetryPayload, TelemetryRead


class TelemetryValidationTests(unittest.TestCase):
    def payload(self, metrics: dict) -> dict:
        return {
            "protocol_version": 1,
            "device_id": "dev-schema-test",
            "sent_at": "2026-09-24T12:00:00Z",
            "sequence": 1,
            "metrics": metrics,
        }

    def test_additional_scalar_metrics_work_without_first_class_metrics(self) -> None:
        payload = TelemetryPayload.model_validate(
            self.payload(
                {
                    "co2_ppm": 742,
                    "voc_index": 88,
                    "occupied": True,
                    "air_quality": "Good",
                }
            )
        )

        self.assertIsNone(payload.metrics.temperature_c)
        self.assertIsNone(payload.metrics.rssi_dbm)
        self.assertIsNone(payload.metrics.uptime_s)
        self.assertEqual(
            payload.metrics.model_extra,
            {
                "co2_ppm": 742,
                "voc_index": 88,
                "occupied": True,
                "air_quality": "Good",
            },
        )

    def test_empty_or_null_only_metrics_are_rejected(self) -> None:
        for metrics in ({}, {"temperature_c": None}, {"custom_metric": None}):
            with self.subTest(metrics=metrics), self.assertRaises(ValidationError):
                TelemetryPayload.model_validate(self.payload(metrics))

    def test_legacy_payload_and_supplied_field_validation_remain(self) -> None:
        payload = TelemetryPayload.model_validate(
            self.payload(
                {"temperature_c": 23.4, "rssi_dbm": -58, "uptime_s": 17}
            )
        )
        self.assertEqual(payload.metrics.temperature_c, 23.4)
        self.assertEqual(payload.metrics.rssi_dbm, -58)
        self.assertEqual(payload.metrics.uptime_s, 17)

        bme_payload = TelemetryPayload.model_validate(
            self.payload(
                {
                    "temperature_c": 22.8,
                    "humidity_pct": 48.2,
                    "pressure_hpa": 1012.6,
                    "rssi_dbm": -61,
                    "uptime_s": 240,
                }
            )
        )
        self.assertEqual(bme_payload.metrics.humidity_pct, 48.2)
        self.assertEqual(bme_payload.metrics.pressure_hpa, 1012.6)

        invalid_metrics = (
            {"temperature_c": float("inf")},
            {"battery_pct": 101},
            {"humidity_pct": -1},
            {"rssi_dbm": -55.5},
            {"uptime_s": -1},
            {"uptime_s": 1.5},
        )
        for metrics in invalid_metrics:
            with self.subTest(metrics=metrics), self.assertRaises(ValidationError):
                TelemetryPayload.model_validate(self.payload(metrics))


class TelemetryPersistenceTests(unittest.TestCase):
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
            email=f"telemetry-owner-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.session.add(self.owner)
        self.session.flush()
        self.key = hashlib.sha256(b"telemetry-test-only-key").digest()
        self.session_id = "e" * 32
        self.device = Device(
            device_id=f"dev-telemetry-{suffix}",
            owner_id=self.owner.id,
            device_secret_hash=self.key.hex(),
            mqtt_session_id=self.session_id,
            status="online",
        )
        self.session.add(self.device)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    @contextmanager
    def mqtt_transaction(self):
        with self.session.begin():
            yield self.session

    def test_additional_only_message_persists_and_round_trips(self) -> None:
        sent_at = datetime.now(timezone.utc)
        body = json.dumps(
            {
                "protocol_version": 1,
                "device_id": self.device.device_id,
                "sent_at": sent_at.isoformat(),
                "sequence": 1,
                "metrics": {
                    "co2_ppm": 815,
                    "voc_index": 94,
                    "occupied": True,
                    "air_quality": "Fair",
                },
            }
        )
        topic = f"deviceops/v1/devices/{self.device.device_id}/telemetry"
        message = create_authenticated_envelope(
            body,
            self.key,
            "d2s",
            topic,
            self.session_id,
        ).encode()

        with (
            patch("deviceops_api.mqtt.SessionLocal") as session_factory,
            patch("deviceops_api.mqtt.realtime_hub") as hub,
            patch("deviceops_api.mqtt.evaluate_committed_metric_sample"),
        ):
            session_factory.begin.side_effect = self.mqtt_transaction
            MqttIngestor()._process_message(topic, message)

        stored = (
            self.session.query(Telemetry)
            .filter(Telemetry.device_id == self.device.device_id)
            .one()
        )
        self.assertIsNone(stored.temperature_c)
        self.assertIsNone(stored.battery_pct)
        self.assertIsNone(stored.humidity_pct)
        self.assertIsNone(stored.pressure_hpa)
        self.assertIsNone(stored.rssi_dbm)
        self.assertIsNone(stored.uptime_s)
        self.assertEqual(stored.additional_metrics["co2_ppm"], 815)
        self.assertIs(stored.additional_metrics["occupied"], True)

        rows = get_device_telemetry(
            self.device.device_id,
            self.session,
            self.owner,
            limit=100,
        )
        response = TelemetryRead.model_validate(rows[0])
        self.assertIsNone(response.temperature_c)
        self.assertIsNone(response.rssi_dbm)
        self.assertIsNone(response.uptime_s)
        self.assertEqual(response.additional_metrics["air_quality"], "Fair")

        event = hub.publish_from_thread.call_args.args[1]
        self.assertIsNone(event["data"]["temperature_c"])
        self.assertIsNone(event["data"]["rssi_dbm"])
        self.assertIsNone(event["data"]["uptime_s"])
        self.assertEqual(event["data"]["additional_metrics"]["voc_index"], 94)


if __name__ == "__main__":
    unittest.main()
