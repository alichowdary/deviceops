"""Focused migration contract tests for nullable core telemetry."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "0014_nullable_core_telemetry.py"
)
SPEC = importlib.util.spec_from_file_location("migration_0014", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class NullableCoreTelemetryMigrationTests(unittest.TestCase):
    def test_upgrade_makes_only_required_columns_nullable(self) -> None:
        self.assertEqual(migration.revision, "0014")
        self.assertEqual(migration.down_revision, "0013")

        with patch.object(migration, "op") as operation:
            migration.upgrade()

        calls = operation.alter_column.call_args_list
        self.assertEqual(
            [(call.args[0], call.args[1]) for call in calls],
            [
                ("telemetry", "temperature_c"),
                ("telemetry", "rssi_dbm"),
                ("telemetry", "uptime_s"),
            ],
        )
        self.assertTrue(all(call.kwargs["nullable"] is True for call in calls))

    def test_downgrade_restores_not_null_without_backfill(self) -> None:
        with patch.object(migration, "op") as operation:
            migration.downgrade()

        calls = operation.alter_column.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call.kwargs["nullable"] is False for call in calls))
        operation.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
