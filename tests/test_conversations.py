from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.conversations import (
    ConversationError,
    add_message,
    create_conversation,
    get_conversation,
)
from biblioteca_kindle.db import connect_database, migrate_database


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


if __name__ == "__main__":
    unittest.main()
