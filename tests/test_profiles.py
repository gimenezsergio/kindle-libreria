from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.ai import resolve_provider_for_profile, DraftProvider, ResponsesProvider
from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.profiles import create_profile, update_profile


class ProfileTests(unittest.TestCase):
    def test_create_and_update_profile_with_provider_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)

            pid = create_profile(
                database,
                name="Perfil Gemini",
                description="Usa Gemini Flash",
                prompt="Sos un asistente filosófico",
                provider_id="gemini",
                model_override="gemini-2.5-pro",
            )

            connection = connect_database(database)
            try:
                row = connection.execute("SELECT * FROM ai_profiles WHERE id = ?", (pid,)).fetchone()
                self.assertEqual(row["name"], "Perfil Gemini")
                self.assertEqual(row["provider_id"], "gemini")
                self.assertEqual(row["model_override"], "gemini-2.5-pro")
            finally:
                connection.close()

            update_profile(
                database,
                pid,
                {
                    "provider_id": "deepseek",
                    "model_override": "deepseek-chat",
                }
            )

            connection = connect_database(database)
            try:
                row = connection.execute("SELECT * FROM ai_profiles WHERE id = ?", (pid,)).fetchone()
                self.assertEqual(row["provider_id"], "deepseek")
                self.assertEqual(row["model_override"], "deepseek-chat")
            finally:
                connection.close()

    def test_resolve_provider_for_profile(self) -> None:
        draft = resolve_provider_for_profile("draft", None)
        self.assertIsInstance(draft, DraftProvider)

        provider = resolve_provider_for_profile("gemini", "gemini-2.5-pro")
        self.assertIsInstance(provider, (ResponsesProvider, DraftProvider))
        if isinstance(provider, ResponsesProvider):
            self.assertEqual(provider.name, "gemini")
            self.assertEqual(provider.model, "gemini-2.5-pro")


if __name__ == "__main__":
    unittest.main()
