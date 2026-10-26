from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from .ai import AIError, AIProvider, DraftProvider, ResponsesProvider, load_environment_file, provider_from_environment, resolve_provider_for_profile
from .conversations import (
    ConversationError,
    add_message,
    build_prompt_packet,
    create_conversation,
    generate_and_save_conversation_summary,
    get_conversation,
    list_work_conversations,
)
from .db import connect_database, migrate_database
from .telegram_client import TelegramAPIError, TelegramClient, markdown_to_telegram_html

logger = logging.getLogger(__name__)

DEFAULT_BOT_COMMANDS = [
    {"command": "libros", "description": "📚 Catálogo de libros"},
    {"command": "nueva", "description": "➕ Iniciar nueva charla"},
    {"command": "historial", "description": "📜 Ver la charla completa"},
    {"command": "buscar", "description": "🔍 Buscar libro por título o autor"},
    {"command": "charla", "description": "💬 Ver conversación activa"},
    {"command": "sintesis", "description": "🧠 Generar síntesis de la charla"},
    {"command": "cerrar", "description": "🚪 Salir de la charla activa"},
    {"command": "start", "description": "🏠 Menú principal"},
]

DISPLAY_TITLE_SQL = (
    "COALESCE(NULLIF(TRIM(w.display_title), ''), "
    "REPLACE(w.preferred_title, '_', ' '))"
)


