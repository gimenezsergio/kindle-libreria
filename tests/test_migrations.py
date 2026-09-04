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
                    "0004_work_display_title.sql",
                    "0005_ai_profiles.sql",
                    "0006_cover_preferences.sql",
                    "0007_cover_candidates.sql",
                    "0008_cover_search_rounds.sql",
                    "0009_reading_conversations.sql",
                    "0010_conversation_context.sql",
                    "0011_remote_sync.sql",
                    "0012_conversation_retrieval.sql",
                    "0013_pinned_context.sql",
                    "0014_external_conversation_turns.sql",
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
                    "ai_profiles",
                    "work_cover_preferences",
                    "cover_candidates",
                    "reading_conversations",
                    "conversation_messages",
                    "conversation_context_sources",
                    "conversation_message_sources",
                    "remote_sync_packages",
                    "external_conversation_turns",
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
            self.assertEqual(count, 14)

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
