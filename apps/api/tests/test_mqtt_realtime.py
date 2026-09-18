"""MQTT-to-realtime routing tests with no broker or database connection."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SQLAlchemyError

from deviceops_api.models import Device, DeviceCommand, DeviceEvent, Telemetry
from deviceops_api.mqtt import MqttIngestor
from deviceops_api.mqtt_auth import create_authenticated_envelope


class MqttRealtimeTests(unittest.TestCase):
    def setUp(self):
        self.ingestor = MqttIngestor()  # Does not connect until start().
        self.now = datetime.now(timezone.utc)
        self.key = hashlib.sha256(b"mqtt-routing-test-only").digest()
        self.device = SimpleNamespace(
            device_id="dev-routing-test",
            owner_id=42,
            device_secret_hash=self.key.hex(),
            mqtt_session_id="0" * 32,
            first_seen_at=self.now,
            last_seen_at=self.now,
            status="online",
        )
        self.command = SimpleNamespace(
            command_id="246efa2b-798e-4c53-a53e-fe1853090044",
            device_id=self.device.device_id,
            status="pending",
            command_type="set_led",
            arguments={"on": True},
            issued_at=self.now,
        )
        self.session = MagicMock()
        self.session.get.side_effect = self.get_row
        self.session.flush.side_effect = self.assign_database_ids
        self.committed = False

    def get_row(self, model, identifier):
        if model is Device and identifier == self.device.device_id:
            return self.device
        if model is DeviceCommand and identifier == self.command.command_id:
            return self.command
        return None

    def assign_database_ids(self, objects=None):
        rows = objects or [self.session.add.call_args.args[0]]
        for row in rows:
            if isinstance(row, Telemetry):
                row.id = 101
            elif isinstance(row, DeviceEvent):
                row.id = 202

    @contextmanager
    def transaction(self, fail_commit=False):
        self.committed = False
        yield self.session
        if fail_commit:
            raise SQLAlchemyError("test commit failure")
        self.committed = True

    def signed_message(self, kind, *, wrong_session=False, bad_signature=False):
        topic = f"deviceops/v1/devices/{self.device.device_id}/{kind}"
        timestamp = self.now.isoformat()
        if kind == "telemetry":
            body = json.dumps({
                "protocol_version": 1,
                "device_id": self.device.device_id,
                "sent_at": timestamp,
                "sequence": 1,
                "metrics": {"temperature_c": 23, "rssi_dbm": -50, "uptime_s": 1},
            })
        elif kind == "status":
            body = "offline"  # Requires matching established session.
        else:
            body = json.dumps({
                "protocol_version": 1,
                "command_id": self.command.command_id,
                "device_id": self.device.device_id,
                "sent_at": timestamp,
                "status": "succeeded",
                "result": {"on": True},
            })
        envelope = create_authenticated_envelope(
            body,
            b"wrong-key" if bad_signature else self.key,
            "d2s",
            topic,
            "1" * 32 if wrong_session else self.device.mqtt_session_id,
        )
        return topic, envelope.encode()

    def test_all_event_kinds_route_by_existing_device_owner_after_commit(self):
        for kind, event_type in (
            ("telemetry", "telemetry"),
            ("status", "device_status"),
            ("command-acks", "command_update"),
        ):
            with self.subTest(kind=kind):
                self.session.reset_mock()

                publications = []

                def check_publication(owner_id, event):
                    self.assertTrue(self.committed)
                    self.assertEqual(owner_id, self.device.owner_id)
                    self.assertNotIn("owner_id", json.dumps(event))
                    publications.append(event)

                with (
                    patch("deviceops_api.mqtt.SessionLocal") as factory,
                    patch("deviceops_api.mqtt.realtime_hub") as hub,
                ):
                    factory.begin.return_value = self.transaction()
                    hub.publish_from_thread.side_effect = check_publication
                    self.ingestor._process_message(*self.signed_message(kind))
                    self.assertEqual(publications[0]["type"], event_type)
                    self.assertEqual(
                        publications[0]["device_id"], self.device.device_id
                    )
                    self.assertEqual(
                        set(publications[0]),
                        {"type", "device_id", "received_at", "data"},
                    )
                    if kind == "telemetry":
                        self.assertEqual(len(publications), 1)
                    else:
                        self.assertEqual(len(publications), 2)
                        self.assertEqual(publications[1]["type"], "event_created")
                        self.assertEqual(
                            publications[1]["data"]["device_id"],
                            self.device.device_id,
                        )
                    device_lookups = [
                        call for call in self.session.get.call_args_list
                        if call.args[0] is Device
                    ]
                    self.assertEqual(len(device_lookups), 1)

    def test_unowned_bad_signature_and_stale_session_never_publish(self):
        for kind in ("telemetry", "status", "command-acks"):
            for rejection in ("unowned", "bad_signature", "wrong_session"):
                with self.subTest(kind=kind, rejection=rejection):
                    self.device.owner_id = None if rejection == "unowned" else 42
                    with (
                        patch("deviceops_api.mqtt.SessionLocal") as factory,
                        patch("deviceops_api.mqtt.realtime_hub") as hub,
                    ):
                        factory.begin.return_value = self.transaction()
                        self.ingestor._process_message(*self.signed_message(
                            kind,
                            bad_signature=rejection == "bad_signature",
                            wrong_session=rejection == "wrong_session",
                        ))
                        hub.publish_from_thread.assert_not_called()

    def test_failed_commit_never_publishes(self):
        for kind in ("telemetry", "status", "command-acks"):
            with self.subTest(kind=kind):
                with (
                    patch("deviceops_api.mqtt.SessionLocal") as factory,
                    patch("deviceops_api.mqtt.realtime_hub") as hub,
                    self.assertLogs("deviceops_api.mqtt", level="ERROR"),
                ):
                    factory.begin.return_value = self.transaction(fail_commit=True)
                    self.ingestor._process_message(*self.signed_message(kind))
                    hub.publish_from_thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