class TelegramBotService:
    def __init__(
        self,
        database: Path | str,
        client: TelegramClient,
        allowed_user_id: int | None = None,
    ) -> None:
        self.database_path = Path(database).expanduser().resolve()
        self.client = client
        self.allowed_user_id = allowed_user_id
        # Asegurar migraciones
        migrate_database(self.database_path)
        # Registrar menú de comandos en Telegram
        try:
            self.client.set_my_commands(DEFAULT_BOT_COMMANDS)
        except Exception as exc:
            logger.debug("No se pudieron registrar los comandos en Telegram: %s", exc)

    def _open_db(self) -> sqlite3.Connection:
        return connect_database(self.database_path)

    # --- Gestión de Sesión ---

    def get_session(self, user_id: int) -> tuple[str | None, str | None]:
        with self._open_db() as conn:
            row = conn.execute(
                "SELECT active_work_id, active_conversation_id FROM telegram_sessions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return row["active_work_id"], row["active_conversation_id"]
            return None, None

    def set_session(
        self,
        user_id: int,
        work_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        with self._open_db() as conn:
            conn.execute(
                """
                INSERT INTO telegram_sessions(user_id, active_work_id, active_conversation_id, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    active_work_id = excluded.active_work_id,
                    active_conversation_id = excluded.active_conversation_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, work_id, conversation_id),
            )
            conn.commit()

    # --- Consultas del Catálogo ---

    def list_works(self, offset: int = 0, limit: int = 5) -> tuple[list[dict[str, Any]], int]:
        with self._open_db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
            rows = conn.execute(
                f"""
                WITH authors AS (
                    SELECT e.work_id, GROUP_CONCAT(DISTINCT c.display_name) AS names
                    FROM editions e
                    JOIN edition_contributors ec ON ec.edition_id=e.id AND ec.role='author'
                    JOIN contributors c ON c.id=ec.contributor_id
                    GROUP BY e.work_id
                ), annotation_counts AS (
                    SELECT e.work_id, COUNT(a.id) AS total
                    FROM editions e LEFT JOIN annotations a ON a.edition_id=e.id
                    GROUP BY e.work_id
                )
                SELECT w.id, {DISPLAY_TITLE_SQL} AS title,
                       COALESCE(authors.names, '') AS authors,
                       COALESCE(annotation_counts.total, 0) AS annotation_count
                FROM works w
                LEFT JOIN authors ON authors.work_id=w.id
                LEFT JOIN annotation_counts ON annotation_counts.work_id=w.id
                ORDER BY {DISPLAY_TITLE_SQL} COLLATE NOCASE
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows], total

    def search_works(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        normalized = " ".join(query.replace("-", " ").replace("_", " ").split())
        pattern = f"%{normalized}%"
        with self._open_db() as conn:
            rows = conn.execute(
                f"""
                WITH authors AS (
                    SELECT e.work_id, GROUP_CONCAT(DISTINCT c.display_name) AS names
                    FROM editions e
                    JOIN edition_contributors ec ON ec.edition_id=e.id AND ec.role='author'
                    JOIN contributors c ON c.id=ec.contributor_id
                    GROUP BY e.work_id
                ), annotation_counts AS (
                    SELECT e.work_id, COUNT(a.id) AS total
                    FROM editions e LEFT JOIN annotations a ON a.edition_id=e.id
                    GROUP BY e.work_id
                )
                SELECT w.id, {DISPLAY_TITLE_SQL} AS title,
                       COALESCE(authors.names, '') AS authors,
                       COALESCE(annotation_counts.total, 0) AS annotation_count
                FROM works w
                LEFT JOIN authors ON authors.work_id=w.id
                LEFT JOIN annotation_counts ON annotation_counts.work_id=w.id
                WHERE {DISPLAY_TITLE_SQL} LIKE ? OR authors.names LIKE ?
                ORDER BY CASE WHEN LOWER({DISPLAY_TITLE_SQL})=LOWER(?) THEN 0 ELSE 1 END,
                         {DISPLAY_TITLE_SQL} COLLATE NOCASE
                LIMIT ?
                """,
                (pattern, pattern, normalized, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_work(self, work_id: str) -> dict[str, Any] | None:
        with self._open_db() as conn:
            row = conn.execute(
                f"""
                WITH authors AS (
                    SELECT e.work_id, GROUP_CONCAT(DISTINCT c.display_name) AS names
                    FROM editions e
                    JOIN edition_contributors ec ON ec.edition_id=e.id AND ec.role='author'
                    JOIN contributors c ON c.id=ec.contributor_id
                    GROUP BY e.work_id
                ), annotation_counts AS (
                    SELECT e.work_id, COUNT(a.id) AS total
                    FROM editions e LEFT JOIN annotations a ON a.edition_id=e.id
                    GROUP BY e.work_id
                )
                SELECT w.id, {DISPLAY_TITLE_SQL} AS title,
                       COALESCE(authors.names, '') AS authors,
                       COALESCE(annotation_counts.total, 0) AS annotation_count
                FROM works w
                LEFT JOIN authors ON authors.work_id=w.id
                LEFT JOIN annotation_counts ON annotation_counts.work_id=w.id
                WHERE w.id = ?
                """,
                (work_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_active_profiles(self) -> list[dict[str, Any]]:
        with self._open_db() as conn:
            rows = conn.execute(
                """
                SELECT id, name, description, is_default
                FROM ai_profiles
                WHERE is_archived = 0
                ORDER BY is_default DESC, name COLLATE NOCASE
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def resolve_conversation_ai(self, conversation_id: str) -> AIProvider:
        with self._open_db() as conn:
            row = conn.execute(
                """
                SELECT p.provider_id, p.model_override
                FROM reading_conversations c
                JOIN ai_profiles p ON c.profile_id = p.id
                WHERE c.id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if row and (row["provider_id"] or row["model_override"]):
                return resolve_provider_for_profile(row["provider_id"], row["model_override"])
        return provider_from_environment()

    # --- Vistas y Pantallas Telegram ---

    def send_welcome(self, chat_id: int, user_id: int) -> None:
        work_id, conv_id = self.get_session(user_id)
        active_status = "Ninguna charla activa."
        if conv_id:
            try:
                conv = get_conversation(self.database_path, conv_id)
                work = self.get_work(conv["work_id"])
                title = work["title"] if work else "Libro"
                active_status = f"Charla activa: *{conv['title']}*\nLibro: *{title}* ({conv['profile_name_snapshot']})"
            except Exception:
                active_status = "Ninguna charla activa."

        text = (
            "📚 *Biblioteca Kindle — Acompañante de Lectura*\n\n"
            f"{active_status}\n\n"
            "Comandos disponibles:\n"
            "• /libros — Ver catálogo de libros\n"
            "• /nueva — Iniciar una nueva charla\n"
            "• /buscar <título o autor> — Buscar una obra\n"
            "• /charla — Ver la conversación activa y últimos mensajes\n"
            "• /sintesis — Resumir la conversación actual\n"
            "• /cerrar — Salir de la charla activa\n\n"
            "O simplemente escribí el nombre de un libro para buscarlo."
        )
        keyboard: list[list[dict[str, str]]] = [
            [
                {"text": "📖 Ver libros", "callback_data": "page:0"},
                {"text": "➕ Nueva charla", "callback_data": f"new:{work_id}" if work_id else "new_prompt"},
            ],
        ]
        if conv_id:
            keyboard.append([{"text": "💬 Ir a la charla activa", "callback_data": f"c:{conv_id}"}])
            keyboard.append([{"text": "🧠 Síntesis de esta charla", "callback_data": "sum"}])

        self.client.send_message(chat_id, text, reply_markup={"inline_keyboard": keyboard}, parse_mode="Markdown")

    def handle_new_conversation_command(self, chat_id: int, user_id: int) -> None:
        work_id, _ = self.get_session(user_id)
        if work_id:
            self.show_profile_picker(chat_id, None, work_id)
        else:
            self.client.send_message(
                chat_id,
                "➕ *Iniciar nueva charla*\n\nElegí el libro sobre el cual querés conversar:",
                parse_mode="Markdown",
            )
            self.show_catalog(chat_id, None, 0)

    def show_catalog(self, chat_id: int, message_id: int | None, offset: int = 0) -> None:
        limit = 5
        works, total = self.list_works(offset=offset, limit=limit)
        if not works:
            text = "No hay libros cargados en la biblioteca."
            if message_id:
                self.client.edit_message_text(chat_id, message_id, text)
            else:
                self.client.send_message(chat_id, text)
            return

        text = f"📚 *Catálogo de Obras* (mostrando {offset + 1}–{min(offset + len(works), total)} de {total}):\n\nElegí un libro para ver sus charlas o comenzar una nueva:"
        buttons: list[list[dict[str, str]]] = []
        for w in works:
            label = f"📖 {w['title'][:32]}"
            if w.get("authors"):
                label += f" — {w['authors'][:20]}"
            buttons.append([{"text": label, "callback_data": f"w:{w['id']}"}])

        nav_row: list[dict[str, str]] = []
        if offset > 0:
            nav_row.append({"text": "⬅️ Anterior", "callback_data": f"page:{max(0, offset - limit)}"})
        if offset + limit < total:
            nav_row.append({"text": "Siguiente ➡️", "callback_data": f"page:{offset + limit}"})
        if nav_row:
            buttons.append(nav_row)

        buttons.append([{"text": "🏠 Menú principal", "callback_data": "menu"}])

        reply_markup = {"inline_keyboard": buttons}
        if message_id:
            self.client.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            self.client.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")

    def show_search_results(self, chat_id: int, query: str) -> None:
        works = self.search_works(query, limit=6)
        if not works:
            self.client.send_message(
                chat_id,
                f"No encontré obras que coincidan con *{query}*.\nProbá con /libros para ver el catálogo completo.",
                parse_mode="Markdown",
            )
            return

        text = f"🔍 *Resultados para «{query}»*:\nElegí el libro con el que querés conversar:"
        buttons: list[list[dict[str, str]]] = []
        for w in works:
            label = f"📖 {w['title'][:32]}"
            if w.get("authors"):
                label += f" — {w['authors'][:20]}"
            buttons.append([{"text": label, "callback_data": f"w:{w['id']}"}])

        buttons.append([{"text": "📚 Ver todo el catálogo", "callback_data": "page:0"}])
        self.client.send_message(chat_id, text, reply_markup={"inline_keyboard": buttons}, parse_mode="Markdown")

    def show_work_menu(self, chat_id: int, message_id: int | None, work_id: str, user_id: int) -> None:
        work = self.get_work(work_id)
        if not work:
            self.client.send_message(chat_id, "Obra no encontrada.")
            return

        self.set_session(user_id, work_id=work_id, conversation_id=None)
        convs = list_work_conversations(self.database_path, work_id)

        author_str = f" de *{work['authors']}*" if work.get("authors") else ""
        text = (
            f"📖 *{work['title']}*{author_str}\n"
            f"📝 {work.get('annotation_count', 0)} subrayados y notas en el Kindle.\n\n"
            "¿Qué querés hacer?"
        )

        buttons: list[list[dict[str, str]]] = [
            [{"text": "➕ Iniciar nueva charla", "callback_data": f"new:{work_id}"}]
        ]

        if convs:
            for c in convs[:5]:  # Máximo 5 más recientes
                title = c.get("title") or "Sin título"
                profile = c.get("profile_name_snapshot") or "Compañero"
                buttons.append([{"text": f"💬 {title[:28]} ({profile})", "callback_data": f"c:{c['id']}"}])

        buttons.append([{"text": "⬅️ Volver a libros", "callback_data": "page:0"}])

        reply_markup = {"inline_keyboard": buttons}
        if message_id:
            self.client.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            self.client.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")

    def show_profile_picker(self, chat_id: int, message_id: int | None, work_id: str) -> None:
        work = self.get_work(work_id)
        work_title = work["title"] if work else "este libro"
        profiles = self.list_active_profiles()

        text = (
            f"👤 *Elegí el perfil pedagógico para conversar sobre*\n"
            f"*{work_title}*:\n\n"
            "Cada perfil adopta un enfoque dialéctico y metodológico distinto."
        )

        buttons: list[list[dict[str, str]]] = []
        for p in profiles:
            label = f"🎭 {p['name']}"
            if p.get("is_default"):
                label += " (por defecto)"
            buttons.append([{"text": label, "callback_data": f"p:{p['id']}"}])

        buttons.append([{"text": "⬅️ Volver al libro", "callback_data": f"w:{work_id}"}])

        reply_markup = {"inline_keyboard": buttons}
        if message_id:
            self.client.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            self.client.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")

    def activate_conversation(self, chat_id: int, message_id: int | None, conversation_id: str, user_id: int) -> None:
        try:
            conv = get_conversation(self.database_path, conversation_id)
        except ConversationError:
            self.client.send_message(chat_id, "La conversación no existe o fue eliminada.")
            return

        work = self.get_work(conv["work_id"])
        work_title = work["title"] if work else "Libro"
        self.set_session(user_id, work_id=conv["work_id"], conversation_id=conversation_id)

        messages = conv.get("messages", [])

        text = (
            f"💬 <b>{conv['title']}</b>\n"
            f"📖 Obra: <b>{work_title}</b>\n"
            f"🎭 Perfil: <b>{conv['profile_name_snapshot']}</b>\n"
            f"📊 Historial: {len(messages)} mensaje(s) registrado(s).\n\n"
            "✨ <b>Charla activa</b>: Escribí cualquier mensaje o pregunta para continuar el diálogo."
        )

        buttons = [
            [
                {"text": "📜 Leer charla completa", "callback_data": f"hist:{conversation_id}"},
                {"text": "🧠 Síntesis", "callback_data": "sum"},
            ],
            [
                {"text": "➕ Nueva charla", "callback_data": f"new:{conv['work_id']}"},
                {"text": "⬅️ Volver al libro", "callback_data": f"w:{conv['work_id']}"},
            ],
            [
                {"text": "📚 Catálogo de libros", "callback_data": "page:0"},
            ],
        ]

        reply_markup = {"inline_keyboard": buttons}
        if message_id:
            self.client.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            self.client.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")

        # Mostrar el último intercambio completo sin recortes
        if messages:
            last_msg = messages[-1]
            if last_msg["role"] == "assistant" and len(messages) >= 2 and messages[-2]["role"] == "user":
                user_q = messages[-2]
                text_last = (
                    "<i>Último intercambio:</i>\n\n"
                    f"👤 <b>Tú:</b>\n{markdown_to_telegram_html(user_q['content'])}\n\n"
                    f"🤖 <b>{conv['profile_name_snapshot']}:</b>\n{markdown_to_telegram_html(last_msg['content'])}"
                )
            else:
                role_label = "👤 <b>Tú:</b>" if last_msg["role"] == "user" else f"🤖 <b>{conv['profile_name_snapshot']}:</b>"
                text_last = f"<i>Último mensaje:</i>\n\n{role_label}\n{markdown_to_telegram_html(last_msg['content'])}"

            self.client.send_message(chat_id, text_last, parse_mode="HTML")

    def send_conversation_history(self, chat_id: int, user_id: int, conversation_id: str | None = None) -> None:
        if not conversation_id:
            _, conversation_id = self.get_session(user_id)
        if not conversation_id:
            self.client.send_message(chat_id, "No tenés ninguna conversación activa. Usá /libros para comenzar una.")
            return

        try:
            conv = get_conversation(self.database_path, conversation_id)
        except ConversationError:
            self.client.send_message(chat_id, "La conversación no existe.")
            return

        messages = conv.get("messages", [])
        if not messages:
            self.client.send_message(chat_id, "Esta conversación aún no tiene mensajes.")
            return

        work = self.get_work(conv["work_id"])
        work_title = work["title"] if work else "Libro"

        self.client.send_message(
            chat_id,
            f"📜 <b>Historial de la charla:</b> <i>{conv['title']}</i>\n"
            f"📖 Obra: <b>{work_title}</b> | 🎭 Perfil: <b>{conv['profile_name_snapshot']}</b>",
            parse_mode="HTML",
        )

        for m in messages:
            role_label = "👤 <b>Tú:</b>" if m["role"] == "user" else f"🤖 <b>{conv['profile_name_snapshot']}:</b>"
            content_html = markdown_to_telegram_html(m["content"])
            full_text = f"{role_label}\n{content_html}"
            self.client.send_message(chat_id, full_text, parse_mode="HTML")

    def generate_summary_for_active(self, chat_id: int, user_id: int) -> None:
        _, conv_id = self.get_session(user_id)
        if not conv_id:
            self.client.send_message(chat_id, "No tenés ninguna conversación activa para sintetizar.")
            return

        try:
            conv = get_conversation(self.database_path, conv_id)
            if not conv.get("messages"):
                self.client.send_message(chat_id, "Esta conversación aún no tiene mensajes para resumir.")
                return

            self.client.send_message(chat_id, "🧠 Generando síntesis estructurada de la conversación con la IA…")
            ai_provider = self.resolve_conversation_ai(conv_id)
            summary_data = generate_and_save_conversation_summary(
                self.database_path, conv_id, provider=ai_provider
            )
            formatted_summary = markdown_to_telegram_html(summary_data["summary"])
            text = (
                f"🧠 <b>Síntesis Guardada — {conv['title']}</b>\n\n"
                f"{formatted_summary}\n\n"
                "<i>Esta síntesis ya quedó guardada y está disponible para conectar con otras charlas de este libro.</i>"
            )
            buttons = [
                [{"text": "💬 Continuar charlando", "callback_data": f"c:{conv_id}"}],
                [{"text": "⬅️ Volver al libro", "callback_data": f"w:{conv['work_id']}"}],
            ]
            self.client.send_message(chat_id, text, reply_markup={"inline_keyboard": buttons}, parse_mode="HTML")
        except Exception as exc:
            logger.exception("Error al generar síntesis")
            self.client.send_message(chat_id, f"❌ Error al generar la síntesis: {exc}")

    def handle_user_text_message(self, chat_id: int, user_id: int, text: str) -> None:
        work_id, conv_id = self.get_session(user_id)
        # Si no hay conversación activa, tratar el texto como búsqueda de libros
        if not conv_id:
            self.show_search_results(chat_id, text)
            return

        # Hay conversación activa: enviar al modelo y guardar
        try:
            conv = get_conversation(self.database_path, conv_id)
        except Exception:
            self.set_session(user_id, None, None)
            self.show_search_results(chat_id, text)
            return

        try:
            # 1. Registrar mensaje del usuario
            add_message(self.database_path, conversation_id=conv_id, role="user", content=text)

            # 2. Armar paquete de prompt y consultar proveedor de IA
            packet = build_prompt_packet(self.database_path, conv_id)
            ai_provider = self.resolve_conversation_ai(conv_id)

            if not ai_provider.ready:
                answer = "El proveedor de IA no está configurado o está en modo borrador. Revisá tu archivo .env."
            else:
                answer = ai_provider.respond(packet)

            # 3. Registrar respuesta del asistente
            add_message(self.database_path, conversation_id=conv_id, role="assistant", content=answer)

            # 4. Enviar a Telegram con formato HTML adaptado
            keyboard = [
                [
                    {"text": "➕ Nueva charla", "callback_data": f"new:{conv['work_id']}"},
                    {"text": "🧠 Síntesis", "callback_data": "sum"},
                ],
                [
                    {"text": "⬅️ Volver al libro", "callback_data": f"w:{conv['work_id']}"},
                    {"text": "📚 Catálogo", "callback_data": "page:0"},
                ],
            ]
            formatted_answer = markdown_to_telegram_html(answer)
            self.client.send_message(
                chat_id,
                formatted_answer,
                reply_markup={"inline_keyboard": keyboard},
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.exception("Error al procesar mensaje de IA")
            self.client.send_message(chat_id, f"❌ Ocurrió un error al responder: {exc}")

    # --- Procesamiento Principal de Updates ---

    def process_update(self, update: dict[str, Any]) -> None:
        # 1. Callback query (clic en botón)
        if "callback_query" in update:
            cb = update["callback_query"]
            cb_id = cb["id"]
            user = cb.get("from", {})
            user_id = user.get("id")
            data = cb.get("data", "")
            message = cb.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            message_id = message.get("message_id")

            if self.allowed_user_id and user_id != self.allowed_user_id:
                self.client.answer_callback_query(cb_id, "Acceso no autorizado", show_alert=True)
                return

            self.client.answer_callback_query(cb_id)

            if data == "menu":
                self.send_welcome(chat_id, user_id)
            elif data.startswith("page:"):
                offset = int(data.split(":")[1])
                self.show_catalog(chat_id, message_id, offset=offset)
            elif data.startswith("w:"):
                work_id = data.split(":", 1)[1]
                self.show_work_menu(chat_id, message_id, work_id, user_id)
            elif data.startswith("new:"):
                work_id = data.split(":", 1)[1]
                self.show_profile_picker(chat_id, message_id, work_id)
            elif data == "new_prompt":
                self.handle_new_conversation_command(chat_id, user_id)
            elif data.startswith("p:"):
                profile_id = data.split(":", 1)[1]
                work_id, _ = self.get_session(user_id)
                if not work_id:
                    self.show_catalog(chat_id, message_id, 0)
                    return
                conv_id = create_conversation(self.database_path, work_id=work_id, profile_id=profile_id)
                self.activate_conversation(chat_id, message_id, conv_id, user_id)
            elif data.startswith("c:"):
                conv_id = data.split(":", 1)[1]
                self.activate_conversation(chat_id, message_id, conv_id, user_id)
            elif data.startswith("hist:"):
                conv_id = data.split(":", 1)[1]
                self.send_conversation_history(chat_id, user_id, conv_id)
            elif data == "sum":
                self.generate_summary_for_active(chat_id, user_id)
            return

        # 2. Mensaje normal
        if "message" in update:
            msg = update["message"]
            user = msg.get("from", {})
            user_id = user.get("id")
            chat_id = msg.get("chat", {}).get("id")
            text = (msg.get("text") or "").strip()

            if self.allowed_user_id and user_id != self.allowed_user_id:
                self.client.send_message(chat_id, "⛔ Este bot es de acceso privado para el dueño de la biblioteca.")
                return

            if not text:
                return

            if text in {"/start", "/menu", "/ayuda"}:
                self.send_welcome(chat_id, user_id)
            elif text.startswith("/libros"):
                self.show_catalog(chat_id, None, 0)
            elif text in {"/nueva", "/nuevo"}:
                self.handle_new_conversation_command(chat_id, user_id)
            elif text in {"/historial", "/completa", "/leer"}:
                self.send_conversation_history(chat_id, user_id)
            elif text.startswith("/buscar"):
                query = text[7:].strip()
                if query:
                    self.show_search_results(chat_id, query)
                else:
                    self.client.send_message(chat_id, "Uso: `/buscar <título o autor>`", parse_mode="Markdown")
            elif text in {"/charla", "/conversacion"}:
                _, conv_id = self.get_session(user_id)
                if conv_id:
                    self.activate_conversation(chat_id, None, conv_id, user_id)
                else:
                    self.client.send_message(chat_id, "No tenés ninguna conversación activa. Usá /libros para comenzar una.")
            elif text in {"/sintesis", "/resumen"}:
                self.generate_summary_for_active(chat_id, user_id)
            elif text in {"/cerrar", "/salir"}:
                self.set_session(user_id, None, None)
                self.client.send_message(chat_id, "Has salido de la conversación activa. Usá /libros para ver tu biblioteca.")
            else:
                self.handle_user_text_message(chat_id, user_id, text)

    def run_polling(self, interval: float = 1.0) -> None:
        """Bucle de sondeo continuo (long polling)."""
        logger.info("Iniciando sondeo de Telegram Bot...")
        offset: int | None = None
        while True:
            try:
                updates = self.client.get_updates(offset=offset, timeout=30)
                for update in updates:
                    update_id = update["update_id"]
                    offset = update_id + 1
                    try:
                        self.process_update(update)
                    except Exception as exc:
                        logger.exception("Error al procesar update %s: %s", update_id, exc)
            except TelegramAPIError as exc:
                logger.error("Error en polling de Telegram: %s", exc)
                time.sleep(3.0)
            except Exception as exc:
                logger.exception("Error inesperado en polling: %s", exc)
                time.sleep(3.0)
            time.sleep(interval)
