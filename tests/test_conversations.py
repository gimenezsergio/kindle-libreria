from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from biblioteca_kindle.conversations import (
    ConversationError,
    add_message,
    create_conversation,
    get_conversation,
    context_options,
    update_context,
    build_prompt_packet,
)
from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.ai import DraftProvider, ResponsesProvider, load_environment_file, provider_from_environment


class ConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "library.sqlite3"
        migrate_database(self.database)
        connection = connect_database(self.database)
        with connection:
            connection.execute(
                "INSERT INTO works(id, preferred_title) VALUES ('work-1', 'Una lectura')"
            )
        connection.close()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_conversation_preserves_profile_used_and_orders_messages(self) -> None:
        identifier = create_conversation(
            self.database,
            work_id="work-1",
            profile_id="companion",
            title="Primera charla",
        )
        add_message(
            self.database,
            conversation_id=identifier,
            role="user",
            content="  ¿Qué conflicto aparece?  ",
        )
        add_message(
            self.database,
            conversation_id=identifier,
            role="assistant",
            content="Podríamos empezar por esta tensión.",
        )

        connection = connect_database(self.database)
        with connection:
            connection.execute(
                "UPDATE ai_profiles SET name = 'Otro nombre', prompt = 'Otro prompt' WHERE id = 'companion'"
            )
        connection.close()

        conversation = get_conversation(self.database, identifier)
        self.assertEqual(conversation["work_id"], "work-1")
        self.assertEqual(conversation["profile_id"], "companion")
        self.assertEqual(conversation["profile_name_snapshot"], "Compañero de lectura")
        self.assertIn("compañero de lectura curioso", conversation["profile_prompt_snapshot"])
        self.assertEqual(
            [(message["sequence"], message["role"], message["content"]) for message in conversation["messages"]],
            [
                (1, "user", "¿Qué conflicto aparece?"),
                (2, "assistant", "Podríamos empezar por esta tensión."),
            ],
        )

    def test_invalid_references_roles_and_empty_messages_are_rejected(self) -> None:
        with self.assertRaisesRegex(ConversationError, "obra no existe"):
            create_conversation(
                self.database, work_id="missing", profile_id="companion"
            )
        identifier = create_conversation(
            self.database, work_id="work-1", profile_id="companion"
        )
        with self.assertRaisesRegex(ConversationError, "rol"):
            add_message(
                self.database,
                conversation_id=identifier,
                role="system",
                content="Mensaje",
            )
        with self.assertRaisesRegex(ConversationError, "vacío"):
            add_message(
                self.database,
                conversation_id=identifier,
                role="user",
                content="   ",
            )

    def test_selected_context_is_snapshotted_for_the_conversation(self) -> None:
        connection = connect_database(self.database)
        with connection:
            connection.execute("INSERT INTO personal_notes(id, target_type, target_id, body) VALUES ('note', 'work', 'work-1', 'Mi hipótesis')")
            connection.execute("INSERT INTO editions(id, work_id, title) VALUES ('edition', 'work-1', 'Una lectura')")
            connection.execute("INSERT INTO annotations(id, edition_id, kind, text) VALUES ('annotation', 'edition', 'highlight', 'Pasaje importante')")
        connection.close()
        identifier = create_conversation(self.database, work_id="work-1", profile_id="companion")
        options = context_options(self.database, identifier)
        self.assertEqual(options["notes"][0]["id"], "note")
        update_context(self.database, identifier, personal_note_ids=["note"], annotation_ids=["annotation"])
        connection = connect_database(self.database)
        with connection:
            connection.execute("UPDATE personal_notes SET body = 'Texto cambiado' WHERE id = 'note'")
        connection.close()
        context = get_conversation(self.database, identifier)["context_sources"]
        self.assertEqual([item["source_type"] for item in context], ["annotation", "personal_note", "work"])
        self.assertIn("Mi hipótesis", [item["content_snapshot"] for item in context])
        add_message(self.database, conversation_id=identifier, role="user", content="¿Qué ves acá?")
        packet = build_prompt_packet(self.database, identifier)
        self.assertIn("no como autoridad", packet.instructions)
        self.assertIn("Mi hipótesis", packet.input[0]["content"])
        self.assertEqual(packet.input[-1]["content"], "¿Qué ves acá?")

    def test_deepseek_provider_uses_responses_endpoint_without_persisting_key(self) -> None:
        with patch.dict("os.environ", {
            "BIBLIOTECA_AI_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "temporary-test-key",
        }, clear=True):
            provider = provider_from_environment()
        self.assertIsInstance(provider, ResponsesProvider)
        self.assertEqual(provider.name, "deepseek")
        self.assertEqual(provider.url, "https://api.deepseek.com/responses")
        self.assertEqual(provider.model, "deepseek-v4-flash")
        with patch.dict("os.environ", {"BIBLIOTECA_AI_PROVIDER": "deepseek"}, clear=True):
            self.assertIsInstance(provider_from_environment(), DraftProvider)

    def test_environment_file_does_not_override_exported_values(self) -> None:
        environment = Path(self.temporary.name) / ".env"
        environment.write_text("BIBLIOTECA_AI_PROVIDER=deepseek\nDEEPSEEK_API_KEY=local-key\n", encoding="utf-8")
        with patch.dict("os.environ", {"BIBLIOTECA_AI_PROVIDER": "draft"}, clear=True):
            load_environment_file(environment)
            self.assertEqual(__import__("os").environ["BIBLIOTECA_AI_PROVIDER"], "draft")
            self.assertEqual(__import__("os").environ["DEEPSEEK_API_KEY"], "local-key")


if __name__ == "__main__":
    unittest.main()
