"""Focused migration contract tests for optional device display names."""

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
    / "0011_device_display_name.py"
)
SPEC = importlib.util.spec_from_file_location("migration_0011", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class DeviceDisplayNameMigrationTests(unittest.TestCase):
    def test_revision_chain_and_upgrade_column(self) -> None:
        self.assertEqual(migration.revision, "0011")
        self.assertEqual(migration.down_revision, "0010")

        with patch.object(migration, "op") as operation:
            migration.upgrade()

        operation.add_column.assert_called_once()
        table_name, column = operation.add_column.call_args.args
        self.assertEqual(table_name, "devices")
        self.assertIsInstance(column, sa.Column)
        self.assertEqual(column.name, "display_name")
        self.assertIsInstance(column.type, sa.String)
        self.assertEqual(column.type.length, 80)
        self.assertTrue(column.nullable)

    def test_downgrade_drops_only_display_name(self) -> None:
        with patch.object(migration, "op") as operation:
            migration.downgrade()

        operation.drop_column.assert_called_once_with("devices", "display_name")


if __name__ == "__main__":
    unittest.main()
