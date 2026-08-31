from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database, migrate_database


class MigrationTests(unittest.TestCase):
    def test_initial_migration_creates_expected_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            self.assertEqual(
                migrate_database(database),
                [
                    "0001_initial.sql",
                    "0002_reading_history.sql",
                    "0003_personal_constraints.sql",
                ],
            )

            connection = connect_database(database)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()

            self.assertTrue(
                {
                    "schema_migrations",
                    "works",
                    "editions",
                    "kindle_deliveries",
                    "reading_states",
                    "annotations",
                    "annotation_occurrences",
                    "collections",
                    "personal_notes",
                    "work_relations",
                    "reading_history_records",
                }.issubset(tables)
            )

    def test_migration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            self.assertEqual(migrate_database(database), [])

            connection = connect_database(database)
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 3)

    def test_foreign_keys_are_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO editions(id, work_id, title) VALUES (?, ?, ?)",
                        ("edition", "missing-work", "Title"),
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
