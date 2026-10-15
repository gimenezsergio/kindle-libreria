from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .ai import AIError, AIProvider, PromptPacket
from .db import connect_database


class LaboratorioError(RuntimeError):
    pass


TUTOR_PHILOSOPHICAL_PROMPT = """Eres el Tutor Filosófico de un Laboratorio de Lectura Personal.
Tu función es actuar como un COLEGA DE LECTURA EXIGENTE e interlocutor dialéctico.
Tu objetivo NO es resumir la obra, ni felicitar al lector, ni dar conferencias académicas, sino ayudar al lector a construir, poner a prueba y afilar su propio pensamiento a partir de la escena o dilema que está examinando.

Directivas estrictas de comportamiento:
1. TONO: Directo, sobrio, respetuoso pero exigente e incisivo. Trata al lector como un par intelectual. No uses frases de cortesía vacías ni adulaciones ("¡Qué interesante pregunta!", "Excelente punto").
2. LONGITUD: Máximo 2 párrafos breves. Respuestas quirúrgicas. Está prohibido escribir sermones o monólogos extensos.
3. ESTRUCTURA DE CADA TURNO:
   - Párrafo 1: Un señalamiento crítico concreto (una distinción conceptual, un punto ciego, un contraejemplo o un supuesto implícito).
   - Párrafo 2: Una única pregunta o provocación directa para devolverle la palabra al lector. No hagas múltiples preguntas a la vez.
4. MANIOBRAS DIALÉCTICAS A UTILIZAR:
   - Contraejemplo: Presenta un caso límite donde la regla moral o afirmación del lector se quiebre.
   - Caza de supuestos: Haz visible lo que el lector da por sentado sin fundamentar.
   - Precisión conceptual: Si usa términos ambiguos o comodín (como "justicia", "libertad", "deber"), pídele que precise qué entiende por ellos en este contexto.
   - Inversión de perspectiva: Invítalo a defender la postura contraria o la del antagonista.
   - Anclaje en el texto: Si la reflexión se va a una abstracción vacía, tráela de vuelta a la escena y a las citas del libro.
5. RIGOR FÁCTICO Y RESPETO DE LA EDICIÓN:
   - Las citas provistas y la descripción del lector son la verdad de referencia para esta sesión. No discutas variantes editoriales ni asumas otra edición.
   - Si el lector menciona un hecho que parece un error grave sobre la trama, no lo desmientas con pedantería ni lo convalides ciegamente: plantéalo de forma condicional mostrando cómo cambia el dilema si el hecho fue de otro modo.
6. FILÓSOFOS COMO HERRAMIENTAS, NO COMO DOGMAS:
   - No des lecciones de historia de la filosofía. Si mencionas a un pensador (Kant, Aristóteles, Nietzsche, Arendt, etc.), hazlo solo para aportar una distinción conceptual útil y aplicable a la escena.
"""

SYNTHESIS_OUTLINE_PROMPT = """A partir del debate dialéctico previo entre el lector y el tutor, debes generar el esquema de síntesis que servirá de andamiaje para que el lector redacte su propio texto de cierre (de 300 a 600 palabras).

Debes responder ÚNICAMENTE en formato JSON válido con exactamente esta estructura:
{
  "outline_thesis": "Frase clara y precisa con la tesis o postura principal que defendió el lector.",
  "outline_objection": "La principal objeción, contraejemplo o dificultad que tuvo que considerar.",
  "outline_counterargument": "Cómo respondió o defendió su postura frente a esa objeción."
}
No incluyas texto antes ni después del bloque JSON."""


def _open_database(path: Path | str) -> sqlite3.Connection:
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        raise LaboratorioError("La base SQLite todavía no existe")
    return connect_database(database)


