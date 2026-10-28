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
                    "0015_conversation_title_origin.sql",
                    "0016_conversation_message_actions.sql",
                    "0017_update_companion_profile_prompt.sql",
                    "0018_profile_provider_override.sql",
                    "0019_update_lectores_muermos_prompt.sql",
                    "0020_update_marta_profile_prompt.sql",
                    "0021_conversational_dynamic_profiles.sql",
                    "0022_recently_opened_works.sql",
                    "0023_philosophical_inquiries.sql",
                    "0024_conversation_summaries.sql",
                    "0025_telegram_sessions.sql",
                    "0026_summary_last_sequence.sql",
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
                    "recently_opened_works",
                    "philosophical_inquiries",
                    "inquiry_annotations",
                    "inquiry_messages",
                    "inquiry_tags",
                    "annotation_contexts",
                    "conversation_summaries",
                    "telegram_sessions",
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
            self.assertEqual(count, 26)



    def test_action_columns_are_nullable_for_existing_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                columns = {
                    row["name"]: row
                    for row in connection.execute("PRAGMA table_info(conversation_messages)")
                }
                self.assertIn("companion_action_id", columns)
                self.assertIn("companion_action_label_snapshot", columns)
                self.assertEqual(columns["companion_action_id"]["notnull"], 0)
                self.assertEqual(columns["companion_action_label_snapshot"]["notnull"], 0)
            finally:
                connection.close()

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

    def test_conversation_summary_source_type_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                # Crear obra, perfil y conversación
                connection.execute("INSERT INTO works(id, preferred_title) VALUES ('w1', 'Work 1')")
                connection.execute("INSERT INTO ai_profiles(id, name, prompt) VALUES ('p1', 'Profile 1', 'Prompt')")
                connection.execute(
                    "INSERT INTO reading_conversations(id, work_id, profile_id, profile_name_snapshot, profile_prompt_snapshot) "
                    "VALUES ('c1', 'w1', 'p1', 'Profile 1', 'Prompt')"
                )
                # Debe permitir source_type = 'conversation_summary'
                connection.execute(
                    "INSERT INTO conversation_context_sources(id, conversation_id, source_type, source_id, label_snapshot, content_snapshot) "
                    "VALUES ('cs1', 'c1', 'conversation_summary', 'c2', 'Síntesis previa', 'Resumen')"
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
