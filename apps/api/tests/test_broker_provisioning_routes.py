"""Transactional registration/deletion tests for optional broker provisioning."""

from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from deviceops_api.broker_provisioning import (
    BrokerProvisioningError,
    BrokerProvisioningPartialFailure,
)
from deviceops_api.database import engine
from deviceops_api.device_credentials import (
    derive_broker_password_from_stored_hash,
    hash_device_secret,
)
from deviceops_api.models import Device, DeviceEvent, User
from deviceops_api.routes.devices import delete_device, register_device
from deviceops_api.schemas import DeviceRegistrationCreate


class RecordingProvisioner:
    def __init__(
        self,
        *,
        provision_error: BrokerProvisioningError | None = None,
        revoke_error: BrokerProvisioningError | None = None,
        revoke_result: bool = True,
    ) -> None:
        self.provision_error = provision_error
        self.revoke_error = revoke_error
        self.revoke_result = revoke_result
        self.provision_calls: list[tuple[str, str]] = []
        self.revoke_calls: list[str] = []
        self.on_revoke = None

    def provision_device(self, device_id: str, broker_password: str) -> None:
        self.provision_calls.append((device_id, broker_password))
        if self.provision_error is not None:
            raise self.provision_error

    def revoke_device(self, device_id: str) -> bool:
        self.revoke_calls.append(device_id)
        if self.on_revoke is not None:
            self.on_revoke(device_id)
        if self.revoke_error is not None:
            raise self.revoke_error
        return self.revoke_result


