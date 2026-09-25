"""Mosquitto Dynamic Security provisioning and transport tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Callable
import unittest

import paho.mqtt.client as mqtt

from deviceops_api.broker_provisioning import (
    DEVICE_ROLE,
    DEVICE_ROLE_PRIORITY,
    DYNAMIC_SECURITY_REQUEST_TOPIC,
    DYNAMIC_SECURITY_RESPONSE_TOPIC,
    BrokerDeviceProvisioner,
    BrokerProvisioningError,
    PahoDynamicSecurityTransport,
)


class RecordingTransport:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.commands: list[dict[str, object]] = []
        self.failures = failures or set()

    def execute(self, command: dict[str, object]) -> None:
        self.commands.append(command)
        if command["command"] in self.failures:
            raise BrokerProvisioningError("safe test failure")


class FakeMessageInfo:
    rc = mqtt.MQTT_ERR_SUCCESS


class FakePahoClient:
    def __init__(
        self,
        response_builder: Callable[[dict[str, object]], bytes | None],
        **constructor_arguments: object,
    ) -> None:
        self.response_builder = response_builder
        self.constructor_arguments = constructor_arguments
        self.connect_timeout: float | None = None
        self.username_password: tuple[str, str] | None = None
        self.tls_set_called = False
        self.tls_insecure_values: list[bool] = []
        self.subscription: tuple[str, int] | None = None
        self.published: tuple[str, str, int, bool] | None = None
        self.on_connect = None
        self.on_subscribe = None
        self.on_message = None
        self.on_disconnect = None
        self._connect_callback_sent = False
        self._subscribe_callback_sent = False
        self._response_sent = False

    def username_pw_set(self, username: str, password: str) -> None:
        self.username_password = (username, password)

    def tls_set(self) -> None:
        self.tls_set_called = True

    def tls_insecure_set(self, value: bool) -> None:
        self.tls_insecure_values.append(value)

    def connect(self, host: str, port: int, keepalive: int) -> int:
        self.connection = (host, port, keepalive)
        return mqtt.MQTT_ERR_SUCCESS

    def subscribe(self, topic: str, qos: int) -> tuple[int, int]:
        self.subscription = (topic, qos)
        return mqtt.MQTT_ERR_SUCCESS, 1

    def publish(
        self, topic: str, payload: str, qos: int, retain: bool
    ) -> FakeMessageInfo:
        self.published = (topic, payload, qos, retain)
        return FakeMessageInfo()

    def loop(self, timeout: float) -> int:
        if not self._connect_callback_sent:
            self._connect_callback_sent = True
            assert self.on_connect is not None
            self.on_connect(self, None, None, 0, None)
        elif self.subscription is not None and not self._subscribe_callback_sent:
            self._subscribe_callback_sent = True
            assert self.on_subscribe is not None
            self.on_subscribe(self, None, 1, [0], None)
        elif self.published is not None and not self._response_sent:
            self._response_sent = True
            request = json.loads(self.published[1])
            response = self.response_builder(request)
            if response is not None:
                assert self.on_message is not None
                self.on_message(
                    self,
                    None,
                    SimpleNamespace(
                        topic=DYNAMIC_SECURITY_RESPONSE_TOPIC,
                        payload=response,
                    ),
                )
        return mqtt.MQTT_ERR_SUCCESS

    def disconnect(self) -> int:
        if self.on_disconnect is not None:
            self.on_disconnect(self, None, None, 0, None)
        return mqtt.MQTT_ERR_SUCCESS


def successful_response(request: dict[str, object]) -> bytes:
    command = request["commands"][0]  # type: ignore[index]
    return json.dumps(
        {
            "responses": [
                {
                    "command": command["command"],
                    "correlationData": command["correlationData"],
                }
            ]
        }
    ).encode()


class BrokerDeviceProvisionerTests(unittest.TestCase):
    def test_provision_atomically_creates_bound_client_with_existing_role(
        self,
    ) -> None:
        transport = RecordingTransport()
        provisioner = BrokerDeviceProvisioner(transport)

        provisioner.provision_device("dev-test", "derived-test-password")

        self.assertEqual(
            transport.commands,
            [
                {
                    "command": "createClient",
                    "username": "dev-test",
                    "password": "derived-test-password",
                    "clientid": "dev-test",
                    "roles": [
                        {
                            "rolename": DEVICE_ROLE,
                            "priority": DEVICE_ROLE_PRIORITY,
                        }
                    ],
                },
            ],
        )

    def test_atomic_create_failure_does_not_issue_a_second_command(self) -> None:
        transport = RecordingTransport({"createClient"})
        provisioner = BrokerDeviceProvisioner(transport)

        with self.assertRaises(BrokerProvisioningError):
            provisioner.provision_device("dev-test", "derived-test-password")

        self.assertEqual(
            [command["command"] for command in transport.commands],
            ["createClient"],
        )

    def test_revoke_uses_delete_client(self) -> None:
        transport = RecordingTransport()
        provisioner = BrokerDeviceProvisioner(transport)

        provisioner.revoke_device("dev-test")

        self.assertEqual(
            transport.commands,
            [{"command": "deleteClient", "username": "dev-test"}],
        )


class PahoDynamicSecurityTransportTests(unittest.TestCase):
    def _transport(
        self,
        response_builder: Callable[[dict[str, object]], bytes | None],
        *,
        timeout: float = 0.02,
    ) -> tuple[PahoDynamicSecurityTransport, list[FakePahoClient]]:
        clients: list[FakePahoClient] = []

        def factory(**arguments: object) -> FakePahoClient:
            client = FakePahoClient(response_builder, **arguments)
            clients.append(client)
            return client

        return (
            PahoDynamicSecurityTransport(
                host="broker.example.test",
                port=443,
                username="test-admin",
                password="admin-test-password",
                tls=True,
                timeout_seconds=timeout,
                client_factory=factory,  # type: ignore[arg-type]
            ),
            clients,
        )

    def test_qos_one_topics_tls_and_matching_correlation(self) -> None:
        transport, clients = self._transport(successful_response)

        transport.execute({"command": "deleteClient", "username": "dev-test"})

        client = clients[0]
        self.assertEqual(
            client.subscription, (DYNAMIC_SECURITY_RESPONSE_TOPIC, 1)
        )
        assert client.published is not None
        topic, payload, qos, retain = client.published
        self.assertEqual(topic, DYNAMIC_SECURITY_REQUEST_TOPIC)
        self.assertEqual(qos, 1)
        self.assertFalse(retain)
        command = json.loads(payload)["commands"][0]
        self.assertEqual(command["command"], "deleteClient")
        self.assertRegex(command["correlationData"], r"^[0-9a-f]{32}$")
        self.assertEqual(
            client.username_password, ("test-admin", "admin-test-password")
        )
        self.assertTrue(client.tls_set_called)
        self.assertEqual(client.tls_insecure_values, [False])

    def test_dynamic_security_error_is_safe_failure(self) -> None:
        def error_response(request: dict[str, object]) -> bytes:
            command = request["commands"][0]  # type: ignore[index]
            return json.dumps(
                {
                    "responses": [
                        {
                            "command": command["command"],
                            "correlationData": command["correlationData"],
                            "error": "server detail that is not propagated",
                        }
                    ]
                }
            ).encode()

        transport, _clients = self._transport(error_response)
        with self.assertRaises(BrokerProvisioningError) as raised:
            transport.execute(
                {
                    "command": "createClient",
                    "username": "dev-test",
                    "password": "derived-test-password",
                }
            )

        message = str(raised.exception)
        self.assertNotIn("derived-test-password", message)
        self.assertNotIn("admin-test-password", message)
        self.assertNotIn("server detail", message)

    def test_malformed_response_fails(self) -> None:
        transport, _clients = self._transport(lambda _request: b"not-json")

        with self.assertRaisesRegex(
            BrokerProvisioningError, "Malformed Dynamic Security response"
        ):
            transport.execute({"command": "deleteClient", "username": "dev-test"})

    def test_mismatched_correlation_is_not_accepted_and_times_out(self) -> None:
        def mismatched_response(request: dict[str, object]) -> bytes:
            command = request["commands"][0]  # type: ignore[index]
            return json.dumps(
                {
                    "responses": [
                        {
                            "command": command["command"],
                            "correlationData": "different-request",
                        }
                    ]
                }
            ).encode()

        transport, _clients = self._transport(mismatched_response, timeout=0.002)

        with self.assertRaisesRegex(BrokerProvisioningError, "Timed out"):
            transport.execute({"command": "deleteClient", "username": "dev-test"})

    def test_matching_correlation_with_wrong_command_fails(self) -> None:
        def unexpected_response(request: dict[str, object]) -> bytes:
            command = request["commands"][0]  # type: ignore[index]
            return json.dumps(
                {
                    "responses": [
                        {
                            "command": "createRole",
                            "correlationData": command["correlationData"],
                        }
                    ]
                }
            ).encode()

        transport, _clients = self._transport(unexpected_response)

        with self.assertRaisesRegex(
            BrokerProvisioningError, "Unexpected Dynamic Security response"
        ):
            transport.execute({"command": "deleteClient", "username": "dev-test"})

    def test_missing_response_times_out(self) -> None:
        transport, _clients = self._transport(
            lambda _request: None, timeout=0.002
        )

        with self.assertRaisesRegex(BrokerProvisioningError, "Timed out"):
            transport.execute({"command": "deleteClient", "username": "dev-test"})

    def test_client_setup_failure_is_wrapped_without_credentials(self) -> None:
        def failing_factory(**_arguments: object) -> FakePahoClient:
            raise OSError("admin-test-password")

        transport = PahoDynamicSecurityTransport(
            host="broker.example.test",
            port=443,
            username="test-admin",
            password="admin-test-password",
            tls=True,
            timeout_seconds=1,
            client_factory=failing_factory,  # type: ignore[arg-type]
        )

        with self.assertRaises(BrokerProvisioningError) as raised:
            transport.execute({"command": "deleteClient", "username": "dev-test"})

        self.assertNotIn("admin-test-password", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
