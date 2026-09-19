"""Focused simulator profile, telemetry, command, and CLI tests."""

from __future__ import annotations

import unittest

from device_simulator.commands import SimulatorCommandState, execute_command
from device_simulator.main import build_capability_manifest, parse_args
from device_simulator.profiles import DEFAULT_PROFILE, PORTABLE_SENSOR_PROFILE


class ProfileTests(unittest.TestCase):
    def test_cli_defaults_to_existing_profile(self) -> None:
        args = parse_args(["--device-id", "sim-default"])
        self.assertEqual(args.profile, "default")
        self.assertEqual(args.interval, 5.0)

    def test_cli_accepts_portable_sensor_profile(self) -> None:
        args = parse_args(
            ["--device-id", "sim-portable", "--profile", "portable-sensor"]
        )
        self.assertEqual(args.profile, "portable-sensor")

    def test_default_manifest_remains_unchanged(self) -> None:
        manifest = build_capability_manifest("sim-default")

        self.assertEqual(
            manifest["telemetry"],
            {
                "temperature_c": {
                    "type": "number",
                    "label": "Temperature",
                    "unit": "°C",
                },
                "battery_pct": {
                    "type": "number",
                    "label": "Battery",
                    "unit": "%",
                },
                "rssi_dbm": {
                    "type": "integer",
                    "label": "RSSI",
                    "unit": "dBm",
                },
                "uptime_s": {
                    "type": "integer",
                    "label": "Uptime",
                    "unit": "s",
                },
            },
        )
        self.assertEqual(
            set(manifest["commands"]),
            {"set_led", "set_reporting_interval", "request_diagnostics"},
        )
        self.assertIs(
            DEFAULT_PROFILE.create_generator("sim-default").__class__,
            DEFAULT_PROFILE.generator_type,
        )

    def test_portable_manifest_is_materially_different(self) -> None:
        manifest = build_capability_manifest("sim-portable", "portable-sensor")

        self.assertEqual(
            list(manifest["telemetry"]),
            [
                "temperature_c",
                "battery_pct",
                "light_lux",
                "motion_detected",
                "rssi_dbm",
                "uptime_s",
            ],
        )
        self.assertNotIn("humidity_pct", manifest["telemetry"])
        self.assertNotIn("pressure_hpa", manifest["telemetry"])
        self.assertEqual(
            manifest["telemetry"]["light_lux"],
            {"type": "number", "label": "Ambient light", "unit": "lux"},
        )
        self.assertEqual(
            manifest["telemetry"]["motion_detected"],
            {"type": "boolean", "label": "Motion detected"},
        )
        self.assertEqual(set(manifest["commands"]), {"request_diagnostics"})

    def test_portable_telemetry_matches_manifest_types(self) -> None:
        generator = PORTABLE_SENSOR_PROFILE.create_generator("sim-portable")
        first = generator.next_message()["metrics"]
        second = generator.next_message()["metrics"]

        self.assertIsInstance(first["light_lux"], float)
        self.assertIsInstance(first["motion_detected"], bool)
        self.assertIsInstance(first["temperature_c"], float)
        self.assertIsInstance(first["battery_pct"], float)
        self.assertIsInstance(first["rssi_dbm"], int)
        self.assertIsInstance(first["uptime_s"], int)
        self.assertNotEqual(first["light_lux"], second["light_lux"])
        self.assertNotIn("humidity_pct", first)
        self.assertNotIn("pressure_hpa", first)

    def test_portable_rejects_unadvertised_commands(self) -> None:
        state = SimulatorCommandState(reporting_interval=5.0)

        for command_type, arguments in (
            ("set_led", {"on": True}),
            ("set_reporting_interval", {"interval_s": 2}),
        ):
            with self.subTest(command_type=command_type):
                with self.assertRaisesRegex(
                    ValueError, "unsupported command for profile 'portable-sensor'"
                ):
                    execute_command(
                        PORTABLE_SENSOR_PROFILE,
                        command_type,
                        arguments,
                        state,
                        uptime_s=10,
                    )

        self.assertFalse(state.led_on)
        self.assertEqual(state.reporting_interval, 5.0)

    def test_default_commands_keep_existing_behavior(self) -> None:
        state = SimulatorCommandState(
            reporting_interval=5.0,
            last_metrics={"temperature_c": 24.5},
        )

        self.assertEqual(
            execute_command(
                DEFAULT_PROFILE, "set_led", {"on": True}, state, uptime_s=1
            ),
            {"on": True},
        )
        self.assertEqual(
            execute_command(
                DEFAULT_PROFILE,
                "set_reporting_interval",
                {"interval_s": 2.5},
                state,
                uptime_s=1,
            ),
            {"interval_s": 2.5},
        )
        self.assertEqual(
            execute_command(
                DEFAULT_PROFILE,
                "request_diagnostics",
                {},
                state,
                uptime_s=9,
            ),
            {
                "led_on": True,
                "reporting_interval_s": 2.5,
                "uptime_s": 9,
                "telemetry": {"temperature_c": 24.5},
            },
        )

    def test_portable_diagnostics_succeeds(self) -> None:
        state = SimulatorCommandState(
            reporting_interval=5.0,
            last_metrics={"light_lux": 215.0, "motion_detected": True},
        )

        result = execute_command(
            PORTABLE_SENSOR_PROFILE,
            "request_diagnostics",
            {},
            state,
            uptime_s=42,
        )

        self.assertEqual(
            result,
            {
                "uptime_s": 42,
                "telemetry": {"light_lux": 215.0, "motion_detected": True},
            },
        )


if __name__ == "__main__":
    unittest.main()