class BrokerProvisioningRouteTests(unittest.TestCase):
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
            email=f"broker-owner-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.other_user = User(
            email=f"broker-other-{suffix}@example.test",
            password_hash="test-only-unused",
        )
        self.session.add_all([self.owner, self.other_user])
        self.session.commit()
        self.suffix = suffix

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def _register(
        self,
        *,
        provisioner: RecordingProvisioner | None,
        device_id: str,
        device_secret: str,
    ):
        patches = (
            patch(
                "deviceops_api.routes.devices.broker_device_provisioner",
                provisioner,
            ),
            patch(
                "deviceops_api.routes.devices.generate_device_id",
                return_value=device_id,
            ),
            patch(
                "deviceops_api.routes.devices.generate_device_secret",
                return_value=device_secret,
            ),
            patch("deviceops_api.routes.devices.realtime_hub"),
        )
        return patches

    def _add_device(self, *, owner: User | None = None) -> Device:
        device = Device(
            device_id=f"dev-broker-route-{uuid4().hex[:10]}",
            owner_id=(owner or self.owner).id,
            device_secret_hash=hashlib.sha256(
                f"stored-key-{uuid4().hex}".encode()
            ).hexdigest(),
            status="unknown",
        )
        self.session.add(device)
        self.session.commit()
        return device

    def test_disabled_registration_preserves_existing_behavior(self) -> None:
        device_id = f"dev-disabled-{self.suffix}"
        device_secret = "test-registration-secret-disabled"
        provisioning_patch, id_patch, secret_patch, hub_patch = self._register(
            provisioner=None,
            device_id=device_id,
            device_secret=device_secret,
        )
        with provisioning_patch, id_patch, secret_patch, hub_patch as hub:
            result = register_device(
                DeviceRegistrationCreate(), self.session, self.owner
            )

        device = self.session.get(Device, device_id)
        self.assertIsNotNone(device)
        assert device is not None
        self.assertEqual(device.owner_id, self.owner.id)
        self.assertEqual(result.device_secret, device_secret)
        self.assertEqual(device.device_secret_hash, hash_device_secret(device_secret))
        self.assertNotEqual(device.device_secret_hash, device_secret)
        hub.publish_from_thread.assert_called_once()

    def test_enabled_registration_provisions_before_commit_and_returns_secret(self) -> None:
        provisioner = RecordingProvisioner()
        device_id = f"dev-enabled-{self.suffix}"
        device_secret = "test-registration-secret-enabled"
        provisioning_patch, id_patch, secret_patch, hub_patch = self._register(
            provisioner=provisioner,
            device_id=device_id,
            device_secret=device_secret,
        )
        with provisioning_patch, id_patch, secret_patch, hub_patch as hub:
            result = register_device(
                DeviceRegistrationCreate(), self.session, self.owner
            )

        stored_hash = hash_device_secret(device_secret)
        self.assertEqual(
            provisioner.provision_calls,
            [(device_id, derive_broker_password_from_stored_hash(stored_hash))],
        )
        device = self.session.get(Device, device_id)
        self.assertIsNotNone(device)
        assert device is not None
        self.assertEqual(device.owner_id, self.owner.id)
        self.assertEqual(device.device_secret_hash, stored_hash)
        self.assertEqual(result.device_secret, device_secret)
        hub.publish_from_thread.assert_called_once()

    def test_broker_failure_rolls_back_device_event_and_realtime(self) -> None:
        provisioner = RecordingProvisioner(
            provision_error=BrokerProvisioningError("safe test failure")
        )
        device_id = f"dev-broker-fail-{self.suffix}"
        device_secret = "test-registration-secret-broker-fail"
        provisioning_patch, id_patch, secret_patch, hub_patch = self._register(
            provisioner=provisioner,
            device_id=device_id,
            device_secret=device_secret,
        )
        with provisioning_patch, id_patch, secret_patch, hub_patch as hub:
            with self.assertRaises(HTTPException) as raised:
                register_device(
                    DeviceRegistrationCreate(), self.session, self.owner
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn(device_secret, str(raised.exception.detail))
        self.assertIsNone(self.session.get(Device, device_id))
        event_count = self.session.scalar(
            select(func.count()).select_from(DeviceEvent).where(
                DeviceEvent.device_id == device_id
            )
        )
        self.assertEqual(event_count, 0)
        hub.publish_from_thread.assert_not_called()

    def test_partial_provisioning_failure_is_surfaced_safely(self) -> None:
        provisioner = RecordingProvisioner(
            provision_error=BrokerProvisioningPartialFailure(
                "admin-test-password derived-test-password"
            )
        )
        device_id = f"dev-partial-fail-{self.suffix}"
        device_secret = "test-registration-secret-partial"
        provisioning_patch, id_patch, secret_patch, hub_patch = self._register(
            provisioner=provisioner,
            device_id=device_id,
            device_secret=device_secret,
        )
        with provisioning_patch, id_patch, secret_patch, hub_patch as hub:
            with (
                self.assertLogs(
                    "deviceops_api.routes.devices", level="CRITICAL"
                ) as captured_logs,
                self.assertRaises(HTTPException) as raised,
            ):
                register_device(
                    DeviceRegistrationCreate(), self.session, self.owner
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("cleanup failed", str(raised.exception.detail))
        self.assertNotIn(device_secret, str(raised.exception.detail))
        logged = " ".join(captured_logs.output)
        self.assertNotIn("admin-test-password", logged)
        self.assertNotIn("derived-test-password", logged)
        self.assertIsNone(self.session.get(Device, device_id))
        hub.publish_from_thread.assert_not_called()

    def test_registration_db_failure_revokes_and_rolls_back(self) -> None:
        provisioner = RecordingProvisioner()
        device_id = f"dev-db-fail-{self.suffix}"
        device_secret = "test-registration-secret-db-fail"
        provisioning_patch, id_patch, secret_patch, hub_patch = self._register(
            provisioner=provisioner,
            device_id=device_id,
            device_secret=device_secret,
        )
        with (
            provisioning_patch,
            id_patch,
            secret_patch,
            hub_patch as hub,
            patch.object(
                self.session,
                "commit",
                side_effect=SQLAlchemyError("test database failure"),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                register_device(DeviceRegistrationCreate(), self.session, self.owner)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(provisioner.revoke_calls, [device_id])
        self.assertIsNone(self.session.get(Device, device_id))
        hub.publish_from_thread.assert_not_called()

    def test_registration_db_and_cleanup_failure_is_safe(self) -> None:
        provisioner = RecordingProvisioner(
            revoke_error=BrokerProvisioningError(
                "admin-test-password derived-test-password"
            )
        )
        device_id = f"dev-db-cleanup-fail-{self.suffix}"
        device_secret = "test-registration-secret-db-cleanup-fail"
        provisioning_patch, id_patch, secret_patch, hub_patch = self._register(
            provisioner=provisioner,
            device_id=device_id,
            device_secret=device_secret,
        )
        with (
            provisioning_patch,
            id_patch,
            secret_patch,
            hub_patch as hub,
            patch.object(
                self.session,
                "commit",
                side_effect=SQLAlchemyError("test database failure"),
            ),
        ):
            with (
                self.assertLogs(
                    "deviceops_api.routes.devices", level="CRITICAL"
                ) as captured_logs,
                self.assertRaises(HTTPException) as raised,
            ):
                register_device(DeviceRegistrationCreate(), self.session, self.owner)

        detail = str(raised.exception.detail)
        self.assertIn("cleanup failed", detail)
        self.assertNotIn(device_secret, detail)
        self.assertNotIn("admin-test-password", detail)
        self.assertNotIn("derived-test-password", detail)
        logged = " ".join(captured_logs.output)
        self.assertNotIn(device_secret, logged)
        self.assertNotIn("admin-test-password", logged)
        self.assertNotIn("derived-test-password", logged)
        self.assertIsNone(self.session.get(Device, device_id))
        hub.publish_from_thread.assert_not_called()

    def test_disabled_deletion_preserves_existing_behavior(self) -> None:
        device = self._add_device()

        with patch(
            "deviceops_api.routes.devices.broker_device_provisioner", None
        ):
            response = delete_device(
                device.device_id, self.session, self.owner
            )

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.session.get(Device, device.device_id))

    def test_enabled_deletion_revokes_before_database_delete(self) -> None:
        device = self._add_device()
        provisioner = RecordingProvisioner()
        existed_during_revoke: list[bool] = []
        provisioner.on_revoke = lambda device_id: existed_during_revoke.append(
            self.session.get(Device, device_id) is not None
        )

        with patch(
            "deviceops_api.routes.devices.broker_device_provisioner",
            provisioner,
        ):
            response = delete_device(
                device.device_id, self.session, self.owner
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(provisioner.revoke_calls, [device.device_id])
        self.assertEqual(existed_during_revoke, [True])
        self.assertIsNone(self.session.get(Device, device.device_id))

    def test_legacy_deletion_continues_when_broker_identity_is_absent(self) -> None:
        device = self._add_device()
        provisioner = RecordingProvisioner(revoke_result=False)

        with patch(
            "deviceops_api.routes.devices.broker_device_provisioner",
            provisioner,
        ):
            response = delete_device(
                device.device_id, self.session, self.owner
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(provisioner.revoke_calls, [device.device_id])
        self.assertIsNone(self.session.get(Device, device.device_id))

    def test_revoke_failure_keeps_database_device(self) -> None:
        device = self._add_device()
        provisioner = RecordingProvisioner(
            revoke_error=BrokerProvisioningError("safe test failure")
        )

        with patch(
            "deviceops_api.routes.devices.broker_device_provisioner",
            provisioner,
        ):
            with self.assertRaises(HTTPException) as raised:
                delete_device(device.device_id, self.session, self.owner)

        self.assertEqual(raised.exception.status_code, 502)
        self.assertIsNotNone(self.session.get(Device, device.device_id))

    def test_deletion_db_failure_reprovisions_same_identity(self) -> None:
        device = self._add_device()
        stored_hash = device.device_secret_hash
        assert stored_hash is not None
        provisioner = RecordingProvisioner()

        with (
            patch(
                "deviceops_api.routes.devices.broker_device_provisioner",
                provisioner,
            ),
            patch.object(
                self.session,
                "commit",
                side_effect=SQLAlchemyError("test database failure"),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                delete_device(device.device_id, self.session, self.owner)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(provisioner.revoke_calls, [device.device_id])
        self.assertEqual(
            provisioner.provision_calls,
            [
                (
                    device.device_id,
                    derive_broker_password_from_stored_hash(stored_hash),
                )
            ],
        )
        self.assertIsNotNone(self.session.get(Device, device.device_id))

    def test_legacy_deletion_db_failure_does_not_create_broker_identity(
        self,
    ) -> None:
        device = self._add_device()
        provisioner = RecordingProvisioner(revoke_result=False)

        with (
            patch(
                "deviceops_api.routes.devices.broker_device_provisioner",
                provisioner,
            ),
            patch.object(
                self.session,
                "commit",
                side_effect=SQLAlchemyError("test database failure"),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                delete_device(device.device_id, self.session, self.owner)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(provisioner.revoke_calls, [device.device_id])
        self.assertEqual(provisioner.provision_calls, [])
        self.assertIsNotNone(self.session.get(Device, device.device_id))

    def test_deletion_db_and_restoration_failure_is_safe(self) -> None:
        device = self._add_device()
        provisioner = RecordingProvisioner(
            provision_error=BrokerProvisioningError(
                "admin-test-password derived-test-password"
            )
        )

        with (
            patch(
                "deviceops_api.routes.devices.broker_device_provisioner",
                provisioner,
            ),
            patch.object(
                self.session,
                "commit",
                side_effect=SQLAlchemyError("test database failure"),
            ),
        ):
            with (
                self.assertLogs(
                    "deviceops_api.routes.devices", level="CRITICAL"
                ) as captured_logs,
                self.assertRaises(HTTPException) as raised,
            ):
                delete_device(device.device_id, self.session, self.owner)

        detail = str(raised.exception.detail)
        self.assertIn("restoration failed", detail)
        self.assertNotIn("admin-test-password", detail)
        self.assertNotIn("derived-test-password", detail)
        logged = " ".join(captured_logs.output)
        self.assertNotIn("admin-test-password", logged)
        self.assertNotIn("derived-test-password", logged)
        self.assertIsNotNone(self.session.get(Device, device.device_id))

    def test_enabled_deletion_preserves_privacy_scoped_lookup(self) -> None:
        other_device = self._add_device(owner=self.other_user)
        provisioner = RecordingProvisioner()

        with patch(
            "deviceops_api.routes.devices.broker_device_provisioner",
            provisioner,
        ):
            for device_id in (other_device.device_id, "missing-device"):
                with self.subTest(device_id=device_id):
                    with self.assertRaises(HTTPException) as raised:
                        delete_device(device_id, self.session, self.owner)
                    self.assertEqual(raised.exception.status_code, 404)

        self.assertEqual(provisioner.revoke_calls, [])
        self.assertIsNotNone(
            self.session.get(Device, other_device.device_id)
        )


if __name__ == "__main__":
    unittest.main()
