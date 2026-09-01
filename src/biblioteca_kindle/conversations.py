from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from .db import connect_database


class ConversationError(RuntimeError):
    pass


def _open_database(path: Path | str) -> sqlite3.Connection:
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        raise ConversationError("La base SQLite todavía no existe")
    return connect_database(database)


def _clean_text(value: object, label: str, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ConversationError(f"{label} debe ser texto")
    text = value.strip()
    if required and not text:
        raise ConversationError(f"{label} no puede estar vacío")
    return text


def create_conversation(
    database: Path | str,
    *,
    work_id: str,
    profile_id: str,
    title: object = "",
) -> str:
    conversation_title = _clean_text(title, "El título") or None
    connection = _open_database(database)
    try:
        work = connection.execute(
            "SELECT 1 FROM works WHERE id = ?", (work_id,)
        ).fetchone()
        if work is None:
            raise ConversationError("La obra no existe")
        profile = connection.execute(
            "SELECT name, prompt, is_archived FROM ai_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if profile is None:
            raise ConversationError("El perfil de conversación no existe")
        if profile["is_archived"]:
            raise ConversationError("No se puede iniciar una conversación con un perfil archivado")

        identifier = str(uuid.uuid4())
        with connection:
            connection.execute(
                """
                INSERT INTO reading_conversations(
                    id, work_id, profile_id, profile_name_snapshot,
                    profile_prompt_snapshot, title
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    work_id,
                    profile_id,
                    profile["name"],
                    profile["prompt"],
                    conversation_title,
                ),
            )
        return identifier
    finally:
        connection.close()


def add_message(
    database: Path | str,
    *,
    conversation_id: str,
    role: str,
    content: object,
) -> str:
    if role not in {"user", "assistant"}:
        raise ConversationError("El rol debe ser user o assistant")
    message_content = _clean_text(content, "El mensaje", required=True)
    connection = _open_database(database)
    try:
        identifier = str(uuid.uuid4())
        connection.execute("BEGIN IMMEDIATE")
        conversation = connection.execute(
            "SELECT status FROM reading_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if conversation is None:
            raise ConversationError("La conversación no existe")
        if conversation["status"] != "active":
            raise ConversationError("La conversación está archivada")
        sequence = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1
            FROM conversation_messages WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO conversation_messages(
                id, conversation_id, sequence, role, content
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (identifier, conversation_id, sequence, role, message_content),
        )
        connection.execute(
            """
            UPDATE reading_conversations
            SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (conversation_id,),
        )
        connection.commit()
        return identifier
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_conversation(database: Path | str, conversation_id: str) -> dict:
    connection = _open_database(database)
    try:
        conversation = connection.execute(
            "SELECT * FROM reading_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if conversation is None:
            raise ConversationError("La conversación no existe")
        messages = connection.execute(
            """
            SELECT id, sequence, role, content, created_at
            FROM conversation_messages
            WHERE conversation_id = ? ORDER BY sequence
            """,
            (conversation_id,),
        ).fetchall()
        result = dict(conversation)
        result["messages"] = [dict(message) for message in messages]
        return result
    finally:
        connection.close()


def list_work_conversations(database: Path | str, work_id: str) -> list[dict]:
    connection = _open_database(database)
    try:
        if connection.execute(
            "SELECT 1 FROM works WHERE id = ?", (work_id,)
        ).fetchone() is None:
            raise ConversationError("La obra no existe")
        rows = connection.execute(
            """
            SELECT rc.id, rc.title, rc.profile_id, rc.profile_name_snapshot,
                   rc.status, rc.created_at, rc.updated_at,
                   COUNT(cm.id) AS message_count
            FROM reading_conversations rc
            LEFT JOIN conversation_messages cm ON cm.conversation_id = rc.id
            WHERE rc.work_id = ?
            GROUP BY rc.id
            ORDER BY rc.updated_at DESC, rc.created_at DESC, rc.id
            """,
            (work_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()
