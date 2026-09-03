from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .db import connect_database, migrate_database
from .remote_sync import SCHEMA_VERSION, SyncPackageError, validate_sync_package


TABLES = {
    "device_snapshots": ("device_snapshots", ("id", "device_key", "mount_point", "mount_read_only", "status", "started_at", "completed_at", "summary_json", "warning_count")),
    "works": ("works", ("id", "preferred_title", "merge_status", "created_at", "updated_at", "display_title")),
    "editions": ("editions", ("id", "work_id", "title", "subtitle", "language", "publication_date", "publisher", "format_hint", "created_at", "updated_at")),
    "contributors": ("contributors", ("id", "display_name", "normalized_name", "created_at")),
    "source_observations": ("source_observations", ("id", "snapshot_id", "source_type", "source_relative_path", "file_size", "file_modified_at", "file_hash", "observed_at", "parser_name", "parser_version", "parse_status", "warning_json")),
    "deliveries": ("kindle_deliveries", ("id", "edition_id", "source_observation_id", "kindle_content_id", "content_type", "document_format", "relative_path", "sidecar_relative_path", "file_size", "file_modified_at", "content_hash", "first_seen_at", "last_seen_at", "presence")),
    "external_identifiers": ("external_identifiers", ("id", "entity_type", "entity_id", "namespace", "value", "source_observation_id", "confidence", "is_preferred", "created_at")),
    "title_aliases": ("title_aliases", ("id", "edition_id", "original_title", "normalized_title", "source_observation_id", "confidence", "resolution_status", "created_at")),
    "annotations": ("annotations", ("id", "edition_id", "kind", "text", "note_text", "start_position_native", "end_position_native", "position_type", "native_created_at", "native_modified_at", "status", "created_at", "updated_at")),
    "annotation_occurrences": ("annotation_occurrences", ("id", "annotation_id", "source_observation_id", "source_kind", "source_record_key", "original_heading", "original_position", "original_date", "raw_payload_ref", "observed_at")),
    "reading_states": ("reading_states", ("id", "kindle_delivery_id", "source_observation_id", "observed_at", "last_position_native", "last_position_type", "last_position_at", "furthest_position_native", "furthest_position_type", "furthest_position_at", "progress_fraction", "progress_method", "reading_time_ms", "words_read")),
    "reading_history_records": ("reading_history_records", ("id", "reading_state_id", "sequence_number", "position_native", "recorded_at")),
}


def _hash(package: dict[str, Any]) -> str:
    body = json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _count(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0])


def _upsert(connection: sqlite3.Connection, group: str, records: list[dict], snapshot_id: str) -> None:
    table, columns = TABLES[group]
    updates = [column for column in columns if column not in {"id", "created_at", "display_title"}]
    sql = (
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
        f"ON CONFLICT(id) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in updates)}"
    )
    for source in records:
        record = dict(source)
        connection.execute(sql, tuple(record.get(column) for column in columns))


def apply_sync_package(database: Path | str, package: dict[str, Any]) -> dict[str, Any]:
    validate_sync_package(package)
    migrate_database(database)
    digest = _hash(package)
    connection = connect_database(database)
    try:
        with connection:
            old = connection.execute(
                "SELECT content_hash,response_json FROM remote_sync_packages WHERE package_id=?",
                (package["package_id"],),
            ).fetchone()
            if old:
                if old["content_hash"] != digest:
                    raise SyncPackageError("package_id reutilizado con contenido diferente")
                response = json.loads(old["response_json"])
                response["status"] = "already_applied"
                return response
            before_works = _count(connection, "SELECT COUNT(*) FROM works")
            before_annotations = _count(connection, "SELECT COUNT(*) FROM annotations")
            previously_present = {
                row["id"] for row in connection.execute(
                    "SELECT id FROM kindle_deliveries WHERE presence='present'"
                )
            }
            snapshot_id = package["package_id"]
            snapshot = package["snapshot"]
            connection.execute(
                "INSERT INTO device_snapshots(id,device_key,mount_point,mount_read_only,status,started_at,completed_at,summary_json,warning_count) VALUES (?,?,?,1,'completed',?,?,?,?)",
                (snapshot_id, package["device_key"], f"remote:{package['agent_id']}", snapshot["started_at_utc"], snapshot["completed_at_utc"], json.dumps({"warnings": package["warnings"]}), len(package["warnings"])),
            )
            entities = package["entities"]
            for group in ("works", "editions", "contributors", "device_snapshots"):
                _upsert(connection, group, entities[group], snapshot_id)
            for record in entities["edition_contributors"]:
                connection.execute(
                    "INSERT INTO edition_contributors(edition_id,contributor_id,role,display_order) VALUES (?,?,?,?) ON CONFLICT(edition_id,contributor_id,role) DO UPDATE SET display_order=excluded.display_order",
                    (record["edition_id"], record["contributor_id"], record["role"], record["display_order"]),
                )
            for group in ("source_observations", "deliveries", "external_identifiers", "title_aliases", "annotations", "annotation_occurrences", "reading_states", "reading_history_records"):
                _upsert(connection, group, entities[group], snapshot_id)
            connection.execute("UPDATE kindle_deliveries SET presence='absent'")
            present = sorted(set(package["present_delivery_ids"]))
            if present:
                connection.execute(
                    f"UPDATE kindle_deliveries SET presence='present' WHERE id IN ({','.join('?' for _ in present)})", present
                )
            totals = {
                "works": _count(connection, "SELECT COUNT(*) FROM works"),
                "books_present": _count(connection, "SELECT COUNT(*) FROM kindle_deliveries WHERE presence='present'"),
                "annotations": _count(connection, "SELECT COUNT(*) FROM annotations"),
            }
            for row in connection.execute("SELECT kind,COUNT(*) total FROM annotations GROUP BY kind"):
                totals[{"highlight": "highlights", "note": "notes", "bookmark": "bookmarks", "other": "other_annotations"}[row["kind"]]] = row["total"]
            response = {"schema_version": SCHEMA_VERSION, "package_id": package["package_id"], "status": "applied", "changes": {"works_created": totals["works"] - before_works, "annotations_created": totals["annotations"] - before_annotations, "books_marked_absent": len(previously_present - set(present))}, "totals": totals, "warnings": package["warnings"]}
            connection.execute(
                "INSERT INTO remote_sync_packages(package_id,content_hash,agent_id,device_key,response_json) VALUES (?,?,?,?,?)",
                (package["package_id"], digest, package["agent_id"], package["device_key"], json.dumps(response, ensure_ascii=False, sort_keys=True)),
            )
        return response
    finally:
        connection.close()
