from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .db import connect_database
from .inventory import InventoryError, hash_file, validate_kindle_root
from .krds import KRDSError, read_krds


KRDS_EXTENSIONS = {".yjr", ".azw3r", ".mbp1", ".pds"}
KRDS_KIND = {
    "annotation.personal.bookmark": "bookmark",
    "annotation.personal.highlight": "highlight",
    "annotation.personal.note": "note",
    "annotation.personal.clip_article": "other",
    "annotation.personal.handwritten_note": "other",
    "annotation.personal.sticky_note": "note",
    "annotation.personal.underline": "highlight",
}
HAN_KIND = {
    "kindle.bookmark": "bookmark",
    "kindle.highlight": "highlight",
    "kindle.note": "note",
}


class AnnotationImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class AnnotationSourceRecord:
    delivery_id: str
    edition_id: str
    observation_id: str
    observed_at: str
    source_kind: str
    source_key: str
    kind: str
    start_position: str | None
    end_position: str | None
    created_at: str | None
    modified_at: str | None
    text: str | None
    note_text: str | None


@dataclass(frozen=True)
class AnnotationImportResult:
    snapshot_id: str
    krds_files: int
    han_files: int
    krds_annotations: int
    han_annotations: int
    created: int
    existing: int
    unmatched_files: int
    warnings: int


def _stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"biblioteca-kindle:{kind}:{value}"))


def _record_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
        raise AnnotationImportError("No hay una instantánea completa válida")
    return row


def _safe_unchanged_source(root: Path, observation: sqlite3.Row) -> Path:
    source = (root / PurePosixPath(observation["source_relative_path"])).resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise AnnotationImportError("Una ruta de anotación sale del Kindle") from exc
    if not source.is_file():
        raise AnnotationImportError(
            f"La fuente ya no existe: {observation['source_relative_path']}"
        )
    if hash_file(source) != observation["file_hash"]:
        raise AnnotationImportError(
            f"{observation['source_relative_path']} cambió después del inventario"
        )
    return source


def _krds_records(
    source: Path,
    observation: sqlite3.Row,
    delivery: sqlite3.Row,
) -> tuple[list[AnnotationSourceRecord], list[str]]:
    try:
        decoded, warnings = read_krds(source.read_bytes())
    except KRDSError as exc:
        raise AnnotationImportError(
            f"No se pudo leer KRDS: {observation['source_relative_path']}"
        ) from exc
    cache = decoded.get("annotation.cache.object")
    if not isinstance(cache, dict):
        raise AnnotationImportError(
            f"Caché de anotaciones inválida: {observation['source_relative_path']}"
        )
    records: list[AnnotationSourceRecord] = []
    for class_name, annotations in cache.items():
        kind = KRDS_KIND.get(class_name, "other")
        if not isinstance(annotations, list):
            warnings.append(f"{class_name}: lista inválida")
            continue
        for annotation in annotations:
            if not isinstance(annotation, dict):
                warnings.append(f"{class_name}: registro inválido")
                continue
            key_payload = {
                "delivery": delivery["id"],
                "class": class_name,
                "start": annotation.get("start_position"),
                "end": annotation.get("end_position"),
                "created": annotation.get("creation_time"),
                "modified": annotation.get("modification_time"),
                "note": annotation.get("note"),
            }
            source_key = _record_hash(key_payload)
            records.append(
                AnnotationSourceRecord(
                    delivery_id=delivery["id"],
                    edition_id=delivery["edition_id"],
                    observation_id=observation["id"],
                    observed_at=observation["observed_at"],
                    source_kind="krds",
                    source_key=source_key,
                    kind=kind,
                    start_position=str(annotation.get("start_position"))
                    if annotation.get("start_position") is not None
                    else None,
                    end_position=str(annotation.get("end_position"))
                    if annotation.get("end_position") is not None
                    else None,
                    created_at=annotation.get("creation_time"),
                    modified_at=annotation.get("modification_time"),
                    text=None,
                    note_text=str(annotation.get("note"))
                    if annotation.get("note") not in (None, "")
                    else None,
                )
            )
    return records, warnings