def create_inquiry(
    database: Path | str | sqlite3.Connection,
    *,
    work_id: str,
    dilemma_question: str,
    chapter_or_section: str | None = None,
    annotation_ids: list[str] | None = None,
    parent_inquiry_id: str | None = None,
) -> dict[str, Any]:
    question = dilemma_question.strip()
    if not question:
        raise LaboratorioError("La pregunta o dilema central no puede estar vacía")

    inquiry_id = str(uuid.uuid4())
    conn = database if isinstance(database, sqlite3.Connection) else _open_database(database)
    should_close = not isinstance(database, sqlite3.Connection)

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO philosophical_inquiries (
                    id, work_id, chapter_or_section, dilemma_question,
                    status, parent_inquiry_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'sparring', ?, strftime('%Y-%m-%d %H:%M:%S', 'now'), strftime('%Y-%m-%d %H:%M:%S', 'now'))
                """,
                (inquiry_id, work_id, chapter_or_section, question, parent_inquiry_id),
            )

            if annotation_ids:
                for order, ann_id in enumerate(annotation_ids):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO inquiry_annotations (
                            inquiry_id, annotation_id, display_order
                        ) VALUES (?, ?, ?)
                        """,
                        (inquiry_id, ann_id, order),
                    )

        return get_inquiry(conn, inquiry_id)
    finally:
        if should_close:
            conn.close()


