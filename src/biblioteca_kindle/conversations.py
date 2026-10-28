from __future__ import annotations

import sqlite3
import re
import uuid
import json
from pathlib import Path

from .db import connect_database
from .ai import PromptPacket, AIProvider, resolve_provider_for_profile
from .companion_actions import get_companion_action


class ConversationError(RuntimeError):
    pass


PAGE_REFERENCE = re.compile(r"\b(?:page|página)\s+(\d+)", re.IGNORECASE)
LOCATION_REFERENCE = re.compile(
    r"\b(?:location|ubicación|posición)\s+(\d+)(?:\s*[-–]\s*(\d+))?",
    re.IGNORECASE,
)

DEFAULT_CONVERSATION_TITLE = "Nueva conversación"
MAX_CONVERSATION_TITLE_LENGTH = 120
MAX_AUTOMATIC_TITLE_LENGTH = 55

CONVERSATION_SUMMARY_PROMPT = """\
Sos un sintetizador analítico de lecturas. Tu tarea es generar una SÍNTESIS EJECUTIVA y ESTRUCTURADA de una conversación de lectura entre un lector y un asistente ({profile_name}) sobre la obra «{work_title}».

La síntesis debe ser clara, densa y tener entre 80 y 150 palabras.
Debe estructurarse obligatoriamente en tres puntos concisos:
1. DILEMA O TEMA CENTRAL: Qué cuestión, escena o problema de la obra se debatió.
2. POSTURA Y ARGUMENTOS: Qué tesis o perspectiva sostuvo {profile_name} y qué acuerdos o desacuerdos surgieron con el lector.
3. PREGUNTAS ABIERTAS: Qué tensión o interrogante quedó planteado para capítulos o lecturas posteriores.

Respondé directamente con los 3 puntos sintetizados, sin introducciones ni despedidas meta.
"""

_GREETING_PREFIX = re.compile(
    r"^(?:hola|buenas(?: tardes| noches| días)?|buen día)\b[\s,!.¡¿-]*",
    re.IGNORECASE,
)
_TITLE_PREFIXES = (
    re.compile(
        r"^(?:dame|decime|dime|explicame|explícame|contame|cuéntame|"
        r"analizá|analiza|mostrame|muéstrame)\s+",
        re.IGNORECASE,
    ),
    re.compile(r"^ayudame\s+a\s+entender\s+", re.IGNORECASE),
    re.compile(r"^ayúdame\s+a\s+entender\s+", re.IGNORECASE),
    re.compile(r"^quiero\s+saber\s+", re.IGNORECASE),
    re.compile(
        r"^(?:quiero|me gustaría|quisiera)\s+(?:que\s+)?"
        r"(?:hablemos|hablar|conversemos|conversar|charlemos|charlar|"
        r"pensemos|pensar|exploremos|explorar|analicemos|analizar)\s+"
        r"(?:sobre|acerca de|de)\s+",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:podemos|podríamos)\s+(?:hablar|conversar|charlar|pensar|"
        r"explorar|analizar)\s+(?:sobre|acerca de|de)\s+",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:te\s+)?(?:quiero|quería)\s+(?:preguntar|consultar)\s+"
        r"(?:sobre|acerca de|por)\s+",
        re.IGNORECASE,
    ),
    re.compile(r"^una\s+pregunta\s+(?:sobre|acerca de)\s+", re.IGNORECASE),
    re.compile(
        r"^¿?\s*(?:qué|que)\s+(?:pensás|piensas|podés\s+decirme|"
        r"puedes\s+decirme)\s+(?:sobre|de)\s+",
        re.IGNORECASE,
    ),
)


def _context_reference(source: str | None) -> str | None:
    text = source or ""
    page = PAGE_REFERENCE.search(text)
    location = LOCATION_REFERENCE.search(text)
    parts = []
    if page:
        parts.append(f"Página {page.group(1)}")
    if location:
        start, end = location.groups()
        parts.append(f"Ubicación {start}{f'–{end}' if end else ''}")
    return " · ".join(parts) or None


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


