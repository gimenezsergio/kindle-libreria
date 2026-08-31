from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from .db import connect_database
from .inventory import InventoryError, hash_file, validate_kindle_root


class ClippingsImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClippingRecord:
    source_key: str
    heading: str
    metadata: str
    position: str | None
    date_text: str | None
    kind: str
    content: str | None


@dataclass(frozen=True)
class ClippingsImportResult:
    snapshot_id: str
    entries: int
    created: int
    existing: int
    matched_headings: int
    provisional_headings: int
    ambiguous_headings: int


def normalize_title(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _heading_variants(heading: str) -> list[str]:
    variants = [normalize_title(heading)]
    without_final_parenthetical = re.sub(r"\s*\([^()]*\)\s*$", "", heading).strip()
    normalized_without = normalize_title(without_final_parenthetical)
    if normalized_without and normalized_without not in variants:
        variants.append(normalized_without)
    return variants


def _display_title(heading: str) -> str:
    stripped = re.sub(r"\s*\([^()]*\)\s*$", "", heading).strip()
    return stripped or heading.strip()


def _stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"biblioteca-kindle:{kind}:{value}"))


def _classify_kind(metadata: str) -> str:
    lowered = metadata.casefold()
    if "highlight" in lowered or "subrayado" in lowered:
        return "highlight"
    if "bookmark" in lowered or "marcador" in lowered:
        return "bookmark"
    if "note" in lowered or "nota" in lowered:
        return "note"
    return "other"


def parse_clippings(data: bytes) -> list[ClippingRecord]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ClippingsImportError("My Clippings.txt no está codificado como UTF-8") from exc
    blocks = [
        block.strip("\r\n")
        for block in re.split(r"\r?\n==========\r?\n?", text)
        if block.strip()
    ]
    records: list[ClippingRecord] = []
    for index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        nonempty_indices = [i for i, line in enumerate(lines) if line.strip()]
        if len(nonempty_indices) < 2:
            raise ClippingsImportError(
                f"Entrada {index} sin encabezado y metadata suficientes"
            )
        heading_index, metadata_index = nonempty_indices[:2]
        heading = lines[heading_index].strip()
        metadata = lines[metadata_index].strip()
        content_lines = lines[metadata_index + 1 :]
        while content_lines and not content_lines[0].strip():
            content_lines.pop(0)
        content = "\n".join(content_lines).strip() or None
        metadata_parts = [part.strip() for part in metadata.split("|", 1)]
        position = metadata_parts[0] or None
        date_text = metadata_parts[1] if len(metadata_parts) == 2 else None
        canonical = "\n".join(line.rstrip() for line in lines).strip()
        records.append(
            ClippingRecord(
                source_key=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                heading=heading,
                metadata=metadata,
                position=position,
                date_text=date_text,
                kind=_classify_kind(metadata),
                content=content,
            )
        )
    return records


