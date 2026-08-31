from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .db import connect_database
from .inventory import InventoryError, hash_file, validate_kindle_root
from .krds import KRDSError, read_krds


PROGRESS_EXTENSIONS = {".yjf", ".azw3f", ".pdt", ".mbs"}
POSITION_TYPES = {
    ".yjf": "kfx",
    ".azw3f": "azw3",
    ".pdt": "pdf",
    ".mbs": "mobi",
}


class ProgressImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProgressImportResult:
    snapshot_id: str
    files: int
    imported: int
    unmatched: int
    with_furthest_position: int
    with_timer: int
    history_records: int
    warnings: int


def _stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"biblioteca-kindle:{kind}:{value}"))


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
        raise ProgressImportError("No hay una instantánea completa válida")
    return row


def import_progress(
    kindle_root: Path | str,
    database: Path | str,
    *,
    snapshot_id: str | None = None,
) -> ProgressImportResult:
    root = validate_kindle_root(kindle_root)
    database_path = Path(database).expanduser().resolve()
    try:
        database_path.relative_to(root)
    except ValueError:
        pass
    else:
        raise InventoryError("La base de datos no puede estar dentro del Kindle")
    if not database_path.is_file():
        raise ProgressImportError("La base SQLite todavía no existe")

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
        observations = [
            row
            for row in observations
            if PurePosixPath(row["source_relative_path"]).suffix.casefold()
            in PROGRESS_EXTENSIONS
        ]
        deliveries = {
            row["sidecar_relative_path"]: row
            for row in connection.execute(
                """
                SELECT id, sidecar_relative_path FROM kindle_deliveries
                WHERE sidecar_relative_path IS NOT NULL
                """
            )
        }

        parsed: list[tuple[sqlite3.Row, sqlite3.Row, dict, list[str], str]] = []
        unmatched = 0
        for observation in observations:
            relative = PurePosixPath(observation["source_relative_path"])
            delivery = deliveries.get(relative.parent.as_posix())
            if delivery is None:
                unmatched += 1
                continue
            source = (root / relative).resolve()
            try:
                source.relative_to(root)
            except ValueError as exc:
                raise ProgressImportError("Una ruta KRDS sale del Kindle") from exc
            if not source.is_file():
                raise ProgressImportError(f"El sidecar ya no existe: {relative}")
            if hash_file(source) != observation["file_hash"]:
                raise ProgressImportError(
                    f"{relative} cambió después del inventario; creá una nueva instantánea"
                )
            try:
                decoded, warnings = read_krds(source.read_bytes())
            except KRDSError as exc:
                raise ProgressImportError(f"No se pudo leer KRDS: {relative}") from exc
            lpr = decoded.get("lpr")
            if not isinstance(lpr, dict) or lpr.get("position") is None:
                raise ProgressImportError(f"El sidecar no contiene lpr válido: {relative}")
            parsed.append(
                (observation, delivery, decoded, warnings, POSITION_TYPES[relative.suffix.casefold()])
            )

        with_fpr = with_timer = history_total = warning_total = 0
        with connection:
            for observation, delivery, decoded, warnings, position_type in parsed:
                lpr = decoded["lpr"]
                fpr = decoded.get("fpr")
                timer = decoded.get("timer.model")
                history = decoded.get("page.history.store")
                if not isinstance(fpr, dict):
                    fpr = None
                if not isinstance(timer, dict):
                    timer = None
                if not isinstance(history, list):
                    history = []
                state_id = _stable_id(
                    "reading-state", f"{delivery['id']}:{observation['id']}"
                )
                connection.execute(
                    """
                    INSERT INTO reading_states(
                        id, kindle_delivery_id, source_observation_id, observed_at,
                        last_position_native, last_position_type, last_position_at,
                        furthest_position_native, furthest_position_type,
                        furthest_position_at, progress_fraction, progress_method,
                        reading_time_ms, words_read
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                    ON CONFLICT(kindle_delivery_id, source_observation_id) DO UPDATE SET
                        last_position_native = excluded.last_position_native,
                        last_position_type = excluded.last_position_type,
                        last_position_at = excluded.last_position_at,
                        furthest_position_native = excluded.furthest_position_native,
                        furthest_position_type = excluded.furthest_position_type,
                        furthest_position_at = excluded.furthest_position_at,
                        progress_fraction = NULL,
                        progress_method = NULL,
                        reading_time_ms = excluded.reading_time_ms,
                        words_read = excluded.words_read
                    """,
                    (
                        state_id,
                        delivery["id"],
                        observation["id"],
                        observation["observed_at"],
                        str(lpr["position"]),
                        position_type,
                        lpr.get("time"),
                        str(fpr["position"]) if fpr else None,
                        position_type if fpr else None,
                        fpr.get("time") if fpr else None,
                        timer.get("total_time") if timer else None,
                        timer.get("total_words") if timer else None,
                    ),
                )
                connection.execute(
                    "DELETE FROM reading_history_records WHERE reading_state_id = ?",
                    (state_id,),
                )
                for sequence, record in enumerate(history):
                    if not isinstance(record, dict) or record.get("position") is None:
                        warnings.append("page.history.store: registro inválido")
                        continue
                    connection.execute(
                        """
                        INSERT INTO reading_history_records(
                            id, reading_state_id, sequence_number,
                            position_native, recorded_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            _stable_id("reading-history", f"{state_id}:{sequence}"),
                            state_id,
                            sequence,
                            str(record["position"]),
                            record.get("time"),
                        ),
                    )
                    history_total += 1
                connection.execute(
                    """
                    UPDATE source_observations
                    SET parser_name = 'krds-progress', parser_version = '1',
                        parse_status = ?, warning_json = ?
                    WHERE id = ?
                    """,
                    (
                        "warning" if warnings else "parsed",
                        json.dumps(warnings, ensure_ascii=False),
                        observation["id"],
                    ),
                )
                with_fpr += int(fpr is not None)
                with_timer += int(timer is not None)
                warning_total += len(warnings)

        return ProgressImportResult(
            snapshot_id=snapshot_id,
            files=len(observations),
            imported=len(parsed),
            unmatched=unmatched,
            with_furthest_position=with_fpr,
            with_timer=with_timer,
            history_records=history_total,
            warnings=warning_total,
        )
    finally:
        connection.close()

