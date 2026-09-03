from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from .db import connect_database
from .ai import PromptPacket


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
            display_title = connection.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(display_title), ''),
                                REPLACE(preferred_title, '_', ' '))
                FROM works WHERE id = ?
                """,
                (work_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO conversation_context_sources(
                    id, conversation_id, source_type, source_id,
                    label_snapshot, content_snapshot
                ) VALUES (?, ?, 'work', ?, 'Ficha del libro', ?)
                """,
                (str(uuid.uuid4()), identifier, work_id, f"Título: {display_title}"),
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
        result["messages"] = []
        for message in messages:
            item = dict(message)
            item["library_sources"] = [
                dict(row) for row in connection.execute(
                    """
                    SELECT source_type, source_id, work_id, work_title_snapshot AS work_title,
                           label_snapshot AS label, content_snapshot AS content,
                           reference_snapshot AS reference, relevance_score AS score
                    FROM conversation_message_sources
                    WHERE message_id=? ORDER BY relevance_score DESC, id
                    """,
                    (message["id"],),
                )
            ]
            result["messages"].append(item)
        result["context_sources"] = [
            dict(row)
            for row in connection.execute(
                """
                SELECT source_type, source_id, label_snapshot, content_snapshot, is_pinned
                FROM conversation_context_sources
                WHERE conversation_id = ? ORDER BY source_type, created_at, id
                """,
                (conversation_id,),
            )
        ]
        return result
    finally:
        connection.close()


