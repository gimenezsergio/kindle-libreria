from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from biblioteca_kindle.ai import PromptPacket
from biblioteca_kindle.conversations import add_message, create_conversation, get_conversation
from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.telegram_bot import TelegramBotService
from biblioteca_kindle.telegram_client import (
    TelegramAPIError,
    TelegramClient,
    markdown_to_telegram_html,
    split_message_text,
)


class MockTelegramClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.edited_messages: list[dict[str, Any]] = []
        self.answered_callbacks: list[dict[str, Any]] = []

    def get_me(self) -> dict[str, Any]:
        return {"id": 12345, "username": "TestBot", "first_name": "Test Bot"}

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
            "parse_mode": parse_mode,
        }
        self.sent_messages.append(record)
        return {"message_id": len(self.sent_messages), "chat": {"id": chat_id}, "text": text}

    def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": reply_markup,
            "parse_mode": parse_mode,
        }
        self.edited_messages.append(record)
        return {"message_id": message_id, "chat": {"id": chat_id}, "text": text}

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        self.answered_callbacks.append(
            {"id": callback_query_id, "text": text, "show_alert": show_alert}
        )
        return True

    def set_my_commands(self, commands: list[dict[str, str]]) -> bool:
        self.registered_commands = commands
        return True


class MockAIProvider:
    def __init__(self, answer: str = "Respuesta analítica del modelo") -> None:
        self.ready = True
        self.name = "mock_ai"
        self.answer = answer

    def respond(self, packet: PromptPacket) -> str:
        return self.answer


class TelegramBotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "library.sqlite3"
        migrate_database(self.database)

        # Seed de prueba
        conn = connect_database(self.database)
        with conn:
            conn.execute(
                """
                INSERT INTO works(id, preferred_title, display_title)
                VALUES ('work-1', '1984', '1984'), ('work-2', 'La sociedad del cansancio', 'La sociedad del cansancio')
                """
            )
            conn.execute(
                """
                INSERT INTO editions(id, work_id, title)
                VALUES ('ed-1', 'work-1', '1984'), ('ed-2', 'work-2', 'La sociedad del cansancio')
                """
            )
            conn.execute(
                """
                INSERT INTO contributors(id, display_name, normalized_name)
                VALUES ('c-1', 'George Orwell', 'george orwell'), ('c-2', 'Byung-Chul Han', 'byung chul han')
                """
            )
            conn.execute(
                """
                INSERT INTO edition_contributors(edition_id, contributor_id, role)
                VALUES ('ed-1', 'c-1', 'author'), ('ed-2', 'c-2', 'author')
                """
            )
        conn.close()

        self.client = MockTelegramClient()
        self.bot = TelegramBotService(self.database, self.client, allowed_user_id=1001)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_split_message_text(self) -> None:
        short_text = "Hola mundo"
        self.assertEqual(split_message_text(short_text), ["Hola mundo"])

        long_text = "Parte 1\n\n" + ("x" * 3000) + "\n\nParte 2\n\n" + ("y" * 2000)
        chunks = split_message_text(long_text, max_length=3500)
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 3500)

    def test_markdown_to_telegram_html(self) -> None:
        md = (
            "### Título Principal\n"
            "El **Gran Hermano** es *crucial*.\n"
            "Bloque:\n"
            "```python\n"
            "def foo():\n"
            "    return True\n"
            "```\n"
            "Cita:\n"
            "> Paz y guerra\n"
            "Inline `variable_1` y caracteres < & >."
        )
        html_out = markdown_to_telegram_html(md)
        self.assertIn("<b>Título Principal</b>", html_out)
        self.assertIn("<b>Gran Hermano</b>", html_out)
        self.assertIn("<i>crucial</i>", html_out)
        self.assertIn("<pre><code>def foo():", html_out)
        self.assertIn("<blockquote>Paz y guerra</blockquote>", html_out)
        self.assertIn("<code>variable_1</code>", html_out)
        self.assertIn("&lt; &amp; &gt;", html_out)

    def test_security_rejects_unauthorized_user(self) -> None:
        # Mensaje de usuario no autorizado (9999 != 1001)
        update_msg = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 9999, "first_name": "Intruso"},
                "chat": {"id": 9999},
                "text": "/start",
            },
        }
        self.bot.process_update(update_msg)
        self.assertEqual(len(self.client.sent_messages), 1)
        self.assertIn("privado", self.client.sent_messages[0]["text"])

        # Callback query de usuario no autorizado
        update_cb = {
            "update_id": 2,
            "callback_query": {
                "id": "cb-999",
                "from": {"id": 9999},
                "message": {"message_id": 11, "chat": {"id": 9999}},
                "data": "page:0",
            },
        }
        self.bot.process_update(update_cb)
        self.assertTrue(any(a["id"] == "cb-999" and a["show_alert"] for a in self.client.answered_callbacks))

    def test_start_command_sends_welcome_with_buttons(self) -> None:
        update = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 1001, "first_name": "Sergio"},
                "chat": {"id": 1001},
                "text": "/start",
            },
        }
        self.bot.process_update(update)
        self.assertEqual(len(self.client.sent_messages), 1)
        last_msg = self.client.sent_messages[0]
        self.assertIn("Biblioteca Kindle", last_msg["text"])
        self.assertIn("inline_keyboard", last_msg["reply_markup"])

    def test_catalog_and_book_selection(self) -> None:
        # 1. Solicitar /libros
        self.bot.process_update({
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 1001},
                "chat": {"id": 1001},
                "text": "/libros",
            },
        })
        self.assertEqual(len(self.client.sent_messages), 1)
        markup = self.client.sent_messages[0]["reply_markup"]["inline_keyboard"]
        buttons_flat = [b for row in markup for b in row]
        # Verificar que aparecen los dos libros
        cb_data = [b["callback_data"] for b in buttons_flat]
        self.assertIn("w:work-1", cb_data)
        self.assertIn("w:work-2", cb_data)

        # 2. Seleccionar work-1 mediante callback
        self.bot.process_update({
            "update_id": 2,
            "callback_query": {
                "id": "cb-1",
                "from": {"id": 1001},
                "message": {"message_id": 2, "chat": {"id": 1001}},
                "data": "w:work-1",
            },
        })
        self.assertEqual(len(self.client.edited_messages), 1)
        edited = self.client.edited_messages[0]
        self.assertIn("1984", edited["text"])
        self.assertIn("George Orwell", edited["text"])
        work_cb_data = [b["callback_data"] for row in edited["reply_markup"]["inline_keyboard"] for b in row]
        self.assertIn("new:work-1", work_cb_data)

    def test_search_works_by_text(self) -> None:
        self.bot.process_update({
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 1001},
                "chat": {"id": 1001},
                "text": "/buscar Orwel",
            },
        })
        self.assertEqual(len(self.client.sent_messages), 1)
        msg = self.client.sent_messages[0]
        self.assertIn("Resultados para «Orwel»", msg["text"])
        cb_data = [b["callback_data"] for row in msg["reply_markup"]["inline_keyboard"] for b in row]
        self.assertIn("w:work-1", cb_data)

    def test_create_conversation_with_profile(self) -> None:
        # 1. Abrir selector de perfil para work-1
        self.bot.process_update({
            "update_id": 1,
            "callback_query": {
                "id": "cb-1",
                "from": {"id": 1001},
                "message": {"message_id": 2, "chat": {"id": 1001}},
                "data": "new:work-1",
            },
        })
        edited = self.client.edited_messages[0]
        self.assertIn("Elegí el perfil pedagógico", edited["text"])
        profile_cb_data = [b["callback_data"] for row in edited["reply_markup"]["inline_keyboard"] for b in row]
        self.assertIn("p:companion", profile_cb_data)

        # 2. Elegir perfil "companion"
        self.bot.set_session(1001, work_id="work-1")
        self.bot.process_update({
            "update_id": 2,
            "callback_query": {
                "id": "cb-2",
                "from": {"id": 1001},
                "message": {"message_id": 2, "chat": {"id": 1001}},
                "data": "p:companion",
            },
        })
        # Verifica que la sesión quedó activa con una conversación
        _, conv_id = self.bot.get_session(1001)
        self.assertIsNotNone(conv_id)
        conv = get_conversation(self.database, conv_id)
        self.assertEqual(conv["work_id"], "work-1")
        self.assertEqual(conv["profile_id"], "companion")

    def test_chatting_in_active_conversation_and_ai_response(self) -> None:
        # Crear conversación previa
        conv_id = create_conversation(self.database, work_id="work-1", profile_id="companion", title="Totalitarismo")
        self.bot.set_session(1001, work_id="work-1", conversation_id=conv_id)

        # Simular respuesta del proveedor de IA
        mock_provider = MockAIProvider(answer="El Gran Hermano simboliza el panóptico absoluto.")
        with patch.object(self.bot, "resolve_conversation_ai", return_value=mock_provider):
            self.bot.process_update({
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "from": {"id": 1001},
                    "chat": {"id": 1001},
                    "text": "¿Qué representa el Gran Hermano?",
                },
            })

        # Verificar que el mensaje y la respuesta se guardaron en la base SQLite
        conv = get_conversation(self.database, conv_id)
        self.assertEqual(len(conv["messages"]), 2)
        self.assertEqual(conv["messages"][0]["role"], "user")
        self.assertEqual(conv["messages"][0]["content"], "¿Qué representa el Gran Hermano?")
        self.assertEqual(conv["messages"][1]["role"], "assistant")
        self.assertEqual(conv["messages"][1]["content"], "El Gran Hermano simboliza el panóptico absoluto.")

        # Verificar que la respuesta se envió al usuario de Telegram
        self.assertEqual(len(self.client.sent_messages), 1)
        self.assertEqual(self.client.sent_messages[0]["text"], "El Gran Hermano simboliza el panóptico absoluto.")
        self.assertEqual(self.client.sent_messages[0]["parse_mode"], "HTML")

    def test_resume_past_conversation(self) -> None:
        # Crear conversación con mensajes
        conv_id = create_conversation(self.database, work_id="work-1", profile_id="companion", title="Charla Antigua")
        add_message(self.database, conversation_id=conv_id, role="user", content="Pregunta sobre la Neolengua")
        add_message(self.database, conversation_id=conv_id, role="assistant", content="La Neolengua limita el pensamiento.")

        # Seleccionar la conversación desde el botón
        self.bot.process_update({
            "update_id": 1,
            "callback_query": {
                "id": "cb-resume",
                "from": {"id": 1001},
                "message": {"message_id": 5, "chat": {"id": 1001}},
                "data": f"c:{conv_id}",
            },
        })

        # Sesión actualizada
        work_id, active_c = self.bot.get_session(1001)
        self.assertEqual(work_id, "work-1")
        self.assertEqual(active_c, conv_id)

        edited = self.client.edited_messages[0]
        self.assertIn("Charla Antigua", edited["text"])
        self.assertIn("Leer charla completa", str(edited["reply_markup"]))

        # El último intercambio completo se envía en un mensaje separado
        last_msg = self.client.sent_messages[-1]
        self.assertIn("Pregunta sobre la Neolengua", last_msg["text"])
        self.assertIn("La Neolengua limita el pensamiento", last_msg["text"])

        # Probar el botón de "Leer charla completa" (callback "hist:<id>")
        self.bot.process_update({
            "update_id": 2,
            "callback_query": {
                "id": "cb-hist",
                "from": {"id": 1001},
                "message": {"message_id": 6, "chat": {"id": 1001}},
                "data": f"hist:{conv_id}",
            },
        })
        history_msgs = [m for m in self.client.sent_messages if "Historial de la charla" in m["text"]]
        self.assertTrue(len(history_msgs) > 0)


    def test_generate_summary_action(self) -> None:
        conv_id = create_conversation(self.database, work_id="work-1", profile_id="companion", title="Tema Libertad")
        add_message(self.database, conversation_id=conv_id, role="user", content="¿Existe libre albedrío en Oceanía?")
        add_message(self.database, conversation_id=conv_id, role="assistant", content="No, el control es psicológico.")
        self.bot.set_session(1001, work_id="work-1", conversation_id=conv_id)

        mock_provider = MockAIProvider(answer="Tesis: En Oceanía no hay libre albedrío posible.")
        with patch.object(self.bot, "resolve_conversation_ai", return_value=mock_provider):
            self.bot.process_update({
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "from": {"id": 1001},
                    "chat": {"id": 1001},
                    "text": "/sintesis",
                },
            })

        # Debería haber enviado mensaje de "generando" y luego el resultado
        self.assertGreaterEqual(len(self.client.sent_messages), 2)
        summary_msg = self.client.sent_messages[-1]
        self.assertIn("Síntesis Guardada", summary_msg["text"])
        self.assertIn("Tesis: En Oceanía no hay libre albedrío posible", summary_msg["text"])

    def test_set_my_commands_called_on_init(self) -> None:
        self.assertTrue(hasattr(self.client, "registered_commands"))
        commands = [c["command"] for c in self.client.registered_commands]
        self.assertIn("nueva", commands)
        self.assertIn("libros", commands)
        self.assertIn("sintesis", commands)

    def test_nueva_command_flow(self) -> None:
        # Caso 1: sin obra activa en sesión -> invita a elegir libro y muestra catálogo
        self.bot.process_update({
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 1001},
                "chat": {"id": 1001},
                "text": "/nueva",
            },
        })
        self.assertGreaterEqual(len(self.client.sent_messages), 2)
        intro = self.client.sent_messages[-2]
        catalog = self.client.sent_messages[-1]
        self.assertIn("Iniciar nueva charla", intro["text"])
        self.assertIn("Catálogo de Obras", catalog["text"])

        # Caso 2: con obra activa en sesión -> abre selector de perfiles
        self.bot.set_session(1001, work_id="work-1")
        self.client.sent_messages.clear()
        self.bot.process_update({
            "update_id": 2,
            "message": {
                "message_id": 11,
                "from": {"id": 1001},
                "chat": {"id": 1001},
                "text": "/nueva",
            },
        })
        self.assertEqual(len(self.client.sent_messages), 1)
        picker = self.client.sent_messages[0]
        self.assertIn("Elegí el perfil pedagógico", picker["text"])


if __name__ == "__main__":
    unittest.main()
