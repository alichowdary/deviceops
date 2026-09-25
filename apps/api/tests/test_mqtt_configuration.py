"""Focused MQTT broker transport and environment configuration tests."""

from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from deviceops_api.config import Settings
from deviceops_api.mqtt import MqttIngestor


class MqttSettingsTests(unittest.TestCase):
    def test_local_defaults_remain_anonymous_plaintext(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configured = Settings.from_environment()

        self.assertEqual(configured.mqtt_host, "localhost")
        self.assertEqual(configured.mqtt_port, 1883)
        self.assertFalse(configured.mqtt_tls)
        self.assertIsNone(configured.mqtt_username)
        self.assertIsNone(configured.mqtt_password)
        self.assertFalse(configured.broker_provisioning_enabled)
        self.assertIsNone(configured.broker_provisioning_host)
        self.assertEqual(configured.broker_provisioning_port, 443)
        self.assertIsNone(configured.broker_provisioning_username)
        self.assertIsNone(configured.broker_provisioning_password)
        self.assertTrue(configured.broker_provisioning_tls)
        self.assertEqual(configured.broker_provisioning_timeout_seconds, 5)

    def test_tls_and_credentials_are_loaded_without_changing_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DEVICEOPS_MQTT_HOST": "broker.example.test",
                "DEVICEOPS_MQTT_PORT": "8883",
                "DEVICEOPS_MQTT_TLS": "true",
                "DEVICEOPS_MQTT_USERNAME": "configured-user",
                "DEVICEOPS_MQTT_PASSWORD": "configured-password",
            },
            clear=True,
        ):
            configured = Settings.from_environment()

        self.assertEqual(configured.mqtt_host, "broker.example.test")
        self.assertEqual(configured.mqtt_port, 8883)
        self.assertTrue(configured.mqtt_tls)
        self.assertEqual(configured.mqtt_username, "configured-user")
        self.assertEqual(configured.mqtt_password, "configured-password")

    def test_partial_credentials_and_invalid_tls_are_rejected(self) -> None:
        for environment in (
            {"DEVICEOPS_MQTT_USERNAME": "configured-user"},
            {"DEVICEOPS_MQTT_PASSWORD": "configured-password"},
            {"DEVICEOPS_MQTT_TLS": "sometimes"},
        ):
            with self.subTest(environment=set(environment)):
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaises(ValueError):
                        Settings.from_environment()

    def test_disabled_provisioning_does_not_require_credentials(self) -> None:
        with patch.dict(
            os.environ,
            {"DEVICEOPS_BROKER_PROVISIONING_ENABLED": "false"},
            clear=True,
        ):
            configured = Settings.from_environment()

        self.assertFalse(configured.broker_provisioning_enabled)
        self.assertIsNone(configured.broker_provisioning_password)

    def test_enabled_provisioning_loads_separate_verified_tls_settings(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DEVICEOPS_BROKER_PROVISIONING_ENABLED": "yes",
                "DEVICEOPS_BROKER_PROVISIONING_HOST": "mqtt.example.test",
                "DEVICEOPS_BROKER_PROVISIONING_PORT": "443",
                "DEVICEOPS_BROKER_PROVISIONING_USERNAME": "dynsec-admin",
                "DEVICEOPS_BROKER_PROVISIONING_PASSWORD": "test-only-password",
                "DEVICEOPS_BROKER_PROVISIONING_TLS": "on",
                "DEVICEOPS_BROKER_PROVISIONING_TIMEOUT_SECONDS": "7",
            },
            clear=True,
        ):
            configured = Settings.from_environment()

        self.assertTrue(configured.broker_provisioning_enabled)
        self.assertEqual(
            configured.broker_provisioning_host, "mqtt.example.test"
        )
        self.assertEqual(configured.broker_provisioning_port, 443)
        self.assertEqual(
            configured.broker_provisioning_username, "dynsec-admin"
        )
        self.assertEqual(
            configured.broker_provisioning_password, "test-only-password"
        )
        self.assertTrue(configured.broker_provisioning_tls)
        self.assertEqual(configured.broker_provisioning_timeout_seconds, 7)

    def test_enabled_provisioning_requires_host_username_and_password(self) -> None:
        complete = {
            "DEVICEOPS_BROKER_PROVISIONING_ENABLED": "true",
            "DEVICEOPS_BROKER_PROVISIONING_HOST": "mqtt.example.test",
            "DEVICEOPS_BROKER_PROVISIONING_USERNAME": "dynsec-admin",
            "DEVICEOPS_BROKER_PROVISIONING_PASSWORD": "test-only-password",
        }
        for missing_name in (
            "DEVICEOPS_BROKER_PROVISIONING_HOST",
            "DEVICEOPS_BROKER_PROVISIONING_USERNAME",
            "DEVICEOPS_BROKER_PROVISIONING_PASSWORD",
        ):
            environment = dict(complete)
            environment.pop(missing_name)
            with self.subTest(missing_name=missing_name):
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaisesRegex(ValueError, missing_name):
                        Settings.from_environment()

    def test_provisioning_tls_uses_existing_boolean_parser(self) -> None:
        environment = {
            "DEVICEOPS_BROKER_PROVISIONING_ENABLED": "true",
            "DEVICEOPS_BROKER_PROVISIONING_HOST": "mqtt.example.test",
            "DEVICEOPS_BROKER_PROVISIONING_USERNAME": "dynsec-admin",
            "DEVICEOPS_BROKER_PROVISIONING_PASSWORD": "test-only-password",
        }
        with patch.dict(
            os.environ,
            {**environment, "DEVICEOPS_BROKER_PROVISIONING_TLS": "off"},
            clear=True,
        ):
            configured = Settings.from_environment()
        self.assertFalse(configured.broker_provisioning_tls)

        with patch.dict(
            os.environ,
            {**environment, "DEVICEOPS_BROKER_PROVISIONING_TLS": "invalid"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                Settings.from_environment()


class MqttClientConfigurationTests(unittest.TestCase):
    def _settings(self, *, tls: bool, authenticated: bool) -> SimpleNamespace:
        return SimpleNamespace(
            mqtt_client_id="test-api-client",
            mqtt_tls=tls,
            mqtt_username="configured-user" if authenticated else None,
            mqtt_password="configured-password" if authenticated else None,
        )

    def test_tls_and_broker_auth_are_applied_to_paho(self) -> None:
        client = MagicMock()
        with (
            patch("deviceops_api.mqtt.settings", self._settings(tls=True, authenticated=True)),
            patch("deviceops_api.mqtt.mqtt.Client", return_value=client),
        ):
            MqttIngestor()

        client.username_pw_set.assert_called_once_with(
            "configured-user", "configured-password"
        )
        client.tls_set.assert_called_once_with()
        client.tls_insecure_set.assert_called_once_with(False)

    def test_local_defaults_do_not_enable_auth_or_tls(self) -> None:
        client = MagicMock()
        with (
            patch("deviceops_api.mqtt.settings", self._settings(tls=False, authenticated=False)),
            patch("deviceops_api.mqtt.mqtt.Client", return_value=client),
        ):
            MqttIngestor()

        client.username_pw_set.assert_not_called()
        client.tls_set.assert_not_called()
        client.tls_insecure_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
