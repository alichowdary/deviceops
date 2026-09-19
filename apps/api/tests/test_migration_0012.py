"""Focused migration contract tests for generic numeric alert metrics."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "0012_generic_alert_metrics.py"
)
SPEC = importlib.util.spec_from_file_location("migration_0012", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class GenericAlertMetricMigrationTests(unittest.TestCase):
    def test_revision_chain_and_non_destructive_upgrade(self) -> None:
        self.assertEqual(migration.revision, "0012")
        self.assertEqual(migration.down_revision, "0011")

        with patch.object(migration, "op") as operation:
            migration.upgrade()

        self.assertEqual(operation.alter_column.call_count, 2)
        for call in operation.alter_column.call_args_list:
            self.assertIsInstance(call.kwargs["type_"], sa.String)
            self.assertEqual(call.kwargs["type_"].length, 64)
        created = {
            call.args[0]: call.args[2]
            for call in operation.create_check_constraint.call_args_list
        }
        self.assertIn("^[a-z][a-z0-9_]{0,63}$", created["ck_alert_rules_metric"])
        self.assertIn("1.7976931348623157e308", created["ck_alert_rules_threshold_bounds"])
        self.assertIn("^[a-z][a-z0-9_]{0,63}$", created["ck_alerts_metric"])
        operation.drop_table.assert_not_called()
        operation.execute.assert_not_called()

    def test_downgrade_restores_legacy_constraints_and_width(self) -> None:
        with patch.object(migration, "op") as operation:
            migration.downgrade()

        self.assertEqual(operation.alter_column.call_count, 2)
        for call in operation.alter_column.call_args_list:
            self.assertEqual(call.kwargs["type_"].length, 32)
        created = {
            call.args[0]: call.args[2]
            for call in operation.create_check_constraint.call_args_list
        }
        self.assertIn("temperature_c", created["ck_alert_rules_metric"])
        self.assertIn("battery_pct", created["ck_alerts_metric"])
        operation.drop_table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