def _snapshot(
    connection: sqlite3.Connection, root: Path, snapshot_id: str | None
) -> sqlite3.Row:
    if snapshot_id is None:
        row = connection.execute(
            """
            SELECT id, started_at FROM device_snapshots
            WHERE status = 'completed' AND mount_point = ?
            ORDER BY started_at DESC LIMIT 1
            """,
            (str(root),),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT id, started_at FROM device_snapshots
            WHERE id = ? AND status = 'completed' AND mount_point = ?
            """,
            (snapshot_id, str(root)),
        ).fetchone()
    if row is None:
        raise ClippingsImportError("No hay una instantánea completa válida")
    return row


def _edition_index(connection: sqlite3.Connection) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for row in connection.execute("SELECT id, title FROM editions"):
        normalized = normalize_title(row["title"])
        if normalized:
            index.setdefault(normalized, set()).add(row["id"])
    for row in connection.execute(
        "SELECT edition_id, normalized_title FROM title_aliases WHERE edition_id IS NOT NULL"
    ):
        index.setdefault(row["normalized_title"], set()).add(row["edition_id"])
    return index


def _resolve_or_create_edition(
    connection: sqlite3.Connection,
    index: dict[str, set[str]],
    heading: str,
    observation_id: str,
) -> tuple[str, str]:
    candidates: set[str] = set()
    for variant in _heading_variants(heading):
        matches = index.get(variant, set())
        if matches:
            candidates.update(matches)
            break
    if len(candidates) == 1:
        return next(iter(candidates)), "matched"

    normalized = _heading_variants(heading)[0]
    status = "conflict" if candidates else "provisional"
    edition_id = _stable_id(f"clippings-{status}-edition", normalized)
    work_id = _stable_id(f"clippings-{status}-work", normalized)
    title = _display_title(heading)
    connection.execute(
        """
        INSERT INTO works(id, preferred_title, merge_status)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (work_id, title, "review" if candidates else "provisional"),
    )
    connection.execute(
        """
        INSERT INTO editions(id, work_id, title)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (edition_id, work_id, title),
    )
    connection.execute(
        """
        INSERT INTO title_aliases(
            id, edition_id, original_title, normalized_title,
            source_observation_id, confidence, resolution_status
        ) VALUES (?, ?, ?, ?, ?, 'low', ?)
        ON CONFLICT(id) DO UPDATE SET
            source_observation_id = excluded.source_observation_id
        """,
        (
            _stable_id(f"clippings-{status}-alias", normalized),
            edition_id,
            heading,
            normalized,
            observation_id,
            status,
        ),
    )
    index.setdefault(normalized, set()).add(edition_id)
    return edition_id, status


def import_clippings(
    kindle_root: Path | str,
    database: Path | str,
    *,
    snapshot_id: str | None = None,
) -> ClippingsImportResult:
    root = validate_kindle_root(kindle_root)
    database_path = Path(database).expanduser().resolve()
    try:
        database_path.relative_to(root)
    except ValueError:
        pass
    else:
        raise InventoryError("La base de datos no puede estar dentro del Kindle")
    if not database_path.is_file():
        raise ClippingsImportError("La base SQLite todavía no existe")

    connection = connect_database(database_path)
    try:
        snapshot = _snapshot(connection, root, snapshot_id)
        snapshot_id = snapshot["id"]
        observation = connection.execute(
            """
            SELECT id, source_relative_path, file_hash, observed_at
            FROM source_observations
            WHERE snapshot_id = ? AND source_type = 'clippings'
            """,
            (snapshot_id,),
        ).fetchone()
        if observation is None:
            raise ClippingsImportError("La instantánea no contiene My Clippings.txt")
        source = (root / observation["source_relative_path"]).resolve()
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise ClippingsImportError("La ruta de clippings sale del Kindle") from exc
        if not source.is_file():
            raise ClippingsImportError("My Clippings.txt ya no existe")
        if hash_file(source) != observation["file_hash"]:
            raise ClippingsImportError(
                "My Clippings.txt cambió después del inventario; creá una nueva instantánea"
            )
        records = parse_clippings(source.read_bytes())
        edition_index = _edition_index(connection)
        heading_resolution: dict[str, tuple[str, str]] = {}
        created = 0
        existing = 0
        with connection:
            for record in records:
                if record.heading not in heading_resolution:
                    heading_resolution[record.heading] = _resolve_or_create_edition(
                        connection,
                        edition_index,
                        record.heading,
                        observation["id"],
                    )
                edition_id, _ = heading_resolution[record.heading]
                annotation_id = _stable_id("clipping-annotation", record.source_key)
                occurrence_id = _stable_id("clipping-occurrence", record.source_key)
                already_exists = connection.execute(
                    """
                    SELECT 1 FROM annotation_occurrences
                    WHERE source_kind = 'clippings' AND source_record_key = ?
                    """,
                    (record.source_key,),
                ).fetchone()
                text = record.content if record.kind == "highlight" else None
                note_text = record.content if record.kind == "note" else None
                connection.execute(
                    """
                    INSERT INTO annotations(
                        id, edition_id, kind, text, note_text,
                        status, native_created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'historical', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        edition_id = excluded.edition_id,
                        kind = excluded.kind,
                        text = excluded.text,
                        note_text = excluded.note_text,
                        native_created_at = excluded.native_created_at,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        annotation_id,
                        edition_id,
                        record.kind,
                        text,
                        note_text,
                        record.date_text,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO annotation_occurrences(
                        id, annotation_id, source_observation_id, source_kind,
                        source_record_key, original_heading, original_position,
                        original_date, observed_at
                    ) VALUES (?, ?, ?, 'clippings', ?, ?, ?, ?, ?)
                    ON CONFLICT(source_kind, source_record_key) DO UPDATE SET
                        source_observation_id = excluded.source_observation_id,
                        observed_at = excluded.observed_at
                    """,
                    (
                        occurrence_id,
                        annotation_id,
                        observation["id"],
                        record.source_key,
                        record.heading,
                        record.position,
                        record.date_text,
                        observation["observed_at"],
                    ),
                )
                if already_exists is None:
                    created += 1
                else:
                    existing += 1
            connection.execute(
                """
                UPDATE source_observations
                SET parser_name = 'clippings', parser_version = '1',
                    parse_status = 'parsed'
                WHERE id = ?
                """,
                (observation["id"],),
            )
        statuses = [status for _, status in heading_resolution.values()]
        return ClippingsImportResult(
            snapshot_id=snapshot_id,
            entries=len(records),
            created=created,
            existing=existing,
            matched_headings=statuses.count("matched"),
            provisional_headings=statuses.count("provisional"),
            ambiguous_headings=statuses.count("conflict"),
        )
    finally:
        connection.close()