def get_inquiry(
    database: Path | str | sqlite3.Connection,
    inquiry_id: str,
) -> dict[str, Any]:
    conn = database if isinstance(database, sqlite3.Connection) else _open_database(database)
    should_close = not isinstance(database, sqlite3.Connection)

    try:
        row = conn.execute(
            """
            SELECT id, work_id, chapter_or_section, dilemma_question, status,
                   outline_thesis, outline_objection, outline_counterargument,
                   final_text, word_count, parent_inquiry_id,
                   created_at, updated_at, completed_at
            FROM philosophical_inquiries
            WHERE id = ?
            """,
            (inquiry_id,),
        ).fetchone()

        if not row:
            raise LaboratorioError("La sesión de indagación no existe")

        inquiry = {
            "id": row["id"],
            "work_id": row["work_id"],
            "chapter_or_section": row["chapter_or_section"],
            "dilemma_question": row["dilemma_question"],
            "status": row["status"],
            "outline_thesis": row["outline_thesis"],
            "outline_objection": row["outline_objection"],
            "outline_counterargument": row["outline_counterargument"],
            "final_text": row["final_text"],
            "word_count": row["word_count"],
            "parent_inquiry_id": row["parent_inquiry_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }

        # Citas vinculadas con su texto
        ann_rows = conn.execute(
            """
            SELECT a.id, a.text, a.note_text, a.kind, a.start_position_native,
                   ac.chapter_title, ac.surrounding_before, ac.surrounding_after
            FROM inquiry_annotations ia
            JOIN annotations a ON a.id = ia.annotation_id
            LEFT JOIN annotation_contexts ac ON ac.annotation_id = a.id
            WHERE ia.inquiry_id = ?
            ORDER BY ia.display_order ASC
            """,
            (inquiry_id,),
        ).fetchall()

        inquiry["annotations"] = [
            {
                "id": r["id"],
                "text": r["text"],
                "note_text": r["note_text"],
                "kind": r["kind"],
                "position": r["start_position_native"],
                "chapter_title": r["chapter_title"],
                "surrounding_before": r["surrounding_before"],
                "surrounding_after": r["surrounding_after"],
            }
            for r in ann_rows
        ]

        # Mensajes de la conversación / sparring
        msg_rows = conn.execute(
            """
            SELECT id, sequence, role, content, created_at
            FROM inquiry_messages
            WHERE inquiry_id = ?
            ORDER BY sequence ASC
            """,
            (inquiry_id,),
        ).fetchall()

        inquiry["messages"] = [
            {
                "id": r["id"],
                "sequence": r["sequence"],
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
            for r in msg_rows
        ]

        # Etiquetas temáticas
        tag_rows = conn.execute(
            """
            SELECT tag FROM inquiry_tags WHERE inquiry_id = ? ORDER BY tag ASC
            """,
            (inquiry_id,),
        ).fetchall()
        inquiry["tags"] = [r["tag"] for r in tag_rows]

        return inquiry
    finally:
        if should_close:
            conn.close()


def list_work_inquiries(
    database: Path | str | sqlite3.Connection,
    work_id: str,
) -> list[dict[str, Any]]:
    conn = database if isinstance(database, sqlite3.Connection) else _open_database(database)
    should_close = not isinstance(database, sqlite3.Connection)

    try:
        rows = conn.execute(
            """
            SELECT id, work_id, chapter_or_section, dilemma_question, status,
                   outline_thesis, final_text, word_count, created_at, completed_at
            FROM philosophical_inquiries
            WHERE work_id = ?
            ORDER BY updated_at DESC
            """,
            (work_id,),
        ).fetchall()

        results = []
        for r in rows:
            inquiry_id = r["id"]
            tag_rows = conn.execute(
                "SELECT tag FROM inquiry_tags WHERE inquiry_id = ? ORDER BY tag ASC",
                (inquiry_id,),
            ).fetchall()
            results.append({
                "id": r["id"],
                "work_id": r["work_id"],
                "chapter_or_section": r["chapter_or_section"],
                "dilemma_question": r["dilemma_question"],
                "status": r["status"],
                "outline_thesis": r["outline_thesis"],
                "final_text": r["final_text"],
                "word_count": r["word_count"],
                "created_at": r["created_at"],
                "completed_at": r["completed_at"],
                "tags": [tr["tag"] for tr in tag_rows],
            })
        return results
    finally:
        if should_close:
            conn.close()


def add_inquiry_message(
    database: Path | str | sqlite3.Connection,
    *,
    inquiry_id: str,
    role: str,
    content: str,
) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise LaboratorioError("El mensaje no puede estar vacío")
    if role not in ("user", "tutor"):
        raise LaboratorioError(f"Rol inválido: {role}")

    conn = database if isinstance(database, sqlite3.Connection) else _open_database(database)
    should_close = not isinstance(database, sqlite3.Connection)

    try:
        with conn:
            max_seq = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM inquiry_messages WHERE inquiry_id = ?",
                (inquiry_id,),
            ).fetchone()[0]

            msg_id = str(uuid.uuid4())
            seq = max_seq + 1

            conn.execute(
                """
                INSERT INTO inquiry_messages (id, inquiry_id, sequence, role, content, created_at)
                VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%S', 'now'))
                """,
                (msg_id, inquiry_id, seq, role, text),
            )

            conn.execute(
                """
                UPDATE philosophical_inquiries
                SET updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
                WHERE id = ?
                """,
                (inquiry_id,),
            )

        return {
            "id": msg_id,
            "sequence": seq,
            "role": role,
            "content": text,
        }
    finally:
        if should_close:
            conn.close()


def generate_tutor_response(
    database: Path | str | sqlite3.Connection,
    *,
    inquiry_id: str,
    provider: AIProvider,
    work_title: str | None = None,
) -> dict[str, Any]:
    inquiry = get_inquiry(database, inquiry_id)
    annotations = inquiry.get("annotations", [])
    messages = inquiry.get("messages", [])

    # Construir el contexto documental
    context_lines = []
    if work_title:
        context_lines.append(f"OBRA: {work_title}")
    if inquiry.get("chapter_or_section"):
        context_lines.append(f"CAPÍTULO O SECCIÓN: {inquiry['chapter_or_section']}")
    context_lines.append(f"DILEMA O PREGUNTA CENTRAL: {inquiry['dilemma_question']}")

    if annotations:
        context_lines.append("\nPASAJES CITADOS POR EL LECTOR:")
        for ann in annotations:
            quote = ann.get("text") or ""
            note = ann.get("note_text")
            before = ann.get("surrounding_before")
            after = ann.get("surrounding_after")
            entry = f"- «{quote}»"
            if before or after:
                entry += f" [Contexto narrativo: ...{before or ''} | {quote} | {after or ''}...]"
            if note:
                entry += f" (Nota personal del lector: {note})"
            context_lines.append(entry)

    instructions = (
        TUTOR_PHILOSOPHICAL_PROMPT
        + "\n\nCONTEXTO DE LA SESIÓN:\n"
        + "\n".join(context_lines)
    )

    # Convertir historial de mensajes a input para el prompt packet
    packet_input = []
    for msg in messages:
        sender_label = "Lector" if msg["role"] == "user" else "Tutor"
        packet_input.append({"content": f"{sender_label}: {msg['content']}"})

    packet = PromptPacket(instructions=instructions, input=packet_input)

    response_text = provider.respond(packet)
    # Guardar en base de datos
    return add_inquiry_message(
        database,
        inquiry_id=inquiry_id,
        role="tutor",
        content=response_text,
    )


def generate_synthesis_outline(
    database: Path | str | sqlite3.Connection,
    *,
    inquiry_id: str,
    provider: AIProvider,
) -> dict[str, Any]:
    import json
    inquiry = get_inquiry(database, inquiry_id)
    messages = inquiry.get("messages", [])

    conversation_text = "\n\n".join(
        f"{'Lector' if m['role'] == 'user' else 'Tutor'}: {m['content']}"
        for m in messages
    )

    packet = PromptPacket(
        instructions=SYNTHESIS_OUTLINE_PROMPT,
        input=[{
            "content": (
                f"DILEMA CENTRAL: {inquiry['dilemma_question']}\n\n"
                f"CONVERSACIÓN DEL DEBATE:\n{conversation_text}"
            )
        }],
    )

    raw_response = provider.respond(packet)
    clean_json = raw_response.strip()
    if clean_json.startswith("```"):
        lines = clean_json.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean_json = "\n".join(lines).strip()

    try:
        data = json.loads(clean_json)
    except json.JSONDecodeError:
        data = {
            "outline_thesis": "Postura planteada durante el debate.",
            "outline_objection": "Objeción o caso límite considerado.",
            "outline_counterargument": "Defensa razonada del argumento.",
        }

    conn = database if isinstance(database, sqlite3.Connection) else _open_database(database)
    should_close = not isinstance(database, sqlite3.Connection)

    try:
        with conn:
            conn.execute(
                """
                UPDATE philosophical_inquiries
                SET outline_thesis = ?,
                    outline_objection = ?,
                    outline_counterargument = ?,
                    status = 'ready_to_write',
                    updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
                WHERE id = ?
                """,
                (
                    data.get("outline_thesis", ""),
                    data.get("outline_objection", ""),
                    data.get("outline_counterargument", ""),
                    inquiry_id,
                ),
            )
        return data
    finally:
        if should_close:
            conn.close()


def save_final_reflection(
    database: Path | str | sqlite3.Connection,
    *,
    inquiry_id: str,
    final_text: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    text = final_text.strip()
    if not text:
        raise LaboratorioError("El texto final no puede estar vacío")

    words = len(text.split())

    conn = database if isinstance(database, sqlite3.Connection) else _open_database(database)
    should_close = not isinstance(database, sqlite3.Connection)

    try:
        with conn:
            conn.execute(
                """
                UPDATE philosophical_inquiries
                SET final_text = ?,
                    word_count = ?,
                    status = 'completed',
                    completed_at = strftime('%Y-%m-%d %H:%M:%S', 'now'),
                    updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
                WHERE id = ?
                """,
                (text, words, inquiry_id),
            )

            if tags:
                conn.execute("DELETE FROM inquiry_tags WHERE inquiry_id = ?", (inquiry_id,))
                for raw_tag in tags:
                    tag = raw_tag.strip()
                    if tag:
                        conn.execute(
                            "INSERT OR IGNORE INTO inquiry_tags (inquiry_id, tag) VALUES (?, ?)",
                            (inquiry_id, tag),
                        )

        return get_inquiry(conn, inquiry_id)
    finally:
        if should_close:
            conn.close()


def save_inquiry_draft(
    database: Path | str | sqlite3.Connection,
    *,
    inquiry_id: str,
    draft_text: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    text = draft_text.strip()
    words = len(text.split()) if text else 0

    conn = database if isinstance(database, sqlite3.Connection) else _open_database(database)
    should_close = not isinstance(database, sqlite3.Connection)

    try:
        with conn:
            conn.execute(
                """
                UPDATE philosophical_inquiries
                SET final_text = ?,
                    word_count = ?,
                    status = 'ready_to_write',
                    updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')
                WHERE id = ?
                """,
                (text, words, inquiry_id),
            )

            if tags is not None:
                conn.execute("DELETE FROM inquiry_tags WHERE inquiry_id = ?", (inquiry_id,))
                for raw_tag in tags:
                    tag = raw_tag.strip()
                    if tag:
                        conn.execute(
                            "INSERT OR IGNORE INTO inquiry_tags (inquiry_id, tag) VALUES (?, ?)",
                            (inquiry_id, tag),
                        )

        return get_inquiry(conn, inquiry_id)
    finally:
        if should_close:
            conn.close()

