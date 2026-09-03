from __future__ import annotations

import json
import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA_VERSION = 1
ENTITY_GROUPS = (
    "works", "editions", "contributors", "edition_contributors", "deliveries",
    "external_identifiers", "title_aliases", "source_observations", "annotations",
    "annotation_occurrences", "reading_states", "reading_history_records",
)
FORBIDDEN_CONTENT_KEYS = {
    "book_bytes", "book_content", "file_bytes", "file_content", "raw_book",
    "base64_book", "epub", "kfx", "azw", "azw3", "mobi", "pdf",
}


class SyncPackageError(ValueError):
    pass


@dataclass(frozen=True)
class SyncExportResult:
    package_id: str
    output: Path
    sha256: str
    byte_count: int
    entity_count: int


def load_sync_schema(kind: str = "package") -> dict[str, Any]:
    if kind not in {"package", "response"}:
        raise ValueError("El esquema debe ser 'package' o 'response'")
    resource = files("biblioteca_kindle").joinpath(
        "schemas", f"sync-{kind}-v{SCHEMA_VERSION}.schema.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def _require_keys(value: dict[str, Any], required: set[str], context: str) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required)
    if missing:
        raise SyncPackageError(f"{context}: faltan campos: {', '.join(missing)}")
    if extra:
        raise SyncPackageError(f"{context}: campos desconocidos: {', '.join(extra)}")


def _parse_uuid(value: Any, field: str) -> None:
    try:
        UUID(str(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise SyncPackageError(f"{field}: UUID inválido") from error


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SyncPackageError(f"{field}: debe ser una fecha UTC terminada en Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise SyncPackageError(f"{field}: fecha inválida") from error
    return parsed


def _reject_book_content(value: Any, path: str = "package") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in FORBIDDEN_CONTENT_KEYS:
                raise SyncPackageError(f"{path}.{key}: no se permite enviar archivos de libros")
            _reject_book_content(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_book_content(child, f"{path}[{index}]")


def validate_sync_package(package: Any) -> None:
    if not isinstance(package, dict):
        raise SyncPackageError("package: debe ser un objeto")
    _require_keys(
        package,
        {"schema_version", "package_id", "created_at_utc", "agent_id", "device_key", "snapshot", "entities", "present_delivery_ids", "warnings"},
        "package",
    )
    if package["schema_version"] != SCHEMA_VERSION:
        raise SyncPackageError(f"schema_version: solo se admite la versión {SCHEMA_VERSION}")
    _parse_uuid(package["package_id"], "package_id")
    _parse_uuid(package["agent_id"], "agent_id")
    _parse_utc(package["created_at_utc"], "created_at_utc")
    if not isinstance(package["device_key"], str) or not package["device_key"].strip():
        raise SyncPackageError("device_key: debe ser un texto no vacío")

    snapshot = package["snapshot"]
    if not isinstance(snapshot, dict):
        raise SyncPackageError("snapshot: debe ser un objeto")
    _require_keys(snapshot, {"kind", "started_at_utc", "completed_at_utc", "mount_read_only", "source_timezone"}, "snapshot")
    if snapshot["kind"] != "full":
        raise SyncPackageError("snapshot.kind: debe ser 'full'")
    started = _parse_utc(snapshot["started_at_utc"], "snapshot.started_at_utc")
    completed = _parse_utc(snapshot["completed_at_utc"], "snapshot.completed_at_utc")
    if completed < started:
        raise SyncPackageError("snapshot: completed_at_utc precede a started_at_utc")
    if snapshot["mount_read_only"] is not True:
        raise SyncPackageError("snapshot.mount_read_only: el Kindle debe estar en solo lectura")
    try:
        ZoneInfo(snapshot["source_timezone"])
    except (ZoneInfoNotFoundError, TypeError) as error:
        raise SyncPackageError("snapshot.source_timezone: zona IANA inválida") from error

    entities = package["entities"]
    if not isinstance(entities, dict):
        raise SyncPackageError("entities: debe ser un objeto")
    _require_keys(entities, set(ENTITY_GROUPS), "entities")
    ids_by_group: dict[str, set[str]] = {}
    for group in ENTITY_GROUPS:
        records = entities[group]
        if not isinstance(records, list):
            raise SyncPackageError(f"entities.{group}: debe ser una lista")
        identifiers: set[str] = set()
        for index, record in enumerate(records):
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
                raise SyncPackageError(f"entities.{group}[{index}].id: identificador inválido")
            if record["id"] in identifiers:
                raise SyncPackageError(f"entities.{group}: identificador duplicado {record['id']}")
            identifiers.add(record["id"])
        ids_by_group[group] = identifiers

    present = package["present_delivery_ids"]
    if not isinstance(present, list) or not all(isinstance(item, str) and item for item in present):
        raise SyncPackageError("present_delivery_ids: debe ser una lista de identificadores")
    if len(present) != len(set(present)):
        raise SyncPackageError("present_delivery_ids: contiene duplicados")
    unknown = sorted(set(present) - ids_by_group["deliveries"])
    if unknown:
        raise SyncPackageError(f"present_delivery_ids: entregas no incluidas: {', '.join(unknown)}")
    if not isinstance(package["warnings"], list) or not all(isinstance(item, str) for item in package["warnings"]):
        raise SyncPackageError("warnings: debe ser una lista de textos")
    _reject_book_content(package)


def validate_sync_response(response: Any, *, expected_package_id: str | None = None) -> None:
    if not isinstance(response, dict):
        raise SyncPackageError("response: debe ser un objeto")
    _require_keys(
        response,
        {"schema_version", "package_id", "status", "changes", "totals", "warnings"},
        "response",
    )
    if response["schema_version"] != SCHEMA_VERSION:
        raise SyncPackageError(f"schema_version: solo se admite la versión {SCHEMA_VERSION}")
    _parse_uuid(response["package_id"], "package_id")
    if expected_package_id is not None and response["package_id"] != expected_package_id:
        raise SyncPackageError("package_id: la confirmación corresponde a otro paquete")
    if response["status"] not in {"applied", "already_applied"}:
        raise SyncPackageError("status: respuesta de sincronización desconocida")
    for field in ("changes", "totals"):
        counts = response[field]
        if not isinstance(counts, dict) or not all(
            isinstance(name, str) and name and isinstance(value, int)
            and not isinstance(value, bool) and value >= 0
            for name, value in counts.items()
        ):
            raise SyncPackageError(f"{field}: debe contener contadores enteros no negativos")
    if not isinstance(response["warnings"], list) or not all(
        isinstance(item, str) for item in response["warnings"]
    ):
        raise SyncPackageError("warnings: debe ser una lista de textos")


def _utc_text(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rows(connection: Any, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def build_sync_package(
    database: Path | str,
    *,
    agent_id: str,
    source_timezone: str,
    package_id: str | None = None,
) -> dict[str, Any]:
    from .db import connect_database

    _parse_uuid(agent_id, "agent_id")
    try:
        ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError as error:
        raise SyncPackageError("source_timezone: zona IANA inválida") from error
    database_path = Path(database).expanduser().resolve()
    if not database_path.is_file():
        raise SyncPackageError("La base SQLite no existe")
    connection = connect_database(database_path)
    try:
        snapshot = connection.execute(
            """
            SELECT id, device_key, mount_point, mount_read_only, started_at,
                   completed_at, warning_count, summary_json
            FROM device_snapshots
            WHERE status = 'completed'
            ORDER BY started_at DESC LIMIT 1
            """
        ).fetchone()
        if snapshot is None:
            raise SyncPackageError("No hay una sincronización completa para exportar")
        if not snapshot["mount_read_only"]:
            raise SyncPackageError("La última sincronización no verificó un montaje de solo lectura")

        entities = {
            "works": _rows(connection, "works"),
            "editions": _rows(connection, "editions"),
            "contributors": _rows(connection, "contributors"),
            "edition_contributors": [
                {"id": f"{row['edition_id']}:{row['contributor_id']}:{row['role']}", **dict(row)}
                for row in connection.execute("SELECT * FROM edition_contributors ORDER BY edition_id, display_order, contributor_id")
            ],
            "deliveries": _rows(connection, "kindle_deliveries"),
            "external_identifiers": _rows(connection, "external_identifiers"),
            "title_aliases": _rows(connection, "title_aliases"),
            "source_observations": [
                {key: value for key, value in dict(row).items() if key != "snapshot_id"}
                for row in connection.execute("SELECT * FROM source_observations ORDER BY rowid")
            ],
            "annotations": _rows(connection, "annotations"),
            "annotation_occurrences": _rows(connection, "annotation_occurrences"),
            "reading_states": _rows(connection, "reading_states"),
            "reading_history_records": _rows(connection, "reading_history_records"),
        }
        warnings = json.loads(snapshot["summary_json"]).get("warnings", [])
        package = {
            "schema_version": SCHEMA_VERSION,
            "package_id": package_id or str(uuid4()),
            "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "agent_id": agent_id,
            "device_key": snapshot["device_key"],
            "snapshot": {
                "kind": "full",
                "started_at_utc": _utc_text(snapshot["started_at"]),
                "completed_at_utc": _utc_text(snapshot["completed_at"] or snapshot["started_at"]),
                "mount_read_only": True,
                "source_timezone": source_timezone,
            },
            "entities": entities,
            "present_delivery_ids": [
                row["id"] for row in entities["deliveries"] if row["presence"] == "present"
            ],
            "warnings": [str(item) for item in warnings],
        }
        validate_sync_package(package)
        package["_local_mount_point"] = snapshot["mount_point"]
        return package
    finally:
        connection.close()


def write_sync_package(package: dict[str, Any], output: Path | str) -> SyncExportResult:
    package = dict(package)
    mount_point = package.pop("_local_mount_point", None)
    validate_sync_package(package)
    output_path = Path(output).expanduser().resolve()
    if mount_point is not None and output_path.is_relative_to(Path(mount_point).resolve()):
        raise SyncPackageError("El paquete no puede guardarse dentro del Kindle")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, output_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return SyncExportResult(
        package_id=package["package_id"], output=output_path,
        sha256=hashlib.sha256(data).hexdigest(), byte_count=len(data),
        entity_count=sum(len(package["entities"][group]) for group in ENTITY_GROUPS),
    )
