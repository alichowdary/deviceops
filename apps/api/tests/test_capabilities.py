"""Focused capability validation, persistence, ownership, and realtime tests."""

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
from sqlalchemy.orm import Session

from deviceops_api.database import engine
from deviceops_api.models import Device, User
from deviceops_api.mqtt import MqttIngestor
from deviceops_api.mqtt_auth import create_authenticated_envelope
from deviceops_api.routes.devices import get_device_capabilities
from deviceops_api.schemas import CommandCreate


class CapabilityTests(unittest.TestCase):
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
            email=f"cap-owner-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.other_user = User(
            email=f"cap-other-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.session.add_all([self.owner, self.other_user])
        self.session.flush()
        self.key = hashlib.sha256(b"capability-test-only-key").digest()
        self.session_id = "a" * 32
        self.device = Device(
            device_id=f"dev-cap-{suffix}",
            owner_id=self.owner.id,
            device_secret_hash=self.key.hex(),
            mqtt_session_id=self.session_id,
            status="online",
        )
        self.never_advertised = Device(
            device_id=f"dev-cap-empty-{suffix}",
            owner_id=self.owner.id,
            device_secret_hash=hashlib.sha256(b"empty-key").hexdigest(),
            status="unknown",
        )
        self.unowned = Device(
            device_id=f"dev-cap-unowned-{suffix}",
            owner_id=None,
            device_secret_hash=self.key.hex(),
            mqtt_session_id=self.session_id,
            status="online",
        )
        self.session.add_all([self.device, self.never_advertised, self.unowned])
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def manifest(self, **changes) -> dict:
        manifest = {
            "protocol_version": 1,
            "capabilities_version": 1,
            "device_id": self.device.device_id,
            "sent_at": "2026-09-19T12:00:00Z",
            "telemetry": {
                "temperature_c": {
                    "type": "number",
                    "label": "Temperature",
                    "unit": "°C",
                },
                "custom_voltage": {
                    "type": "number",
                    "label": "Custom voltage",
                    "unit": "V",
                },
            },
            "commands": {
                "set_led": {
                    "label": "LED",
                    "arguments": {
                        "on": {"type": "boolean", "label": "On"}
                    },
                }
            },
        }
        manifest.update(changes)
        return manifest

    def signed_message(
        self,
        manifest: dict | str,
        *,
        device_id: str | None = None,
        key: bytes | None = None,
        session_id: str | None = None,
    ) -> tuple[str, bytes]:
        topic_device_id = device_id or self.device.device_id
        topic = f"deviceops/v1/devices/{topic_device_id}/capabilities"
        body = manifest if isinstance(manifest, str) else json.dumps(manifest)
        envelope = create_authenticated_envelope(
            body,
            key or self.key,
            "d2s",
            topic,
            session_id or self.session_id,
        )
        return topic, envelope.encode()

    @contextmanager
    def mqtt_transaction(self):
        with self.session.begin():
            yield self.session

    def process(self, message: tuple[str, bytes]):
        ingestor = MqttIngestor()
        with (
            patch("deviceops_api.mqtt.SessionLocal") as session_factory,
            patch("deviceops_api.mqtt.realtime_hub") as hub,
        ):
            session_factory.begin.side_effect = self.mqtt_transaction
            ingestor._process_message(*message)
        return hub

    def test_valid_manifest_persists_replaces_and_publishes_owner_event(self) -> None:
        hub = self.process(self.signed_message(self.manifest()))
        self.assertEqual(
            self.device.capabilities["telemetry"]["custom_voltage"]["unit"], "V"
        )
        self.assertIsNotNone(self.device.capabilities_updated_at)
        hub.publish_from_thread.assert_called_once()
        owner_id, event = hub.publish_from_thread.call_args.args
        self.assertEqual(owner_id, self.owner.id)
        self.assertEqual(event["type"], "capabilities_updated")
        self.assertEqual(event["device_id"], self.device.device_id)
        self.assertNotIn("owner_id", json.dumps(event))

        first_updated_at = self.device.capabilities_updated_at
        replacement = self.manifest(
            telemetry={
                "uptime_s": {
                    "type": "integer",
                    "label": "Uptime",
                    "unit": "s",
                }
            },
            commands={},
        )
        self.process(self.signed_message(replacement))
        self.assertEqual(set(self.device.capabilities["telemetry"]), {"uptime_s"})
        self.assertGreaterEqual(self.device.capabilities_updated_at, first_updated_at)

    def test_get_is_owner_scoped_and_never_advertised_is_explicit_null(self) -> None:
        self.process(self.signed_message(self.manifest()))
        stored = get_device_capabilities(
            self.device.device_id, self.session, self.owner
        )
        self.assertEqual(stored.capabilities.device_id, self.device.device_id)
        self.assertIsNotNone(stored.updated_at)
        self.assertNotIn("owner_id", stored.model_dump_json())

        empty = get_device_capabilities(
            self.never_advertised.device_id, self.session, self.owner
        )
        self.assertIsNone(empty.capabilities)
        self.assertIsNone(empty.updated_at)

        with self.assertRaises(HTTPException) as raised:
            get_device_capabilities(
                self.device.device_id, self.session, self.other_user
            )
        self.assertEqual(raised.exception.status_code, 404)

    def test_security_and_identity_rejections_do_not_replace_state(self) -> None:
        self.process(self.signed_message(self.manifest()))
        original = self.device.capabilities
        cases = {
            "bad signature": self.signed_message(
                self.manifest(), key=b"wrong-signing-key"
            ),
            "stale session": self.signed_message(
                self.manifest(), session_id="b" * 32
            ),
            "topic body mismatch": self.signed_message(
                self.manifest(device_id="different-device")
            ),
            "malformed json": self.signed_message("{"),
            "unknown device": self.signed_message(
                self.manifest(device_id="unknown-device"),
                device_id="unknown-device",
            ),
            "unowned device": self.signed_message(
                self.manifest(device_id=self.unowned.device_id),
                device_id=self.unowned.device_id,
            ),
        }
        for name, message in cases.items():
            with self.subTest(name=name):
                hub = self.process(message)
                self.assertEqual(self.device.capabilities, original)
                hub.publish_from_thread.assert_not_called()

    def test_schema_rejections_and_supported_subset(self) -> None:
        invalid_manifests = []
        invalid_manifests.append(self.manifest(protocol_version=True))
        unsupported_type = self.manifest()
        unsupported_type["telemetry"]["temperature_c"]["type"] = "decimal"
        invalid_manifests.append(unsupported_type)

        bad_bounds = self.manifest(
            commands={
                "set_reporting_interval": {
                    "label": "Reporting interval",
                    "arguments": {
                        "interval_s": {
                            "type": "integer",
                            "label": "Interval",
                            "min": 60,
                            "max": 1,
                        }
                    },
                }
            }
        )
        invalid_manifests.append(bad_bounds)

        fractional_interval = self.manifest(
            commands={
                "set_reporting_interval": {
                    "label": "Reporting interval",
                    "arguments": {
                        "interval_s": {
                            "type": "number",
                            "label": "Interval",
                            "min": 1,
                            "max": 60,
                        }
                    },
                }
            }
        )
        invalid_manifests.append(fractional_interval)

        boolean_bounds = self.manifest()
        boolean_bounds["commands"]["set_led"]["arguments"]["on"]["min"] = 0
        invalid_manifests.append(boolean_bounds)

        invalid_manifests.append(
            self.manifest(
                commands={
                    "reboot": {"label": "Reboot", "arguments": {}}
                }
            )
        )
        invalid_manifests.append(
            self.manifest(
                commands={
                    "set_led": {
                        "label": "LED",
                        "arguments": {
                            "on": {"type": "string", "label": "On"}
                        },
                    }
                }
            )
        )
        invalid_manifests.append(
            self.manifest(
                telemetry={
                    "bad metric": {"type": "number", "label": "Bad"}
                }
            )
        )

        for manifest in invalid_manifests:
            with self.subTest(manifest=manifest):
                hub = self.process(self.signed_message(manifest))
                self.assertIsNone(self.device.capabilities)
                hub.publish_from_thread.assert_not_called()

        supported_subset = self.manifest(commands={})
        self.process(self.signed_message(supported_subset))
        self.assertIn("custom_voltage", self.device.capabilities["telemetry"])
        self.assertEqual(self.device.capabilities["commands"], {})

    def test_reporting_interval_requires_whole_seconds_from_one_to_sixty(self) -> None:
        for interval in (1, 2, 60):
            with self.subTest(interval=interval):
                command = CommandCreate(
                    type="set_reporting_interval",
                    arguments={"interval_s": interval},
                )
                self.assertEqual(command.arguments["interval_s"], interval)

        for interval in (0, 61, 2.5, True):
            with self.subTest(interval=interval), self.assertRaises(ValidationError):
                CommandCreate(
                    type="set_reporting_interval",
                    arguments={"interval_s": interval},
                )

    def test_oversized_manifest_is_rejected(self) -> None:
        telemetry = {
            f"metric_{index}": {
                "type": "number",
                "label": "L" * 80,
                "unit": "U" * 24,
            }
            for index in range(128)
        }
        manifest = self.manifest(telemetry=telemetry, commands={})
        self.assertGreater(len(json.dumps(manifest).encode()), 16_384)
        hub = self.process(self.signed_message(manifest))
        self.assertIsNone(self.device.capabilities)
        hub.publish_from_thread.assert_not_called()

    def test_new_online_session_accepts_current_and_rejects_stale_retained(self) -> None:
        new_session = "c" * 32
        status_topic = f"deviceops/v1/devices/{self.device.device_id}/status"
        online = create_authenticated_envelope(
            "online", self.key, "d2s", status_topic, new_session
        ).encode()
        self.process((status_topic, online))
        self.assertEqual(self.device.mqtt_session_id, new_session)
        self.assertEqual(self.device.status, "online")

        stale_hub = self.process(self.signed_message(self.manifest()))
        self.assertIsNone(self.device.capabilities)
        stale_hub.publish_from_thread.assert_not_called()

        current = self.signed_message(self.manifest(), session_id=new_session)
        self.process(current)
        self.assertEqual(self.device.capabilities["device_id"], self.device.device_id)


if __name__ == "__main__":
    unittest.main()
