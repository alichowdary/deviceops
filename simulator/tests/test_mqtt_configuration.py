"""Focused simulator hosted, local, and custom MQTT configuration tests."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import hmac
from io import StringIO
import os
import unittest
from unittest.mock import MagicMock, patch

import paho.mqtt.client as mqtt

from device_simulator.main import (
    HOSTED_BROKER_HOST,
    HOSTED_BROKER_PORT,
    broker_credentials_from_environment,
    configure_mqtt_transport,
    parse_args,
    resolve_broker_configuration,
    run,
    telemetry_publish_completed,
)
from device_simulator.mqtt_auth import derive_broker_password


class SimulatorMqttConfigurationTests(unittest.TestCase):
    def test_hosted_mode_is_default_and_uses_device_identity(self) -> None:
        secret = "hosted-device-secret"
        with patch.dict(os.environ, {}, clear=True):
            configured = resolve_broker_configuration(
                parse_args(["--device-id", "dev-hosted"]), secret
            )

        self.assertEqual(configured.host, HOSTED_BROKER_HOST)
        self.assertEqual(configured.port, HOSTED_BROKER_PORT)
        self.assertTrue(configured.tls)
        self.assertEqual(configured.username, "dev-hosted")
        self.assertEqual(configured.password, derive_broker_password(secret))

    def test_broker_password_uses_raw_signing_key_and_domain_separation(self) -> None:
        secret = "known-device-secret"
        raw_signing_key = hashlib.sha256(secret.encode("utf-8")).digest()
        expected = hmac.new(
            raw_signing_key,
            b"deviceops-broker-auth-v1",
            hashlib.sha256,
        ).hexdigest()
        wrong_hex_text_result = hmac.new(
            hashlib.sha256(secret.encode("utf-8")).hexdigest().encode("ascii"),
            b"deviceops-broker-auth-v1",
            hashlib.sha256,
        ).hexdigest()

        derived = derive_broker_password(secret)

        self.assertEqual(derived, expected)
        self.assertNotEqual(derived, wrong_hex_text_result)
        self.assertRegex(derived, r"^[0-9a-f]{64}$")

    def test_explicit_local_mode_is_anonymous_plaintext_localhost(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configured = resolve_broker_configuration(
                parse_args(["--device-id", "sim-local", "--local"]),
                "local-device-secret",
            )

        self.assertEqual(configured.host, "localhost")
        self.assertEqual(configured.port, 1883)
        self.assertFalse(configured.tls)
        self.assertIsNone(configured.username)
        self.assertIsNone(configured.password)

    def test_custom_mode_preserves_operator_overrides(self) -> None:
        environment = {
            "DEVICEOPS_MQTT_USERNAME": "configured-user",
            "DEVICEOPS_MQTT_PASSWORD": "configured-password",
        }
        with patch.dict(os.environ, environment, clear=True):
            configured = resolve_broker_configuration(
                parse_args(
                    [
                        "--device-id",
                        "sim-custom",
                        "--custom",
                        "--broker-host",
                        "broker.example.test",
                        "--broker-port",
                        "8883",
                        "--tls",
                    ]
                ),
                "custom-device-secret",
            )

        self.assertEqual(configured.host, "broker.example.test")
        self.assertEqual(configured.port, 8883)
        self.assertTrue(configured.tls)
        self.assertEqual(configured.username, "configured-user")
        self.assertEqual(configured.password, "configured-password")

    def test_invalid_mode_and_override_combinations_are_rejected(self) -> None:
        cases = (
            ["--device-id", "sim", "--broker-host", "broker.example.test"],
            ["--device-id", "sim", "--local", "--tls"],
            ["--device-id", "sim", "--custom"],
        )
        with patch.dict(os.environ, {}, clear=True):
            for arguments in cases:
                with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                    resolve_broker_configuration(
                        parse_args(arguments), "device-secret"
                    )

        with self.assertRaises(SystemExit):
            parse_args(["--device-id", "sim", "--local", "--custom"])

    def test_hosted_and_local_modes_reject_environment_credentials(self) -> None:
        environment = {
            "DEVICEOPS_MQTT_USERNAME": "unexpected-user",
            "DEVICEOPS_MQTT_PASSWORD": "unexpected-password",
        }
        with patch.dict(os.environ, environment, clear=True):
            for mode in ([], ["--local"]):
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    resolve_broker_configuration(
                        parse_args(["--device-id", "sim", *mode]),
                        "device-secret",
                    )

    def test_credentials_must_be_nonempty_and_configured_together(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(broker_credentials_from_environment(), (None, None))

        for environment in (
            {"DEVICEOPS_MQTT_USERNAME": "configured-user"},
            {"DEVICEOPS_MQTT_PASSWORD": "configured-password"},
            {
                "DEVICEOPS_MQTT_USERNAME": "",
                "DEVICEOPS_MQTT_PASSWORD": "configured-password",
            },
        ):
            with self.subTest(environment=set(environment)):
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaises(ValueError):
                        broker_credentials_from_environment()

    def test_secret_values_are_absent_from_config_repr_and_errors(self) -> None:
        device_secret = "never-log-device-secret"
        broker_password = derive_broker_password(device_secret)
        with patch.dict(os.environ, {}, clear=True):
            configured = resolve_broker_configuration(
                parse_args(["--device-id", "dev-hosted"]), device_secret
            )
        rendered = repr(configured)
        self.assertNotIn(device_secret, rendered)
        self.assertNotIn(broker_password, rendered)

        environment = {
            "DEVICEOPS_MQTT_USERNAME": "operator-user",
            "DEVICEOPS_MQTT_PASSWORD": "never-log-operator-password",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(ValueError) as raised:
                resolve_broker_configuration(
                    parse_args(["--device-id", "dev-hosted"]), device_secret
                )
        self.assertNotIn(device_secret, str(raised.exception))
        self.assertNotIn(
            environment["DEVICEOPS_MQTT_PASSWORD"], str(raised.exception)
        )

    def test_run_uses_device_id_as_client_id_without_logging_secrets(self) -> None:
        device_secret = "never-print-device-secret"
        broker_password = derive_broker_password(device_secret)
        client = MagicMock()
        client.connect.side_effect = OSError("broker unavailable")
        standard_output = StringIO()
        standard_error = StringIO()

        with (
            patch("device_simulator.main.mqtt.Client", return_value=client) as factory,
            redirect_stdout(standard_output),
            redirect_stderr(standard_error),
        ):
            result = run(
                "dev-client-id",
                5,
                HOSTED_BROKER_HOST,
                HOSTED_BROKER_PORT,
                device_secret,
                broker_tls=True,
                broker_username="dev-client-id",
                broker_password=broker_password,
            )

        self.assertEqual(result, 1)
        self.assertEqual(factory.call_args.kwargs["client_id"], "dev-client-id")
        client.username_pw_set.assert_called_once_with(
            "dev-client-id", broker_password
        )
        rendered = standard_output.getvalue() + standard_error.getvalue()
        self.assertNotIn(device_secret, rendered)
        self.assertNotIn(broker_password, rendered)

    def test_tls_and_broker_auth_use_paho_verified_defaults(self) -> None:
        client = MagicMock()

        configure_mqtt_transport(
            client,
            tls_enabled=True,
            username="configured-user",
            password="configured-password",
        )

        client.username_pw_set.assert_called_once_with(
            "configured-user", "configured-password"
        )
        client.tls_set.assert_called_once_with()
        client.tls_insecure_set.assert_called_once_with(False)

    def test_local_transport_does_not_enable_auth_or_tls(self) -> None:
        client = MagicMock()

        configure_mqtt_transport(
            client,
            tls_enabled=False,
            username=None,
            password=None,
        )

        client.username_pw_set.assert_not_called()
        client.tls_set.assert_not_called()
        client.tls_insecure_set.assert_not_called()

    def test_transient_disconnect_waits_for_reconnect_but_other_errors_fail(self) -> None:
        self.assertTrue(telemetry_publish_completed(mqtt.MQTT_ERR_SUCCESS))
        self.assertFalse(telemetry_publish_completed(mqtt.MQTT_ERR_NO_CONN))
        with self.assertRaises(RuntimeError):
            telemetry_publish_completed(mqtt.MQTT_ERR_INVAL)


if __name__ == "__main__":
    unittest.main()
