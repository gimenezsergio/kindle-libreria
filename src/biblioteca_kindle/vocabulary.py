from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from .db import connect_database
from .inventory import InventoryError, hash_file, validate_kindle_root
from .manifests import ManifestImportError


class VocabularyImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class VocabularyImportResult:
    snapshot_id: str
    rows: int
    matched: int
    unmatched: int


def _stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"biblioteca-kindle:{kind}:{value}"))


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def _snapshot(
    connection: sqlite3.Connection, root: Path, snapshot_id: str | None
) -> sqlite3.Row:
    if snapshot_id is None:
        row = connection.execute(
            """
            SELECT id FROM device_snapshots
            WHERE status = 'completed' AND mount_point = ?
            ORDER BY started_at DESC LIMIT 1
            """,
            (str(root),),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT id FROM device_snapshots
            WHERE id = ? AND status = 'completed' AND mount_point = ?
            """,
            (snapshot_id, str(root)),
        ).fetchone()
    if row is None:
        raise VocabularyImportError("No hay una instantánea completa válida")
    return row


def _read_book_info(path: Path) -> list[sqlite3.Row]:
    uri = f"file:{path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            """
            SELECT id, asin, guid, lang, title, authors
            FROM BOOK_INFO
            ORDER BY id
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise VocabularyImportError("No se pudo leer BOOK_INFO de vocab.db") from exc
    finally:
        if "connection" in locals():
            connection.close()
    return rows


def import_vocabulary(
    kindle_root: Path | str,
    database: Path | str,
    *,
    snapshot_id: str | None = None,
) -> VocabularyImportResult:
    root = validate_kindle_root(kindle_root)
    database_path = Path(database).expanduser().resolve()
    try:
        database_path.relative_to(root)
    except ValueError:
        pass
    else:
        raise InventoryError("La base de datos no puede estar dentro del Kindle")
    if not database_path.is_file():
        raise VocabularyImportError("La base SQLite todavía no existe")

    connection = connect_database(database_path)
    try:
        snapshot = _snapshot(connection, root, snapshot_id)
        snapshot_id = snapshot["id"]
        observation = connection.execute(
            """
            SELECT id, source_relative_path, file_hash
            FROM source_observations
            WHERE snapshot_id = ?
              AND source_relative_path = 'system/vocabulary/vocab.db'
            """,
            (snapshot_id,),
        ).fetchone()
        if observation is None:
            raise VocabularyImportError("La instantánea no contiene vocab.db")
        source_path = (root / observation["source_relative_path"]).resolve()
        try:
            source_path.relative_to(root)
        except ValueError as exc:
            raise VocabularyImportError("La ruta de vocab.db sale del Kindle") from exc
        if not source_path.is_file():
            raise VocabularyImportError("vocab.db ya no existe en el Kindle")
        if hash_file(source_path) != observation["file_hash"]:
            raise VocabularyImportError(
                "vocab.db cambió después del inventario; creá una nueva instantánea"
            )

        rows = _read_book_info(source_path)
        matched = 0
        with connection:
            for row in rows:
                asin = str(row["asin"] or "").strip()
                if not asin:
                    continue
                delivery = connection.execute(
                    """
                    SELECT kd.id, kd.edition_id, e.work_id, kd.content_type
                    FROM kindle_deliveries AS kd
                    JOIN editions AS e ON e.id = kd.edition_id
                    WHERE kd.kindle_content_id = ?
                    """,
                    (asin,),
                ).fetchone()
                if delivery is None:
                    continue
                matched += 1
                title = str(row["title"] or "").strip()
                language = str(row["lang"] or "").strip() or None
                author = str(row["authors"] or "").strip()
                if title:
                    connection.execute(
                        "UPDATE editions SET title = ?, language = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (title, language, delivery["edition_id"]),
                    )
                    connection.execute(
                        "UPDATE works SET preferred_title = ?, updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (title, delivery["work_id"]),
                    )
                    connection.execute(
                        """
                        INSERT INTO title_aliases(
                            id, edition_id, original_title, normalized_title,
                            source_observation_id, confidence, resolution_status
                        ) VALUES (?, ?, ?, ?, ?, 'exact', 'resolved')
                        ON CONFLICT(id) DO UPDATE SET
                            original_title = excluded.original_title,
                            normalized_title = excluded.normalized_title,
                            source_observation_id = excluded.source_observation_id
                        """,
                        (
                            _stable_id("vocab-title", f"{row['id']}:{title}"),
                            delivery["edition_id"],
                            title,
                            _normalize_name(title),
                            observation["id"],
                        ),
                    )
                if author:
                    normalized_author = _normalize_name(author)
                    contributor_id = _stable_id("contributor", normalized_author)
                    connection.execute(
                        """
                        INSERT INTO contributors(id, display_name, normalized_name)
                        VALUES (?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET display_name = excluded.display_name
                        """,
                        (contributor_id, author, normalized_author),
                    )
                    connection.execute(
                        """
                        INSERT INTO edition_contributors(
                            edition_id, contributor_id, role, display_order
                        ) VALUES (?, ?, 'author', 0)
                        ON CONFLICT DO NOTHING
                        """,
                        (delivery["edition_id"], contributor_id),
                    )
                for namespace, value in (
                    ("kindle_vocab_id", row["id"]),
                    ("kindle_vocab_guid", row["guid"]),
                ):
                    value = str(value or "").strip()
                    if not value:
                        continue
                    connection.execute(
                        """
                        INSERT INTO external_identifiers(
                            id, entity_type, entity_id, namespace, value,
                            source_observation_id, confidence, is_preferred
                        ) VALUES (?, 'edition', ?, ?, ?, ?, 'exact', 0)
                        ON CONFLICT(namespace, value, entity_type, entity_id)
                        DO UPDATE SET source_observation_id = excluded.source_observation_id
                        """,
                        (
                            _stable_id(namespace, value),
                            delivery["edition_id"],
                            namespace,
                            value,
                            observation["id"],
                        ),
                    )
                if delivery["content_type"] == "kindle.ebook":
                    connection.execute(
                        """
                        INSERT INTO external_identifiers(
                            id, entity_type, entity_id, namespace, value,
                            source_observation_id, confidence, is_preferred
                        ) VALUES (?, 'edition', ?, 'asin', ?, ?, 'exact', 1)
                        ON CONFLICT(namespace, value, entity_type, entity_id)
                        DO UPDATE SET source_observation_id = excluded.source_observation_id
                        """,
                        (
                            _stable_id("asin", asin),
                            delivery["edition_id"],
                            asin,
                            observation["id"],
                        ),
                    )
            connection.execute(
                """
                UPDATE source_observations
                SET parser_name = 'vocabulary', parser_version = '1',
                    parse_status = 'parsed'
                WHERE id = ?
                """,
                (observation["id"],),
            )
        return VocabularyImportResult(
            snapshot_id=snapshot_id,
            rows=len(rows),
            matched=matched,
            unmatched=len(rows) - matched,
        )
    finally:
        connection.close()

