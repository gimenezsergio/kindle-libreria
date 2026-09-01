from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import connect_database


class ReportError(RuntimeError):
    pass


def _open_database(path: Path | str) -> sqlite3.Connection:
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        raise ReportError("La base SQLite todavía no existe")
    return connect_database(database)


def _count(connection: sqlite3.Connection, query: str, parameters: tuple = ()) -> int:
    return int(connection.execute(query, parameters).fetchone()[0])


def library_summary(database: Path | str) -> str:
    connection = _open_database(database)
    try:
        snapshot = connection.execute(
            """
            SELECT id, started_at, completed_at, warning_count
            FROM device_snapshots
            WHERE status = 'completed'
            ORDER BY started_at DESC LIMIT 1
            """
        ).fetchone()
        annotations = {
            row["kind"]: row["total"]
            for row in connection.execute(
                "SELECT kind, COUNT(*) AS total FROM annotations GROUP BY kind"
            )
        }
        sources = {
            row["source_kind"]: row["total"]
            for row in connection.execute(
                "SELECT source_kind, COUNT(*) AS total FROM annotation_occurrences GROUP BY source_kind"
            )
        }
        delivery_total = _count(connection, "SELECT COUNT(*) FROM kindle_deliveries")
        delivery_present = _count(
            connection, "SELECT COUNT(*) FROM kindle_deliveries WHERE presence = 'present'"
        )
        delivery_absent = _count(
            connection, "SELECT COUNT(*) FROM kindle_deliveries WHERE presence = 'absent'"
        )
        provisional = _count(
            connection, "SELECT COUNT(*) FROM works WHERE merge_status = 'provisional'"
        )
        review = _count(
            connection, "SELECT COUNT(*) FROM works WHERE merge_status = 'review'"
        )
        warnings = _count(
            connection,
            "SELECT COUNT(*) FROM source_observations WHERE parse_status IN ('warning', 'failed')",
        )
        lines = ["Biblioteca Kindle — resumen local"]
        if snapshot is None:
            lines.append("Última sincronización: ninguna")
        else:
            lines.append(
                f"Última sincronización: {snapshot['completed_at'] or snapshot['started_at']} "
                f"({snapshot['warning_count']} advertencias)"
            )
        lines.extend(
            [
                f"Obras: {_count(connection, 'SELECT COUNT(*) FROM works')}",
                f"Ediciones: {_count(connection, 'SELECT COUNT(*) FROM editions')}",
                f"Entregas: {delivery_total} (presentes: {delivery_present}; "
                f"ausentes: {delivery_absent})",
                "Anotaciones por tipo: " + (
                    ", ".join(f"{key}={value}" for key, value in sorted(annotations.items()))
                    if annotations else "ninguna"
                ),
                "Ocurrencias por fuente: " + (
                    ", ".join(f"{key}={value}" for key, value in sorted(sources.items()))
                    if sources else "ninguna"
                ),
                f"Obras provisionales: {provisional}",
                f"Obras para revisar: {review}",
                f"Observaciones con advertencias: {warnings}",
                f"Colecciones propias: {_count(connection, 'SELECT COUNT(*) FROM collections')}",
                f"Notas propias: {_count(connection, 'SELECT COUNT(*) FROM personal_notes')}",
                f"Relaciones entre obras: {_count(connection, 'SELECT COUNT(*) FROM work_relations')}",
            ]
        )
        return "\n".join(lines)
    finally:
        connection.close()


def work_card(database: Path | str, work_id: str, *, include_private: bool = False) -> str:
    connection = _open_database(database)
    try:
        work = connection.execute(
            """
            SELECT id, preferred_title,
                   COALESCE(NULLIF(TRIM(display_title), ''), REPLACE(preferred_title, '_', ' ')) AS shown_title,
                   merge_status FROM works WHERE id = ?
            """,
            (work_id,),
        ).fetchone()
        if work is None:
            raise ReportError(f"No existe la obra: {work_id}")
        editions = connection.execute(
            "SELECT id, title, language, publisher FROM editions WHERE work_id = ? ORDER BY title",
            (work_id,),
        ).fetchall()
        lines = [
            f"Obra: {work['shown_title']}",
            f"ID: {work['id']}",
            f"Estado: {work['merge_status']}",
            f"Ediciones: {len(editions)}",
        ]
        for edition in editions:
            detail = ", ".join(
                value for value in (edition["language"], edition["publisher"]) if value
            )
            lines.append(f"- {edition['title']}" + (f" ({detail})" if detail else ""))
        lines.append(
            f"Anotaciones: {_count(connection, 'SELECT COUNT(*) FROM annotations WHERE edition_id IN (SELECT id FROM editions WHERE work_id = ?)', (work_id,))}"
        )
        lines.append(
            f"Colecciones propias: {_count(connection, 'SELECT COUNT(*) FROM work_collections WHERE work_id = ?', (work_id,))}"
        )
        lines.append(
            f"Relaciones: {_count(connection, 'SELECT COUNT(*) FROM work_relations WHERE source_work_id = ? OR target_work_id = ?', (work_id, work_id))}"
        )
        notes = connection.execute(
            "SELECT body FROM personal_notes WHERE target_type = 'work' AND target_id = ? ORDER BY created_at",
            (work_id,),
        ).fetchall()
        lines.append(f"Notas propias: {len(notes)}")
        if include_private:
            lines.extend(f"- {row['body']}" for row in notes)
        elif notes:
            lines.append("(contenido privado oculto; use --include-private para mostrarlo)")
        return "\n".join(lines)
    finally:
        connection.close()
