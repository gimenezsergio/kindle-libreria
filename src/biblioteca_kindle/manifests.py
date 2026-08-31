from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .db import connect_database
from .inventory import InventoryError, validate_kindle_root


class ManifestImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManifestImportResult:
    snapshot_id: str
    imported: int
    created: int
    updated: int


@dataclass(frozen=True)
class ManifestRecord:
    observation_id: str
    content_id: str
    content_type: str
    title: str
    book_relative_path: str
    sidecar_relative_path: str
    document_format: str
    file_size: int
    file_modified_at: str | None
    content_hash: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(kind: str, content_type: str, content_id: str) -> str:
    key = f"biblioteca-kindle:{kind}:{content_type}:{content_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _latest_completed_snapshot(
    connection: sqlite3.Connection, root: Path
) -> sqlite3.Row:
    snapshot = connection.execute(
        """
        SELECT id, started_at
        FROM device_snapshots
        WHERE status = 'completed' AND mount_point = ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (str(root),),
    ).fetchone()
    if snapshot is None:
        raise ManifestImportError("No hay una instantánea completa para este Kindle")
    return snapshot


def _safe_source_path(root: Path, relative_path: str) -> Path:
    path = (root / PurePosixPath(relative_path)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ManifestImportError(f"Ruta de fuente fuera del Kindle: {relative_path}") from exc
    if not path.is_file():
        raise ManifestImportError(f"La fuente ya no existe: {relative_path}")
    return path


def _title_from_stem(stem: str, content_id: str) -> str:
    suffix = f"_{content_id}"
    title = stem[: -len(suffix)] if stem.casefold().endswith(suffix.casefold()) else stem
    return title.strip(" _-") or content_id


def _parse_manifest_records(
    connection: sqlite3.Connection,
    root: Path,
    snapshot_id: str,
) -> list[ManifestRecord]:
    observations = connection.execute(
        """
        SELECT id, source_relative_path
        FROM source_observations
        WHERE snapshot_id = ?
          AND source_type = 'sidecar'
          AND lower(source_relative_path) LIKE '%.mf'
        ORDER BY source_relative_path
        """,
        (snapshot_id,),
    ).fetchall()
    book_rows = connection.execute(
        """
        SELECT source_relative_path, file_size, file_modified_at, file_hash
        FROM source_observations
        WHERE snapshot_id = ? AND source_type = 'book'
        """,
        (snapshot_id,),
    ).fetchall()
    books = {row["source_relative_path"]: row for row in book_rows}
    records: list[ManifestRecord] = []
    seen_keys: set[tuple[str, str]] = set()

    for observation in observations:
        manifest_path = _safe_source_path(root, observation["source_relative_path"])
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            content = payload["content"]
            content_id = str(content["id"]).strip()
            content_type = str(content["type"]).strip()
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ManifestImportError(
                f"Manifiesto inválido: {observation['source_relative_path']}"
            ) from exc
        if not content_id or not content_type:
            raise ManifestImportError(
                f"Manifiesto sin identidad: {observation['source_relative_path']}"
            )
        key = (content_type, content_id)
        if key in seen_keys:
            raise ManifestImportError(
                f"Identidad de contenido duplicada en la instantánea: {content_type}/{content_id}"
            )
        seen_keys.add(key)

        sidecar = PurePosixPath(observation["source_relative_path"]).parent
        if not sidecar.name.casefold().endswith(".sdr"):
            raise ManifestImportError(
                f"Manifiesto fuera de un directorio .sdr: {observation['source_relative_path']}"
            )
        book_stem = sidecar.name[:-4]
        candidates = []
        for relative_path, row in books.items():
            candidate = PurePosixPath(relative_path)
            if candidate.parent != sidecar.parent:
                continue
            if candidate.stem != book_stem:
                continue
            if content_id.casefold() not in candidate.name.casefold():
                continue
            candidates.append(row)
        if len(candidates) != 1:
            raise ManifestImportError(
                f"Se esperó un libro para {sidecar.as_posix()} y se encontraron {len(candidates)}"
            )
        book = candidates[0]
        book_path = PurePosixPath(book["source_relative_path"])
        records.append(
            ManifestRecord(
                observation_id=observation["id"],
                content_id=content_id,
                content_type=content_type,
                title=_title_from_stem(book_stem, content_id),
                book_relative_path=book_path.as_posix(),
                sidecar_relative_path=sidecar.as_posix(),
                document_format=book_path.suffix.lstrip(".").upper(),
                file_size=book["file_size"],
                file_modified_at=book["file_modified_at"],
                content_hash=book["file_hash"],
            )
        )
    return records


def import_manifests(
    kindle_root: Path | str,
    database: Path | str,
    *,
    snapshot_id: str | None = None,
) -> ManifestImportResult:
    root = validate_kindle_root(kindle_root)
    database_path = Path(database).expanduser().resolve()
    try:
        database_path.relative_to(root)
    except ValueError:
        pass
    else:
        raise InventoryError("La base de datos no puede estar dentro del Kindle")
    if not database_path.is_file():
        raise ManifestImportError("La base SQLite todavía no existe")

    connection = connect_database(database_path)
    try:
        if snapshot_id is None:
            snapshot = _latest_completed_snapshot(connection, root)
            snapshot_id = snapshot["id"]
            observed_at = snapshot["started_at"]
        else:
            snapshot = connection.execute(
                """
                SELECT id, started_at FROM device_snapshots
                WHERE id = ? AND status = 'completed' AND mount_point = ?
                """,
                (snapshot_id, str(root)),
            ).fetchone()
            if snapshot is None:
                raise ManifestImportError("La instantánea indicada no es válida o completa")
            observed_at = snapshot["started_at"]

        records = _parse_manifest_records(connection, root, snapshot_id)
        created = 0
        updated = 0
        with connection:
            for record in records:
                delivery_id = _stable_id(
                    "delivery", record.content_type, record.content_id
                )
                edition_id = _stable_id("edition", record.content_type, record.content_id)
                work_id = _stable_id("work", record.content_type, record.content_id)
                exists = connection.execute(
                    "SELECT 1 FROM kindle_deliveries WHERE id = ?", (delivery_id,)
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO works(id, preferred_title, merge_status)
                    VALUES (?, ?, 'provisional')
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (work_id, record.title),
                )
                connection.execute(
                    """
                    INSERT INTO editions(id, work_id, title, format_hint)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (edition_id, work_id, record.title, record.document_format),
                )
                connection.execute(
                    """
                    INSERT INTO kindle_deliveries(
                        id, edition_id, source_observation_id, kindle_content_id,
                        content_type, document_format, relative_path,
                        sidecar_relative_path, file_size, file_modified_at,
                        content_hash, first_seen_at, last_seen_at, presence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'present')
                    ON CONFLICT(id) DO UPDATE SET
                        source_observation_id = excluded.source_observation_id,
                        document_format = excluded.document_format,
                        relative_path = excluded.relative_path,
                        sidecar_relative_path = excluded.sidecar_relative_path,
                        file_size = excluded.file_size,
                        file_modified_at = excluded.file_modified_at,
                        content_hash = excluded.content_hash,
                        last_seen_at = excluded.last_seen_at,
                        presence = 'present'
                    """,
                    (
                        delivery_id,
                        edition_id,
                        record.observation_id,
                        record.content_id,
                        record.content_type,
                        record.document_format,
                        record.book_relative_path,
                        record.sidecar_relative_path,
                        record.file_size,
                        record.file_modified_at,
                        record.content_hash,
                        observed_at,
                        observed_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO external_identifiers(
                        id, entity_type, entity_id, namespace, value,
                        source_observation_id, confidence, is_preferred
                    ) VALUES (?, 'kindle_delivery', ?, 'kindle_content_id', ?, ?, 'exact', 1)
                    ON CONFLICT(namespace, value, entity_type, entity_id)
                    DO UPDATE SET source_observation_id = excluded.source_observation_id
                    """,
                    (
                        _stable_id("identifier", record.content_type, record.content_id),
                        delivery_id,
                        record.content_id,
                        record.observation_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE source_observations
                    SET parser_name = 'manifest', parser_version = '1',
                        parse_status = 'parsed'
                    WHERE id = ?
                    """,
                    (record.observation_id,),
                )
                if exists is None:
                    created += 1
                else:
                    updated += 1
        return ManifestImportResult(
            snapshot_id=snapshot_id,
            imported=len(records),
            created=created,
            updated=updated,
        )
    finally:
        connection.close()