def context_options(database: Path | str, conversation_id: str) -> dict:
    connection = _open_database(database)
    try:
        conversation = connection.execute(
            "SELECT work_id FROM reading_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if conversation is None:
            raise ConversationError("La conversación no existe")
        work_id = conversation["work_id"]
        notes = [dict(row) for row in connection.execute(
            """
            SELECT id, body AS content FROM personal_notes
            WHERE target_type = 'work' AND target_id = ?
            ORDER BY created_at DESC, id
            """,
            (work_id,),
        )]
        annotations = [dict(row) for row in connection.execute(
            """
            SELECT an.id, an.kind,
                   COALESCE(NULLIF(TRIM(an.text), ''), NULLIF(TRIM(an.note_text), ''),
                            'Anotación sin texto recuperable') AS content
            FROM annotations an JOIN editions e ON e.id = an.edition_id
            WHERE e.work_id = ? ORDER BY COALESCE(an.native_created_at, an.created_at) DESC
            """,
            (work_id,),
        )]
        selected = connection.execute(
            """
            SELECT source_type, source_id FROM conversation_context_sources
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchall()
        return {
            "notes": notes,
            "annotations": annotations,
            "selected": {row["source_type"]: [] for row in selected} | {
                kind: [row["source_id"] for row in selected if row["source_type"] == kind]
                for kind in {row["source_type"] for row in selected}
            },
        }
    finally:
        connection.close()


def update_context(
    database: Path | str,
    conversation_id: str,
    *,
    personal_note_ids: object,
    annotation_ids: object,
) -> None:
    if not isinstance(personal_note_ids, list) or not all(isinstance(item, str) for item in personal_note_ids):
        raise ConversationError("La selección de notas no es válida")
    if not isinstance(annotation_ids, list) or not all(isinstance(item, str) for item in annotation_ids):
        raise ConversationError("La selección de anotaciones no es válida")
    note_ids = list(dict.fromkeys(personal_note_ids))
    selected_annotation_ids = list(dict.fromkeys(annotation_ids))
    connection = _open_database(database)
    try:
        conversation = connection.execute(
            "SELECT work_id FROM reading_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if conversation is None:
            raise ConversationError("La conversación no existe")
        work_id = conversation["work_id"]
        notes = {row["id"]: row for row in connection.execute(
            "SELECT id, body FROM personal_notes WHERE target_type = 'work' AND target_id = ?",
            (work_id,),
        )}
        annotations = {row["id"]: row for row in connection.execute(
            """
            SELECT an.id, an.kind, COALESCE(NULLIF(TRIM(an.text), ''),
                   NULLIF(TRIM(an.note_text), ''), 'Anotación sin texto recuperable') AS content
            FROM annotations an JOIN editions e ON e.id = an.edition_id WHERE e.work_id = ?
            """,
            (work_id,),
        )}
        if any(identifier not in notes for identifier in note_ids):
            raise ConversationError("Una nota seleccionada no pertenece a este libro")
        if any(identifier not in annotations for identifier in selected_annotation_ids):
            raise ConversationError("Una anotación seleccionada no pertenece a este libro")
        with connection:
            connection.execute(
                "DELETE FROM conversation_context_sources WHERE conversation_id = ? AND source_type != 'work' AND is_pinned = 0",
                (conversation_id,),
            )
            connection.executemany(
                """
                INSERT INTO conversation_context_sources(
                    id, conversation_id, source_type, source_id, label_snapshot, content_snapshot
                ) VALUES (?, ?, 'personal_note', ?, 'Nota propia', ?)
                """,
                [(str(uuid.uuid4()), conversation_id, identifier, notes[identifier]["body"]) for identifier in note_ids],
            )
            connection.executemany(
                """
                INSERT INTO conversation_context_sources(
                    id, conversation_id, source_type, source_id, label_snapshot, content_snapshot
                ) VALUES (?, ?, 'annotation', ?, ?, ?)
                """,
                [(str(uuid.uuid4()), conversation_id, identifier, annotations[identifier]["kind"], annotations[identifier]["content"]) for identifier in selected_annotation_ids],
            )
    finally:
        connection.close()


def attach_library_sources(
    database: Path | str, message_id: str, sources: list[dict]
) -> None:
    connection = _open_database(database)
    try:
        if connection.execute(
            "SELECT 1 FROM conversation_messages WHERE id=?", (message_id,)
        ).fetchone() is None:
            raise ConversationError("El mensaje no existe")
        with connection:
            connection.executemany(
                """
                INSERT INTO conversation_message_sources(
                    id,message_id,source_type,source_id,work_id,work_title_snapshot,
                    label_snapshot,content_snapshot,reference_snapshot,relevance_score
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (str(uuid.uuid4()), message_id, item["source_type"], item["source_id"],
                     item["work_id"], item["work_title"], item["label"], item["content"],
                     item.get("reference"), item["score"])
                    for item in sources
                ],
            )
    finally:
        connection.close()


def pin_library_sources(
    database: Path | str, conversation_id: str, sources: list[dict]
) -> int:
    pinnable = [item for item in sources if item["source_type"] in {"work", "personal_note", "annotation"}]
    connection = _open_database(database)
    try:
        if connection.execute(
            "SELECT 1 FROM reading_conversations WHERE id=?", (conversation_id,)
        ).fetchone() is None:
            raise ConversationError("La conversación no existe")
        with connection:
            for item in pinnable:
                connection.execute(
                    """
                    INSERT INTO conversation_context_sources(
                        id,conversation_id,source_type,source_id,label_snapshot,
                        content_snapshot,is_pinned
                    ) VALUES (?,?,?,?,?,?,1)
                    ON CONFLICT(conversation_id,source_type,source_id) DO UPDATE SET
                        label_snapshot=excluded.label_snapshot,
                        content_snapshot=excluded.content_snapshot,
                        is_pinned=1
                    """,
                    (str(uuid.uuid4()), conversation_id, item["source_type"], item["source_id"],
                     f"{item['label']} · {item['work_title']}", item["content"]),
                )
        return len(pinnable)
    finally:
        connection.close()


def build_prompt_packet(
    database: Path | str,
    conversation_id: str,
    *,
    library_sources: list[dict] | None = None,
) -> PromptPacket:
    conversation = get_conversation(database, conversation_id)
    sources = "\n\n".join(
        f"[{item['label_snapshot']}]\n{item['content_snapshot']}"
        for item in conversation["context_sources"]
    )
    instructions = (
        f"{conversation['profile_prompt_snapshot']}\n\n"
        "Trabajá como acompañante de lectura, no como autoridad. Distinguí datos del contexto, "
        "inferencias e hipótesis. Si el contexto no alcanza, decilo; no inventes contenido del libro. "
        "Antes de afirmar que una selección no llegó, revisá el bloque CONTEXTO VIGENTE situado "
        "inmediatamente antes de la última pregunta. "
        "Citá la evidencia recuperada usando sus identificadores [B1], [B2], etc. "
        "Todo lo que no esté respaldado por esas fuentes es conocimiento general o una hipótesis."
    )
    messages = [{"role": item["role"], "content": item["content"]} for item in conversation["messages"]]
    automatic_parts = []
    for index, item in enumerate(library_sources or [], 1):
        reference = f" · {item['reference']}" if item.get("reference") else ""
        automatic_parts.append(
            f"[B{index}] {item['label']} · {item['work_title']}{reference}\n{item['content']}"
        )
    automatic = "\n\n".join(automatic_parts)
    context_content = "MATERIAL SELECCIONADO PARA ESTA CONVERSACIÓN:\n\n" + sources
    if automatic:
        context_content += "\n\nEVIDENCIA RECUPERADA DE LA BIBLIOTECA PARA ESTA PREGUNTA:\n\n" + automatic
    context_message = {
        "role": "user",
        "content": (
            "CONTEXTO VIGENTE PARA LA PRÓXIMA PREGUNTA. Este material fue "
            "seleccionado por el usuario y está disponible ahora:\n\n" + context_content
        ),
    }
    if messages and messages[-1]["role"] == "user":
        prompt_input = [*messages[:-1], context_message, messages[-1]]
    else:
        prompt_input = [*messages, context_message]
    return PromptPacket(instructions=instructions, input=prompt_input)


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