def _clean_conversation_title(value: object, *, required: bool = False) -> str:
    title = _clean_text(value, "El título", required=required)
    if len(title) > MAX_CONVERSATION_TITLE_LENGTH:
        raise ConversationError(
            f"El título no puede superar {MAX_CONVERSATION_TITLE_LENGTH} caracteres"
        )
    return title


def _truncate_title(text: str, limit: int = MAX_AUTOMATIC_TITLE_LENGTH) -> str:
    if len(text) <= limit:
        return text
    candidate = text[: limit + 1].rsplit(" ", 1)[0].strip()
    return candidate or text[:limit].strip()


def generate_conversation_title(message: object) -> str:
    """Deriva una etiqueta local, estable y breve para el primer mensaje útil."""
    if not isinstance(message, str):
        return DEFAULT_CONVERSATION_TITLE
    title = " ".join(message.split()).strip(" \t\n\r:;,.!?¿¡—–-\"“”")
    title = _GREETING_PREFIX.sub("", title)
    for prefix in _TITLE_PREFIXES:
        updated = prefix.sub("", title).strip()
        if updated != title:
            title = updated
            break
    title = title.strip(" \t\n\r:;,.!?¿¡—–-\"“”")
    if len(title) < 4:
        return DEFAULT_CONVERSATION_TITLE
    title = _truncate_title(title)
    return title[:1].upper() + title[1:]


def _update_conversation_after_message(
    connection: sqlite3.Connection,
    conversation_id: str,
    *,
    role: str,
    content: str,
) -> None:
    if role == "user":
        automatic_title = generate_conversation_title(content)
        connection.execute(
            """
            UPDATE reading_conversations
            SET title = CASE WHEN title_origin = 'pending' THEN ? ELSE title END,
                title_origin = CASE WHEN title_origin = 'pending' THEN 'automatic' ELSE title_origin END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (automatic_title, conversation_id),
        )
        return
    connection.execute(
        "UPDATE reading_conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (conversation_id,),
    )


def create_conversation(
    database: Path | str,
    *,
    work_id: str,
    profile_id: str,
    title: object = "",
) -> str:
    conversation_title = _clean_conversation_title(title) or None
    title_origin = "manual" if conversation_title else "pending"
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
                    profile_prompt_snapshot, title, title_origin
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    work_id,
                    profile_id,
                    profile["name"],
                    profile["prompt"],
                    conversation_title,
                    title_origin,
                ),
            )
            work_row = connection.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(w.display_title), ''),
                                REPLACE(w.preferred_title, '_', ' ')) AS display_title,
                       COALESCE(GROUP_CONCAT(DISTINCT c.display_name), '') AS authors
                FROM works w
                LEFT JOIN editions e ON e.work_id = w.id
                LEFT JOIN edition_contributors ec ON ec.edition_id = e.id AND ec.role = 'author'
                LEFT JOIN contributors c ON c.id = ec.contributor_id
                WHERE w.id = ? GROUP BY w.id
                """,
                (work_id,),
            ).fetchone()
            display_title = work_row["display_title"] if work_row else "Obra"
            authors = work_row["authors"] if work_row else ""
            content_text = f"Obra principal de la conversación: «{display_title}»"
            if authors:
                content_text += f" (Autoría: {authors})"
            connection.execute(
                """
                INSERT INTO conversation_context_sources(
                    id, conversation_id, source_type, source_id,
                    label_snapshot, content_snapshot
                ) VALUES (?, ?, 'work', ?, 'Ficha del libro', ?)
                """,
                (str(uuid.uuid4()), identifier, work_id, content_text),
            )
        return identifier
    finally:
        connection.close()


