from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from .db import connect_database


class PersonalDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class CollectionResult:
    id: str
    created: bool


@dataclass(frozen=True)
class RelationResult:
    id: str
    created: bool


def _open_database(path: Path | str) -> sqlite3.Connection:
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        raise PersonalDataError("La base SQLite todavía no existe")
    return connect_database(database)


def _require_row(
    connection: sqlite3.Connection, table: str, identifier: str, label: str
) -> None:
    if table not in {"works", "collections"}:
        raise ValueError("Tabla no permitida")
    exists = connection.execute(
        f"SELECT 1 FROM {table} WHERE id = ?", (identifier,)
    ).fetchone()
    if exists is None:
        raise PersonalDataError(f"No existe {label}: {identifier}")


def create_collection(
    database: Path | str,
    name: str,
    *,
    parent_id: str | None = None,
    description: str | None = None,
) -> CollectionResult:
    name = " ".join(name.split())
    if not name:
        raise PersonalDataError("La colección necesita un nombre")
    connection = _open_database(database)
    try:
        if parent_id is not None:
            _require_row(connection, "collections", parent_id, "la colección padre")
        if parent_id is None:
            existing = connection.execute(
                "SELECT id FROM collections WHERE parent_id IS NULL AND name = ?",
                (name,),
            ).fetchone()
        else:
            existing = connection.execute(
                "SELECT id FROM collections WHERE parent_id = ? AND name = ?",
                (parent_id, name),
            ).fetchone()
        if existing is not None:
            with connection:
                if description is not None:
                    connection.execute(
                        "UPDATE collections SET description = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (description, existing["id"]),
                    )
            return CollectionResult(id=existing["id"], created=False)
        identifier = str(uuid.uuid4())
        with connection:
            connection.execute(
                """
                INSERT INTO collections(id, parent_id, name, description)
                VALUES (?, ?, ?, ?)
                """,
                (identifier, parent_id, name, description),
            )
        return CollectionResult(id=identifier, created=True)
    finally:
        connection.close()

def assign_work_to_collection(
    database: Path | str,
    work_id: str,
    collection_id: str,
    *,
    note: str | None = None,
    display_order: int = 0,
) -> bool:
    if display_order < 0:
        raise PersonalDataError("El orden no puede ser negativo")
    connection = _open_database(database)
    try:
        _require_row(connection, "works", work_id, "la obra")
        _require_row(connection, "collections", collection_id, "la colección")
        existing = connection.execute(
            """
            SELECT 1 FROM work_collections
            WHERE work_id = ? AND collection_id = ?
            """,
            (work_id, collection_id),
        ).fetchone()
        with connection:
            connection.execute(
                """
                INSERT INTO work_collections(work_id, collection_id, display_order, note)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(work_id, collection_id) DO UPDATE SET
                    display_order = excluded.display_order,
                    note = excluded.note
                """,
                (work_id, collection_id, display_order, note),
            )
        return existing is None
    finally:
        connection.close()


def add_work_note(database: Path | str, work_id: str, body: str) -> str:
    body = body.strip()
    if not body:
        raise PersonalDataError("La nota no puede estar vacía")
    connection = _open_database(database)
    try:
        _require_row(connection, "works", work_id, "la obra")
        identifier = str(uuid.uuid4())
        with connection:
            connection.execute(
                """
                INSERT INTO personal_notes(id, target_type, target_id, body)
                VALUES (?, 'work', ?, ?)
                """,
                (identifier, work_id, body),
            )
        return identifier
    finally:
        connection.close()


def set_work_display_title(
    database: Path | str, work_id: str, title: str | None
) -> str | None:
    normalized = " ".join(title.split()) if title is not None else ""
    display_title = normalized or None
    connection = _open_database(database)
    try:
        _require_row(connection, "works", work_id, "la obra")
        with connection:
            connection.execute(
                "UPDATE works SET display_title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (display_title, work_id),
            )
        return display_title
    finally:
        connection.close()


def add_work_relation(
    database: Path | str,
    source_work_id: str,
    target_work_id: str,
    relation_type: str,
    *,
    label: str | None = None,
    explanation: str | None = None,
    symmetric: bool = False,
) -> RelationResult:
    relation_type = " ".join(relation_type.split()).casefold()
    if not relation_type:
        raise PersonalDataError("La relación necesita un tipo")
    if source_work_id == target_work_id:
        raise PersonalDataError("Una obra no puede relacionarse consigo misma")
    connection = _open_database(database)
    try:
        _require_row(connection, "works", source_work_id, "la obra de origen")
        _require_row(connection, "works", target_work_id, "la obra de destino")
        if symmetric and target_work_id < source_work_id:
            source_work_id, target_work_id = target_work_id, source_work_id
        existing = connection.execute(
            """
            SELECT id FROM work_relations
            WHERE source_work_id = ? AND target_work_id = ? AND relation_type = ?
            """,
            (source_work_id, target_work_id, relation_type),
        ).fetchone()
        if existing is not None:
            with connection:
                connection.execute(
                    """
                    UPDATE work_relations
                    SET label = ?, explanation = ?, is_symmetric = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (label, explanation, int(symmetric), existing["id"]),
                )
            return RelationResult(id=existing["id"], created=False)
        key = f"{source_work_id}:{target_work_id}:{relation_type}"
        identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, f"biblioteca-kindle:relation:{key}"))
        with connection:
            connection.execute(
                """
                INSERT INTO work_relations(
                    id, source_work_id, target_work_id, relation_type,
                    label, explanation, is_symmetric
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    source_work_id,
                    target_work_id,
                    relation_type,
                    label,
                    explanation,
                    int(symmetric),
                ),
            )
        return RelationResult(id=identifier, created=True)
    finally:
        connection.close()
