"""Focused persistence, isolation, and idempotency tests for fleet events."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deviceops_api.database import engine
from deviceops_api.events import create_device_event
from deviceops_api.models import Device, DeviceCommand, DeviceEvent, User
from deviceops_api.mqtt import MqttIngestor
from deviceops_api.mqtt_auth import create_authenticated_envelope
from deviceops_api.routes.commands import create_device_command
from deviceops_api.routes.devices import register_device
from deviceops_api.routes.events import list_events
from deviceops_api.schemas import CommandCreate, DeviceEventRead, DeviceRegistrationCreate


class EventPersistenceTests(unittest.TestCase):
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
            email=f"events-owner-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.other_user = User(
            email=f"events-other-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.session.add_all([self.owner, self.other_user])
        self.session.flush()

        self.signing_key = hashlib.sha256(b"events-test-only-key").digest()
        self.session_id = "a" * 32
        self.device = Device(
            device_id=f"dev-events-owner-{suffix}",
            owner_id=self.owner.id,
            device_secret_hash=self.signing_key.hex(),
            mqtt_session_id=self.session_id,
            status="unknown",
        )
        self.other_device = Device(
            device_id=f"dev-events-other-{suffix}",
            owner_id=self.other_user.id,
            device_secret_hash=hashlib.sha256(b"other-test-key").hexdigest(),
            status="unknown",
        )
        self.session.add_all([self.device, self.other_device])
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def _list_events(
        self,
        user: User,
        *,
        device_id: str | None = None,
        event_type=None,
        severity=None,
    ) -> list[DeviceEvent]:
        return list_events(
            session=self.session,
            current_user=user,
            limit=100,
            device_id=device_id,
            event_type=event_type,
            severity=severity,
        )

    def _event_count(self, event_type: str, device_id: str | None = None) -> int:
        statement = select(func.count()).select_from(DeviceEvent).where(
            DeviceEvent.event_type == event_type
        )
        if device_id is not None:
            statement = statement.where(DeviceEvent.device_id == device_id)
        count = self.session.scalar(statement) or 0
        self.session.commit()
        return count

    def _signed_message(
        self,
        kind: str,
        body: str,
        *,
        session_id: str | None = None,
    ) -> tuple[str, bytes]:
        topic = f"deviceops/v1/devices/{self.device.device_id}/{kind}"
        envelope = create_authenticated_envelope(
            body,
            self.signing_key,
            "d2s",
            topic,
            session_id or self.session_id,
        )
        return topic, envelope.encode()

    def _process_message(self, topic: str, payload: bytes) -> None:
        ingestor = MqttIngestor()
        with patch("deviceops_api.mqtt.SessionLocal") as session_factory:
            session_factory.begin.side_effect = self._mqtt_transaction
            ingestor._process_message(topic, payload)

    @contextmanager
    def _mqtt_transaction(self):
        with self.session.begin():
            yield self.session

    def test_owner_feed_is_isolated_filterable_and_hides_owner_id(self) -> None:
        now = datetime.now(timezone.utc)
        own_event = create_device_event(
            self.session,
            owner_id=self.owner.id,
            device_id=self.device.device_id,
            event_type="device_registered",
            occurred_at=now,
        )
        create_device_event(
            self.session,
            owner_id=self.other_user.id,
            device_id=self.other_device.device_id,
            event_type="device_online",
            occurred_at=now,
        )
        self.session.commit()

        owner_events = self._list_events(self.owner)
        other_events = self._list_events(self.other_user)
        self.assertEqual([event.id for event in owner_events], [own_event.id])
        self.assertEqual(len(other_events), 1)
        self.assertEqual(other_events[0].device_id, self.other_device.device_id)
        public_event = DeviceEventRead.model_validate(owner_events[0]).model_dump()
        self.assertNotIn("owner_id", public_event)
        self.assertEqual(
            self._list_events(self.owner, event_type="device_registered"),
            owner_events,
        )
        self.assertEqual(
            self._list_events(self.owner, severity="info"), owner_events
        )

    def test_unowned_device_filter_returns_not_found(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            self._list_events(self.owner, device_id=self.other_device.device_id)
        self.assertEqual(raised.exception.status_code, 404)

    def test_registration_creates_exactly_one_event(self) -> None:
        device_id = f"dev-events-created-{uuid4().hex[:10]}"
        with (
            patch(
                "deviceops_api.routes.devices.generate_device_id",
                return_value=device_id,
            ),
            patch(
                "deviceops_api.routes.devices.generate_device_secret",
                return_value="test-registration-secret",
            ),
            patch("deviceops_api.routes.devices.realtime_hub") as hub,
        ):
            register_device(
                DeviceRegistrationCreate(), self.session, self.owner
            )

        events = self.session.scalars(
            select(DeviceEvent).where(DeviceEvent.device_id == device_id)
        ).all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "device_registered")
        hub.publish_from_thread.assert_called_once()
        self.assertNotIn("owner_id", json.dumps(hub.publish_from_thread.call_args.args[1]))

    def test_status_events_only_record_effective_transitions(self) -> None:
        online = self._signed_message("status", "online")
        self._process_message(*online)
        self._process_message(*online)
        self.assertEqual(
            self._event_count("device_online", self.device.device_id), 1
        )

        offline = self._signed_message("status", "offline")
        self._process_message(*offline)
        self.session.refresh(self.device)
        first_offline_since = self.device.offline_since
        self.assertIsNotNone(first_offline_since)
        self.session.commit()
        self._process_message(*offline)
        self.session.refresh(self.device)
        self.assertEqual(self.device.offline_since, first_offline_since)
        self.session.commit()
        self.assertEqual(
            self._event_count("device_offline", self.device.device_id), 1
        )

        self.session.commit()
        self._process_message(*online)
        self.session.refresh(self.device)
        self.assertIsNone(self.device.offline_since)

    def test_command_creation_and_first_ack_are_each_recorded_once(self) -> None:
        with (
            patch("deviceops_api.routes.commands.mqtt_ingestor") as mqtt,
            patch("deviceops_api.routes.commands.realtime_hub"),
        ):
            command = create_device_command(
                self.device.device_id,
                CommandCreate(type="set_led", arguments={"on": True}),
                self.session,
                self.owner,
            )
        mqtt.publish_command.assert_called_once_with(command)
        self.assertEqual(
            self._event_count("command_issued", self.device.device_id), 1
        )

        ack_body = json.dumps(
            {
                "protocol_version": 1,
                "command_id": command.command_id,
                "device_id": self.device.device_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "status": "succeeded",
                "result": {"on": True},
            }
        )
        acknowledgement = self._signed_message("command-acks", ack_body)
        self._process_message(*acknowledgement)
        self._process_message(*acknowledgement)
        self.assertEqual(
            self._event_count("command_succeeded", self.device.device_id), 1
        )

        failed_command = DeviceCommand(
            command_id=str(uuid4()),
            device_id=self.device.device_id,
            command_type="request_diagnostics",
            arguments={},
            status="pending",
            issued_at=datetime.now(timezone.utc),
        )
        self.session.add(failed_command)
        self.session.commit()
        failed_body = json.dumps(
            {
                "protocol_version": 1,
                "command_id": failed_command.command_id,
                "device_id": self.device.device_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "result": {"error": "test-only failure"},
            }
        )
        failed_ack = self._signed_message("command-acks", failed_body)
        self._process_message(*failed_ack)
        self._process_message(*failed_ack)
        self.assertEqual(
            self._event_count("command_failed", self.device.device_id), 1
        )


if __name__ == "__main__":
    unittest.main()