def update_conversation_title(
    database: Path | str, *, conversation_id: str, title: object
) -> None:
    conversation_title = _clean_conversation_title(title, required=True)
    connection = _open_database(database)
    try:
        with connection:
            updated = connection.execute(
                """
                UPDATE reading_conversations
                SET title = ?, title_origin = 'manual', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (conversation_title, conversation_id),
            ).rowcount
        if updated == 0:
            raise ConversationError("La conversación no existe")
    finally:
        connection.close()


def add_message(
    database: Path | str,
    *,
    conversation_id: str,
    role: str,
    content: object,
    companion_action_id: object = None,
) -> str:
    if role not in {"user", "assistant"}:
        raise ConversationError("El rol debe ser user o assistant")
    message_content = _clean_text(content, "El mensaje", required=True)
    try:
        action = get_companion_action(companion_action_id)
    except ValueError as error:
        raise ConversationError(str(error)) from error
    if role != "user" and action is not None:
        raise ConversationError("Solo un mensaje del usuario puede registrar una acción")
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
                id, conversation_id, sequence, role, content,
                companion_action_id, companion_action_label_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identifier,
                conversation_id,
                sequence,
                role,
                message_content,
                action.id if action else None,
                action.label if action else None,
            ),
        )
        _update_conversation_after_message(
            connection, conversation_id, role=role, content=message_content
        )
        connection.commit()
        return identifier
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def prepare_external_turn(
    database: Path | str,
    *,
    conversation_id: str,
    content: object,
    library_sources: list[dict],
) -> tuple[str, str]:
    message_content = _clean_text(content, "El mensaje", required=True)
    turn_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    connection = _open_database(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        conversation = connection.execute(
            "SELECT status FROM reading_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if conversation is None:
            raise ConversationError("La conversación no existe")
        if conversation["status"] != "active":
            raise ConversationError("La conversación está archivada")
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO conversation_messages(id,conversation_id,sequence,role,content) VALUES (?, ?, ?, 'user', ?)",
            (message_id, conversation_id, sequence, message_content),
        )
        connection.execute(
            "INSERT INTO external_conversation_turns(id,conversation_id,user_message_id,source_snapshot_json) VALUES (?, ?, ?, ?)",
            (turn_id, conversation_id, message_id, json.dumps(library_sources, ensure_ascii=False)),
        )
        _update_conversation_after_message(
            connection, conversation_id, role="user", content=message_content
        )
        connection.commit()
        return turn_id, message_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def complete_external_turn(
    database: Path | str, *, turn_id: str, content: object
) -> tuple[str, bool]:
    message_content = _clean_text(content, "La respuesta", required=True)
    connection = _open_database(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        turn = connection.execute(
            "SELECT * FROM external_conversation_turns WHERE id = ?", (turn_id,)
        ).fetchone()
        if turn is None:
            raise ConversationError("El turno externo no existe")
        if turn["status"] == "completed":
            connection.rollback()
            return str(turn["assistant_message_id"]), False
        conversation = connection.execute(
            "SELECT status FROM reading_conversations WHERE id = ?", (turn["conversation_id"],)
        ).fetchone()
        if conversation is None or conversation["status"] != "active":
            raise ConversationError("La conversación no está activa")
        message_id = str(uuid.uuid4())
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM conversation_messages WHERE conversation_id = ?",
            (turn["conversation_id"],),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO conversation_messages(id,conversation_id,sequence,role,content) VALUES (?, ?, ?, 'assistant', ?)",
            (message_id, turn["conversation_id"], sequence, message_content),
        )
        sources = json.loads(turn["source_snapshot_json"])
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
        connection.execute(
            "UPDATE external_conversation_turns SET status='completed', assistant_message_id=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (message_id, turn_id),
        )
        connection.execute(
            "UPDATE reading_conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (turn["conversation_id"],),
        )
        connection.commit()
        return message_id, True
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
            SELECT id, sequence, role, content, created_at,
                   companion_action_id, companion_action_label_snapshot
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


def get_conversation_summary(
    database: Path | str,
    conversation_id: str,
) -> dict | None:
    connection = _open_database(database)
    try:
        row = connection.execute(
            """
            SELECT cs.conversation_id, cs.work_id, cs.profile_id,
                   cs.profile_name_snapshot, cs.title_snapshot,
                   cs.summary, cs.created_at, cs.updated_at,
                   cs.last_message_sequence,
                   COALESCE((
                       SELECT MAX(cm.sequence)
                       FROM conversation_messages cm
                       WHERE cm.conversation_id = cs.conversation_id
                   ), 0) AS current_max_sequence
            FROM conversation_summaries cs
            WHERE cs.conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        res = dict(row)
        last_seq = res.get("last_message_sequence")
        curr_seq = res.get("current_max_sequence") or 0
        if last_seq is not None:
            new_msgs = max(0, curr_seq - last_seq)
        else:
            new_msgs = 0
        res["new_messages_count"] = new_msgs
        res["has_new_messages"] = (new_msgs > 0)
        return res
    finally:
        connection.close()


def list_work_conversation_summaries(
    database: Path | str,
    work_id: str,
    *,
    exclude_conversation_id: str | None = None,
) -> list[dict]:
    connection = _open_database(database)
    try:
        query = """
            SELECT cs.conversation_id, cs.work_id, cs.profile_id,
                   cs.profile_name_snapshot, cs.title_snapshot,
                   cs.summary, cs.created_at, cs.updated_at
            FROM conversation_summaries cs
            WHERE cs.work_id = ?
        """
        params: list[object] = [work_id]
        if exclude_conversation_id:
            query += " AND cs.conversation_id != ?"
            params.append(exclude_conversation_id)
        query += " ORDER BY cs.updated_at DESC"
        rows = connection.execute(query, params).fetchall()
        return [
            {
                "id": row["conversation_id"],
                "conversation_id": row["conversation_id"],
                "work_id": row["work_id"],
                "profile_id": row["profile_id"],
                "profile_name": row["profile_name_snapshot"],
                "title": row["title_snapshot"],
                "summary": row["summary"],
                "content": row["summary"],
                "label": f"Síntesis: {row['profile_name_snapshot']} · {row['title_snapshot']}",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    finally:
        connection.close()


def generate_and_save_conversation_summary(
    database: Path | str,
    conversation_id: str,
    *,
    provider: AIProvider | None = None,
) -> dict:
    conversation = get_conversation(database, conversation_id)
    messages = conversation.get("messages", [])
    user_messages = [m for m in messages if m["role"] == "user"]
    if not user_messages:
        raise ConversationError("No se puede sintetizar una conversación vacía o sin intervenciones del lector")

    work_id = conversation["work_id"]
    profile_name = conversation.get("profile_name_snapshot") or "Asistente"
    title = conversation.get("title") or DEFAULT_CONVERSATION_TITLE

    connection = _open_database(database)
    try:
        work_row = connection.execute(
            "SELECT COALESCE(NULLIF(TRIM(display_title), ''), REPLACE(preferred_title, '_', ' ')) AS title FROM works WHERE id = ?",
            (work_id,),
        ).fetchone()
        work_title = work_row["title"] if work_row else "Obra"
    finally:
        connection.close()

    instructions = CONVERSATION_SUMMARY_PROMPT.format(
        profile_name=profile_name,
        work_title=work_title,
    )

    conversation_text_parts = []
    for m in messages:
        sender = "Lector" if m["role"] == "user" else profile_name
        conversation_text_parts.append(f"{sender}: {m['content']}")
    conversation_text = "\n\n".join(conversation_text_parts)

    packet = PromptPacket(
        instructions=instructions,
        input=[{
            "role": "user",
            "content": f"A continuación la transcripción de la conversación para sintetizar:\n\n{conversation_text}",
        }],
    )

    if provider is None:
        provider = resolve_provider_for_profile(conversation.get("profile_id"))

    summary_text = provider.respond(packet).strip()

    connection = _open_database(database)
    try:
        current_seq_row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        last_message_sequence = current_seq_row[0] if current_seq_row else 0

        with connection:
            connection.execute(
                """
                INSERT INTO conversation_summaries(
                    conversation_id, work_id, profile_id, profile_name_snapshot,
                    title_snapshot, summary, last_message_sequence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    profile_name_snapshot = excluded.profile_name_snapshot,
                    title_snapshot = excluded.title_snapshot,
                    summary = excluded.summary,
                    last_message_sequence = excluded.last_message_sequence,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    conversation_id,
                    work_id,
                    conversation["profile_id"],
                    profile_name,
                    title,
                    summary_text,
                    last_message_sequence,
                ),
            )
        return {
            "conversation_id": conversation_id,
            "work_id": work_id,
            "profile_id": conversation["profile_id"],
            "profile_name": profile_name,
            "title": title,
            "summary": summary_text,
            "last_message_sequence": last_message_sequence,
            "new_messages_count": 0,
            "has_new_messages": False,
        }
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
        annotation_rows = connection.execute(
            """
            SELECT an.id, an.kind, an.position_type,
                   an.start_position_native, an.end_position_native,
                   (SELECT COALESCE(ao.original_position, '') || ' ' || COALESCE(ao.original_date, '')
                    FROM annotation_occurrences ao WHERE ao.annotation_id = an.id
                    ORDER BY ao.observed_at DESC LIMIT 1) AS source_reference,
                   COALESCE(NULLIF(TRIM(an.text), ''), NULLIF(TRIM(an.note_text), ''),
                            'Anotación sin texto recuperable') AS content
            FROM annotations an JOIN editions e ON e.id = an.edition_id
            WHERE e.work_id = ? ORDER BY COALESCE(an.native_created_at, an.created_at) DESC
            """,
            (work_id,),
        )
        annotations = []
        for row in annotation_rows:
            item = dict(row)
            item["reference"] = _context_reference(item.pop("source_reference", None))
            annotations.append(item)
        summaries = list_work_conversation_summaries(database, work_id, exclude_conversation_id=conversation_id)
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
            "conversation_summaries": summaries,
            "selected": {row["source_type"]: [] for row in selected} | {
                kind: [row["source_id"] for row in selected if row["source_type"] == kind]
                for kind in {row["source_type"] for row in selected}
            },
        }
    finally:
        connection.close()


def resolve_turn_context_sources(
    database: Path | str,
    conversation_id: str,
    *,
    personal_note_ids: object | None = None,
    annotation_ids: object | None = None,
    conversation_summary_ids: object | None = None,
) -> list[dict]:
    """Resuelve el contexto de un próximo turno sin escribir en SQLite.

    Cuando llegan ids desde el cliente representa el reemplazo que haría
    ``update_context``: conserva la ficha del libro y los materiales fijados,
    y usa la selección de borrador para notas, anotaciones y síntesis.
    """
    connection = _open_database(database)
    try:
        conversation = connection.execute(
            "SELECT work_id FROM reading_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if conversation is None:
            raise ConversationError("La conversación no existe")
        current = [
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
        if personal_note_ids is None and annotation_ids is None and conversation_summary_ids is None:
            return current
        note_input = [] if personal_note_ids is None else personal_note_ids
        annotation_input = [] if annotation_ids is None else annotation_ids
        summary_input = [] if conversation_summary_ids is None else conversation_summary_ids
        if not isinstance(note_input, list) or not all(isinstance(item, str) for item in note_input):
            raise ConversationError("La selección de notas no es válida")
        if not isinstance(annotation_input, list) or not all(isinstance(item, str) for item in annotation_input):
            raise ConversationError("La selección de anotaciones no es válida")
        if not isinstance(summary_input, list) or not all(isinstance(item, str) for item in summary_input):
            raise ConversationError("La selección de síntesis de conversación no es válida")
        note_ids = list(dict.fromkeys(note_input))
        annotation_ids_clean = list(dict.fromkeys(annotation_input))
        summary_ids_clean = list(dict.fromkeys(summary_input))
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
        summaries = {row["conversation_id"]: row for row in connection.execute(
            """
            SELECT conversation_id, profile_name_snapshot, title_snapshot, summary
            FROM conversation_summaries WHERE work_id = ?
            """,
            (work_id,),
        )}
        if any(identifier not in notes for identifier in note_ids):
            raise ConversationError("Una nota seleccionada no pertenece a este libro")
        if any(identifier not in annotations for identifier in annotation_ids_clean):
            raise ConversationError("Una anotación seleccionada no pertenece a este libro")
        if any(identifier not in summaries for identifier in summary_ids_clean):
            raise ConversationError("Una síntesis seleccionada no pertenece a este libro")
        retained = [
            item for item in current
            if item["source_type"] == "work"
            or item["is_pinned"]
            or (personal_note_ids is None and item["source_type"] == "personal_note")
            or (annotation_ids is None and item["source_type"] == "annotation")
            or (conversation_summary_ids is None and item["source_type"] == "conversation_summary")
        ]
        material = [
            {
                "source_type": "personal_note", "source_id": identifier,
                "label_snapshot": "Nota propia", "content_snapshot": notes[identifier]["body"],
                "is_pinned": 0,
            }
            for identifier in note_ids
        ] + [
            {
                "source_type": "annotation", "source_id": identifier,
                "label_snapshot": annotations[identifier]["kind"],
                "content_snapshot": annotations[identifier]["content"], "is_pinned": 0,
            }
            for identifier in annotation_ids_clean
        ] + [
            {
                "source_type": "conversation_summary", "source_id": identifier,
                "label_snapshot": f"Síntesis: {summaries[identifier]['profile_name_snapshot']} · {summaries[identifier]['title_snapshot']}",
                "content_snapshot": summaries[identifier]["summary"], "is_pinned": 0,
            }
            for identifier in summary_ids_clean
        ]
        merged = {(item["source_type"], item["source_id"]): item for item in retained}
        for item in material:
            merged[(item["source_type"], item["source_id"])] = item
        return list(merged.values())
    finally:
        connection.close()


def update_context(
    database: Path | str,
    conversation_id: str,
    *,
    personal_note_ids: object,
    annotation_ids: object,
    conversation_summary_ids: object | None = None,
) -> None:
    if not isinstance(personal_note_ids, list) or not all(isinstance(item, str) for item in personal_note_ids):
        raise ConversationError("La selección de notas no es válida")
    if not isinstance(annotation_ids, list) or not all(isinstance(item, str) for item in annotation_ids):
        raise ConversationError("La selección de anotaciones no es válida")
    if conversation_summary_ids is not None and (
        not isinstance(conversation_summary_ids, list)
        or not all(isinstance(item, str) for item in conversation_summary_ids)
    ):
        raise ConversationError("La selección de síntesis de conversación no es válida")

    note_ids = list(dict.fromkeys(personal_note_ids))
    selected_annotation_ids = list(dict.fromkeys(annotation_ids))
    summary_ids = list(dict.fromkeys(conversation_summary_ids)) if conversation_summary_ids is not None else None

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
        summaries = {row["conversation_id"]: row for row in connection.execute(
            """
            SELECT conversation_id, profile_name_snapshot, title_snapshot, summary
            FROM conversation_summaries WHERE work_id = ?
            """,
            (work_id,),
        )}

        if any(identifier not in notes for identifier in note_ids):
            raise ConversationError("Una nota seleccionada no pertenece a este libro")
        if any(identifier not in annotations for identifier in selected_annotation_ids):
            raise ConversationError("Una anotación seleccionada no pertenece a este libro")
        if summary_ids and any(identifier not in summaries for identifier in summary_ids):
            raise ConversationError("Una síntesis seleccionada no pertenece a este libro")

        with connection:
            if summary_ids is not None:
                connection.execute(
                    "DELETE FROM conversation_context_sources WHERE conversation_id = ? AND source_type != 'work' AND is_pinned = 0",
                    (conversation_id,),
                )
            else:
                connection.execute(
                    "DELETE FROM conversation_context_sources WHERE conversation_id = ? AND source_type NOT IN ('work', 'conversation_summary') AND is_pinned = 0",
                    (conversation_id,),
                )
            connection.executemany(
                """
                INSERT INTO conversation_context_sources(
                    id, conversation_id, source_type, source_id, label_snapshot, content_snapshot
                ) VALUES (?, ?, 'personal_note', ?, 'Nota propia', ?)
                ON CONFLICT(conversation_id, source_type, source_id) DO UPDATE SET
                    label_snapshot=excluded.label_snapshot,
                    content_snapshot=excluded.content_snapshot
                """,
                [(str(uuid.uuid4()), conversation_id, identifier, notes[identifier]["body"]) for identifier in note_ids],
            )
            connection.executemany(
                """
                INSERT INTO conversation_context_sources(
                    id, conversation_id, source_type, source_id, label_snapshot, content_snapshot
                ) VALUES (?, ?, 'annotation', ?, ?, ?)
                ON CONFLICT(conversation_id, source_type, source_id) DO UPDATE SET
                    label_snapshot=excluded.label_snapshot,
                    content_snapshot=excluded.content_snapshot
                """,
                [(str(uuid.uuid4()), conversation_id, identifier, annotations[identifier]["kind"], annotations[identifier]["content"]) for identifier in selected_annotation_ids],
            )
            if summary_ids:
                connection.executemany(
                    """
                    INSERT INTO conversation_context_sources(
                        id, conversation_id, source_type, source_id, label_snapshot, content_snapshot
                    ) VALUES (?, ?, 'conversation_summary', ?, ?, ?)
                    ON CONFLICT(conversation_id, source_type, source_id) DO UPDATE SET
                        label_snapshot=excluded.label_snapshot,
                        content_snapshot=excluded.content_snapshot
                    """,
                    [
                        (
                            str(uuid.uuid4()),
                            conversation_id,
                            identifier,
                            f"Síntesis: {summaries[identifier]['profile_name_snapshot']} · {summaries[identifier]['title_snapshot']}",
                            summaries[identifier]["summary"],
                        )
                        for identifier in summary_ids
                    ],
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
    context_sources: list[dict] | None = None,
    draft_content: object | None = None,
) -> PromptPacket:
    conversation = get_conversation(database, conversation_id)
    if context_sources is not None:
        conversation["context_sources"] = context_sources
    sources_parts = []
    for item in conversation["context_sources"]:
        label = item.get("label_snapshot", "")
        content = item.get("content_snapshot", "")
        if item.get("source_type") == "conversation_summary":
            sources_parts.append(f"[MEMORIA PREVIA — {label}]\n{content}")
        else:
            sources_parts.append(f"[{label}]\n{content}")
    sources = "\n\n".join(sources_parts)
    instructions = (
        f"{conversation['profile_prompt_snapshot']}\n\n"
        "Estás conversando sobre la OBRA PRINCIPAL indicada en la ficha del contexto. "
        "Utilizá activamente tu conocimiento general sobre esta obra para analizar sus temas, estructura y contenido. "
        "Los subrayados, notas y selecciones del usuario representan sus puntos de interés personales en su lectura, "
        "no la totalidad del libro. No te niegues a responder sobre la obra ni afirmes que falta contexto solo porque "
        "un pasaje no esté explícitamente subrayado. "
        "Trabajá como acompañante de lectura riguroso pero conversable, no como autoridad rígida. "
        "Distinguí datos del contexto, inferencias e hipótesis. "
        "Si el usuario pregunta por la atribución fáctica de una cita, pasaje o personaje específico y existe ambigüedad "
        "en el fragmento o incertidumbre en la fuente, sé prudente y aclara las hipótesis plausibles en lugar de afirmar "
        "categóricamente un dato no verificado. "
        "Si el usuario señala que una afirmación o atribución tuya es errónea, no intentes defender el error previo con "
        "justificaciones retóricas ni interpretaciones ad-hoc; reevaluá los hechos con objetividad y considerá otros "
        "personajes o pasajes de la obra. "
        "DINÁMICA CONVERSACIONAL Y SEGUIMIENTO: La estructura rígida con encabezados (###) se utiliza únicamente en el primer turno de presentación o análisis inicial de la conversación. En los mensajes de seguimiento, repreguntas o comentarios posteriores del diálogo, respondé de forma fluida, directa y conversacional sin repetir la plantilla de secciones, manteniendo siempre tu personalidad y tono. "
        "Cuando uses subrayados o notas adjuntas, o evidencias de otras obras de la biblioteca, nombrá de manera natural "
        "la obra y el tipo de material (por ejemplo: 'Según un subrayado de 1984…' o 'En relación con El cisne negro…'). "
        "Si dispones de memorias previas o síntesis de conversaciones anteriores, refierete a ellas como antecedentes o debates previos (por ejemplo: 'En el debate previo sobre este punto...'). "
        "No uses códigos ni identificadores técnicos para referirte a las fuentes."
    )
    messages = [{"role": item["role"], "content": item["content"]} for item in conversation["messages"]]
    if draft_content is not None:
        messages.append({"role": "user", "content": _clean_text(draft_content, "El mensaje", required=True)})
    automatic_parts = []
    for item in library_sources or []:
        reference = f" · {item['reference']}" if item.get("reference") else ""
        automatic_parts.append(
            f"FUENTE — {item['label']} de «{item['work_title']}»{reference}\n{item['content']}"
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
            SELECT rc.id, rc.title, rc.title_origin, rc.profile_id, rc.profile_name_snapshot,
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