def _han_records(
    source: Path,
    observation: sqlite3.Row,
    delivery: sqlite3.Row,
) -> list[AnnotationSourceRecord]:
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))["payload"]
        source_records = payload["records"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AnnotationImportError(
            f"HAN inválido: {observation['source_relative_path']}"
        ) from exc
    records: list[AnnotationSourceRecord] = []
    for record in source_records:
        kind = HAN_KIND.get(str(record.get("type")))
        if kind is None:
            continue
        annotation_id = str(record.get("annotationId") or "").strip()
        source_key = _record_hash(
            {
                "delivery": delivery["id"],
                "annotation_id": annotation_id,
                "fallback": None if annotation_id else record,
            }
        )
        text = str(record.get("text")) if record.get("text") not in (None, "") else None
        records.append(
            AnnotationSourceRecord(
                delivery_id=delivery["id"],
                edition_id=delivery["edition_id"],
                observation_id=observation["id"],
                observed_at=observation["observed_at"],
                source_kind="han",
                source_key=source_key,
                kind=kind,
                start_position=str(record.get("startPosition"))
                if record.get("startPosition") is not None
                else None,
                end_position=str(record.get("endPosition"))
                if record.get("endPosition") is not None
                else None,
                created_at=str(record.get("creationTime"))
                if record.get("creationTime") is not None
                else None,
                modified_at=str(record.get("lastModificationTime"))
                if record.get("lastModificationTime") is not None
                else None,
                text=text if kind == "highlight" else None,
                note_text=text if kind == "note" else None,
            )
        )
    return records


def import_annotations(
    kindle_root: Path | str,
    database: Path | str,
    *,
    snapshot_id: str | None = None,
) -> AnnotationImportResult:
    root = validate_kindle_root(kindle_root)
    database_path = Path(database).expanduser().resolve()
    try:
        database_path.relative_to(root)
    except ValueError:
        pass
    else:
        raise InventoryError("La base de datos no puede estar dentro del Kindle")
    if not database_path.is_file():
        raise AnnotationImportError("La base SQLite todavía no existe")

    connection = connect_database(database_path)
    try:
        snapshot = _snapshot(connection, root, snapshot_id)
        snapshot_id = snapshot["id"]
        observations = connection.execute(
            """
            SELECT id, source_relative_path, file_hash, observed_at
            FROM source_observations
            WHERE snapshot_id = ? AND source_type = 'sidecar'
            ORDER BY source_relative_path
            """,
            (snapshot_id,),
        ).fetchall()
        deliveries_by_sidecar = {
            row["sidecar_relative_path"]: row
            for row in connection.execute(
                """
                SELECT id, edition_id, kindle_content_id, sidecar_relative_path
                FROM kindle_deliveries WHERE sidecar_relative_path IS NOT NULL
                """
            )
        }
        deliveries_by_content = {
            row["kindle_content_id"]: row
            for row in deliveries_by_sidecar.values()
            if row["kindle_content_id"]
        }

        all_records: list[AnnotationSourceRecord] = []
        parsed_sources: list[tuple[sqlite3.Row, list[str], str]] = []
        krds_files = han_files = krds_count = han_count = unmatched = 0
        for observation in observations:
            relative = PurePosixPath(observation["source_relative_path"])
            suffix = relative.suffix.casefold()
            if suffix not in KRDS_EXTENSIONS and suffix != ".han":
                continue
            source = _safe_unchanged_source(root, observation)
            if suffix in KRDS_EXTENSIONS:
                krds_files += 1
                delivery = deliveries_by_sidecar.get(relative.parent.as_posix())
                if delivery is None:
                    unmatched += 1
                    continue
                records, warnings = _krds_records(source, observation, delivery)
                all_records.extend(records)
                krds_count += len(records)
                parsed_sources.append((observation, warnings, "krds-annotations"))
            else:
                han_files += 1
                try:
                    payload = json.loads(source.read_text(encoding="utf-8-sig"))["payload"]
                    content_id = str(payload["key"])
                except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise AnnotationImportError(f"HAN sin content.id: {relative}") from exc
                delivery = deliveries_by_content.get(content_id)
                if delivery is None:
                    unmatched += 1
                    continue
                records = _han_records(source, observation, delivery)
                all_records.extend(records)
                han_count += len(records)
                parsed_sources.append((observation, [], "han-annotations"))

        created = existing = warning_total = 0
        with connection:
            for record in all_records:
                logical_key = f"{record.source_kind}:{record.delivery_id}:{record.source_key}"
                annotation_id = _stable_id("source-annotation", logical_key)
                occurrence_id = _stable_id("source-occurrence", logical_key)
                found = connection.execute(
                    """
                    SELECT 1 FROM annotation_occurrences
                    WHERE source_kind = ? AND source_record_key = ?
                    """,
                    (record.source_kind, record.source_key),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO annotations(
                        id, edition_id, kind, text, note_text,
                        start_position_native, end_position_native,
                        position_type, native_created_at, native_modified_at,
                        status, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        edition_id = excluded.edition_id,
                        kind = excluded.kind,
                        text = excluded.text,
                        note_text = excluded.note_text,
                        start_position_native = excluded.start_position_native,
                        end_position_native = excluded.end_position_native,
                        native_created_at = excluded.native_created_at,
                        native_modified_at = excluded.native_modified_at,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        annotation_id,
                        record.edition_id,
                        record.kind,
                        record.text,
                        record.note_text,
                        record.start_position,
                        record.end_position,
                        record.source_kind,
                        record.created_at,
                        record.modified_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO annotation_occurrences(
                        id, annotation_id, source_observation_id, source_kind,
                        source_record_key, original_position, original_date,
                        observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_kind, source_record_key) DO UPDATE SET
                        source_observation_id = excluded.source_observation_id,
                        observed_at = excluded.observed_at
                    """,
                    (
                        occurrence_id,
                        annotation_id,
                        record.observation_id,
                        record.source_kind,
                        record.source_key,
                        record.start_position,
                        record.created_at,
                        record.observed_at,
                    ),
                )
                if found is None:
                    created += 1
                else:
                    existing += 1
            for observation, warnings, parser_name in parsed_sources:
                warning_total += len(warnings)
                connection.execute(
                    """
                    UPDATE source_observations
                    SET parser_name = ?, parser_version = '1', parse_status = ?,
                        warning_json = ?
                    WHERE id = ?
                    """,
                    (
                        parser_name,
                        "warning" if warnings else "parsed",
                        json.dumps(warnings, ensure_ascii=False),
                        observation["id"],
                    ),
                )
        return AnnotationImportResult(
            snapshot_id=snapshot_id,
            krds_files=krds_files,
            han_files=han_files,
            krds_annotations=krds_count,
            han_annotations=han_count,
            created=created,
            existing=existing,
            unmatched_files=unmatched,
            warnings=warning_total,
        )
    finally:
        connection.close()
