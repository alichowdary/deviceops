"""Focused migration contract tests for global retention indexes."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "0013_retention_indexes.py"
)
SPEC = importlib.util.spec_from_file_location("migration_0013", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class RetentionIndexMigrationTests(unittest.TestCase):
    def test_upgrade_adds_only_global_timestamp_indexes(self) -> None:
        self.assertEqual(migration.revision, "0013")
        self.assertEqual(migration.down_revision, "0012")

        with patch.object(migration, "op") as operation:
            migration.upgrade()

        self.assertEqual(
            [call.args for call in operation.create_index.call_args_list],
            [
                ("ix_telemetry_received_at", "telemetry", ["received_at"]),
                (
                    "ix_device_events_occurred_at",
                    "device_events",
                    ["occurred_at"],
                ),
            ],
        )
        operation.drop_table.assert_not_called()

    def test_downgrade_removes_both_retention_indexes(self) -> None:
        with patch.object(migration, "op") as operation:
            migration.downgrade()

        self.assertEqual(
            [call.args[0] for call in operation.drop_index.call_args_list],
            ["ix_device_events_occurred_at", "ix_telemetry_received_at"],
        )
        self.assertTrue(
            all(
                call.kwargs["table_name"] in {"device_events", "telemetry"}
                for call in operation.drop_index.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
