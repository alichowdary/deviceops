"""Focused simulator MQTT TLS and broker-auth configuration tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from device_simulator.main import (
    broker_credentials_from_environment,
    configure_mqtt_transport,
    parse_args,
)


class SimulatorMqttConfigurationTests(unittest.TestCase):
    def test_cli_keeps_local_defaults_and_accepts_tls(self) -> None:
        local = parse_args(["--device-id", "sim-local"])
        production = parse_args(
            [
                "--device-id",
                "sim-production",
                "--broker-host",
                "broker.example.test",
                "--broker-port",
                "8883",
                "--tls",
            ]
        )

        self.assertEqual(local.broker_host, "localhost")
        self.assertEqual(local.broker_port, 1883)
        self.assertFalse(local.tls)
        self.assertEqual(production.broker_host, "broker.example.test")
        self.assertEqual(production.broker_port, 8883)
        self.assertTrue(production.tls)

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


if __name__ == "__main__":
    unittest.main()
