"""Mosquitto Dynamic Security provisioning over its MQTT control API."""

from __future__ import annotations

from collections.abc import Callable
import json
import time
from typing import Any, Protocol
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt import MQTTException

from .config import Settings, settings


DYNAMIC_SECURITY_REQUEST_TOPIC = "$CONTROL/dynamic-security/v1"
DYNAMIC_SECURITY_RESPONSE_TOPIC = "$CONTROL/dynamic-security/v1/response"
DEVICE_ROLE = "deviceops-device-v1"
DEVICE_ROLE_PRIORITY = 10


class BrokerProvisioningError(RuntimeError):
    """A safe broker provisioning failure suitable for route translation."""


class BrokerProvisioningConfigurationError(BrokerProvisioningError):
    """Broker provisioning was enabled without usable configuration."""


class BrokerProvisioningPartialFailure(BrokerProvisioningError):
    """A primary provisioning operation and its compensation both failed."""


class BrokerClientNotFoundError(BrokerProvisioningError):
    """The requested broker client was already absent."""


class DynamicSecurityTransport(Protocol):
    def execute(self, command: dict[str, object]) -> None: ...


class PahoDynamicSecurityTransport:
    """Execute one Dynamic Security command and wait for its correlated response."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        tls: bool,
        timeout_seconds: float,
        client_factory: Callable[..., mqtt.Client] | None = None,
    ) -> None:
        if not host or not username or not password:
            raise BrokerProvisioningConfigurationError(
                "Broker provisioning host and credentials are required"
            )
        if port < 1 or timeout_seconds <= 0:
            raise BrokerProvisioningConfigurationError(
                "Broker provisioning port and timeout must be positive"
            )
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._tls = tls
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory or mqtt.Client

    def execute(self, command: dict[str, object]) -> None:
        command_name = command.get("command")
        if not isinstance(command_name, str) or not command_name:
            raise BrokerProvisioningError(
                "Dynamic Security command name is required"
            )

        correlation_data = uuid4().hex
        correlated_command = dict(command)
        correlated_command["correlationData"] = correlation_data
        payload = json.dumps(
            {"commands": [correlated_command]}, separators=(",", ":")
        )

        try:
            client = self._client_factory(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"deviceops-provisioning-{uuid4().hex}",
                protocol=mqtt.MQTTv5,
                reconnect_on_failure=False,
            )
            client.connect_timeout = self._timeout_seconds
            client.username_pw_set(self._username, self._password)
            if self._tls:
                client.tls_set()
                client.tls_insecure_set(False)
        except (OSError, RuntimeError, ValueError, MQTTException) as exc:
            raise BrokerProvisioningError(
                "Broker provisioning client setup failed"
            ) from exc

        state: dict[str, Any] = {
            "ready": False,
            "failure": None,
            "responses": [],
            "closing": False,
        }

        def on_connect(
            callback_client: mqtt.Client,
            _userdata: object,
            _flags: object,
            reason_code: object,
            _properties: object,
        ) -> None:
            if reason_code != 0:
                state["failure"] = "Broker provisioning connection was rejected"
                return
            result, _message_id = callback_client.subscribe(
                DYNAMIC_SECURITY_RESPONSE_TOPIC, qos=1
            )
            if result != mqtt.MQTT_ERR_SUCCESS:
                state["failure"] = "Dynamic Security response subscription failed"

        def on_subscribe(
            _callback_client: mqtt.Client,
            _userdata: object,
            _message_id: int,
            reason_codes: list[object],
            _properties: object,
        ) -> None:
            if any(
                getattr(reason_code, "is_failure", False)
                or (isinstance(reason_code, int) and reason_code >= 128)
                for reason_code in reason_codes
            ):
                state["failure"] = "Dynamic Security response subscription was rejected"
                return
            state["ready"] = True

        def on_message(
            _callback_client: mqtt.Client,
            _userdata: object,
            message: mqtt.MQTTMessage,
        ) -> None:
            if message.topic == DYNAMIC_SECURITY_RESPONSE_TOPIC:
                state["responses"].append(message.payload)

        def on_disconnect(
            _callback_client: mqtt.Client,
            _userdata: object,
            _disconnect_flags: object,
            _reason_code: object,
            _properties: object,
        ) -> None:
            if not state["closing"]:
                state["failure"] = "Broker provisioning connection was lost"

        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.on_disconnect = on_disconnect

        connected = False
        try:
            try:
                connect_result = client.connect(
                    self._host, self._port, keepalive=30
                )
            except (OSError, MQTTException) as exc:
                raise BrokerProvisioningError(
                    "Broker provisioning connection failed"
                ) from exc
            if connect_result != mqtt.MQTT_ERR_SUCCESS:
                raise BrokerProvisioningError(
                    "Broker provisioning connection failed"
                )
            connected = True

            self._wait_until_ready(client, state)
            message_info = client.publish(
                DYNAMIC_SECURITY_REQUEST_TOPIC,
                payload=payload,
                qos=1,
                retain=False,
            )
            if message_info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise BrokerProvisioningError(
                    f"Dynamic Security command {command_name} could not be published"
                )
            self._wait_for_response(
                client,
                state,
                command_name=command_name,
                correlation_data=correlation_data,
            )
        except BrokerProvisioningError:
            raise
        except (OSError, RuntimeError, ValueError, MQTTException) as exc:
            raise BrokerProvisioningError(
                f"Dynamic Security command {command_name} failed"
            ) from exc
        finally:
            state["closing"] = True
            if connected:
                try:
                    client.disconnect()
                    client.loop(timeout=0.1)
                except (OSError, RuntimeError, MQTTException):
                    pass

    def _wait_until_ready(
        self, client: mqtt.Client, state: dict[str, Any]
    ) -> None:
        deadline = time.monotonic() + self._timeout_seconds
        while not state["ready"]:
            self._raise_state_failure(state)
            self._loop_once(client, deadline)
        self._raise_state_failure(state)

    def _wait_for_response(
        self,
        client: mqtt.Client,
        state: dict[str, Any],
        *,
        command_name: str,
        correlation_data: str,
    ) -> None:
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            self._raise_state_failure(state)
            while state["responses"]:
                payload = state["responses"].pop(0)
                if self._validate_response(
                    payload,
                    command_name=command_name,
                    correlation_data=correlation_data,
                ):
                    return
            self._loop_once(client, deadline)

    @staticmethod
    def _raise_state_failure(state: dict[str, Any]) -> None:
        failure = state["failure"]
        if failure is not None:
            raise BrokerProvisioningError(failure)

    @staticmethod
    def _loop_once(client: mqtt.Client, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BrokerProvisioningError(
                "Timed out waiting for Dynamic Security response"
            )
        result = client.loop(timeout=min(0.1, remaining))
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise BrokerProvisioningError(
                "Broker provisioning MQTT transport failed"
            )

    @staticmethod
    def _validate_response(
        payload: bytes,
        *,
        command_name: str,
        correlation_data: str,
    ) -> bool:
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrokerProvisioningError(
                "Malformed Dynamic Security response"
            ) from exc
        if not isinstance(document, dict):
            raise BrokerProvisioningError("Malformed Dynamic Security response")
        responses = document.get("responses")
        if not isinstance(responses, list) or not responses:
            raise BrokerProvisioningError("Malformed Dynamic Security response")

        for response in responses:
            if not isinstance(response, dict):
                raise BrokerProvisioningError(
                    "Malformed Dynamic Security response"
                )
            if response.get("correlationData") != correlation_data:
                continue
            if response.get("command") != command_name:
                raise BrokerProvisioningError(
                    "Unexpected Dynamic Security response"
                )
            if (
                command_name == "deleteClient"
                and response.get("error") == "Client not found"
            ):
                raise BrokerClientNotFoundError(
                    "Broker client is already absent"
                )
            if "error" in response:
                raise BrokerProvisioningError(
                    f"Dynamic Security command {command_name} was rejected"
                )
            return True
        return False


class BrokerDeviceProvisioner:
    """Provision and revoke the one broker identity belonging to a device."""

    def __init__(self, transport: DynamicSecurityTransport) -> None:
        self._transport = transport

    def provision_device(self, device_id: str, broker_password: str) -> None:
        self._transport.execute(
            {
                "command": "createClient",
                "username": device_id,
                "password": broker_password,
                "clientid": device_id,
                "roles": [
                    {
                        "rolename": DEVICE_ROLE,
                        "priority": DEVICE_ROLE_PRIORITY,
                    }
                ],
            }
        )

    def revoke_device(self, device_id: str) -> bool:
        """Return whether a broker identity existed and was removed."""
        try:
            self._transport.execute(
                {"command": "deleteClient", "username": device_id}
            )
        except BrokerClientNotFoundError:
            return False
        return True


def build_broker_device_provisioner(
    configured: Settings,
) -> BrokerDeviceProvisioner | None:
    if not configured.broker_provisioning_enabled:
        return None
    if (
        configured.broker_provisioning_host is None
        or configured.broker_provisioning_username is None
        or configured.broker_provisioning_password is None
    ):
        raise BrokerProvisioningConfigurationError(
            "Broker provisioning configuration is incomplete"
        )
    return BrokerDeviceProvisioner(
        PahoDynamicSecurityTransport(
            host=configured.broker_provisioning_host,
            port=configured.broker_provisioning_port,
            username=configured.broker_provisioning_username,
            password=configured.broker_provisioning_password,
            tls=configured.broker_provisioning_tls,
            timeout_seconds=configured.broker_provisioning_timeout_seconds,
        )
    )


broker_device_provisioner = build_broker_device_provisioner(settings)
