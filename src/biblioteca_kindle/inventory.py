from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .db import connect_database, migrate_database


BOOK_EXTENSIONS = {".azw", ".azw3", ".kfx", ".mobi", ".pdf", ".prc"}
SIDECAR_EXTENSIONS = {
    ".apnx",
    ".asc",
    ".azw3f",
    ".azw3r",
    ".han",
    ".mbp1",
    ".mbs",
    ".meta",
    ".mf",
    ".pds",
    ".pdt",
    ".phl",
    ".yjf",
    ".yjr",
}
SYSTEM_DATABASES = {
    "system/fmcache/fmcache.db",
    "system/isd.db",
    "system/readingstreams/readingstreams.db",
    "system/vocabulary/vocab.db",
}


class InventoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class MountStatus:
    source: str
    target: Path
    filesystem: str
    options: frozenset[str]

    @property
    def read_only(self) -> bool:
        return "ro" in self.options


@dataclass(frozen=True)
class InventoryResult:
    snapshot_id: str
    file_count: int
    total_bytes: int
    warning_count: int


def _unescape_mount_field(value: str) -> str:
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )


def inspect_mount(
    requested_path: Path | str,
    mountinfo_path: Path | str = "/proc/self/mountinfo",
) -> MountStatus:
    requested = Path(requested_path).expanduser().resolve()
    candidates: list[MountStatus] = []
    for line in Path(mountinfo_path).read_text(encoding="utf-8").splitlines():
        before, separator, after = line.partition(" - ")
        if not separator:
            continue
        left = before.split()
        right = after.split()
        if len(left) < 6 or len(right) < 2:
            continue
        target = Path(_unescape_mount_field(left[4])).resolve()
        try:
            requested.relative_to(target)
        except ValueError:
            continue
        options = frozenset(left[5].split(","))
        candidates.append(
            MountStatus(
                source=_unescape_mount_field(right[1]),
                target=target,
                filesystem=right[0],
                options=options,
            )
        )
    if not candidates:
        raise InventoryError(f"No se encontró un montaje para {requested}")
    return max(candidates, key=lambda item: len(item.target.parts))


def validate_kindle_root(root: Path | str) -> Path:
    kindle_root = Path(root).expanduser().resolve()
    if not kindle_root.is_dir():
        raise InventoryError(f"El punto de montaje no existe: {kindle_root}")
    if not (kindle_root / "documents").is_dir():
        raise InventoryError("La ruta no contiene el directorio documents de Kindle")
    if not (kindle_root / "system").is_dir():
        raise InventoryError("La ruta no contiene el directorio system de Kindle")
    return kindle_root


def ensure_output_outside_kindle(root: Path, database: Path | str) -> Path:
    database_path = Path(database).expanduser().resolve()
    try:
        database_path.relative_to(root)
    except ValueError:
        return database_path
    raise InventoryError("La base de datos no puede estar dentro del Kindle")


def _source_type(relative_path: Path) -> str | None:
    posix = relative_path.as_posix()
    suffix = relative_path.suffix.casefold()
    if posix == "documents/My Clippings.txt":
        return "clippings"
    if posix in SYSTEM_DATABASES:
        return "database"
    if posix == "metadata.calibre":
        return "calibre"
    if suffix in BOOK_EXTENSIONS and relative_path.parts[0] == "documents":
        return "book"
    if ".sdr" in relative_path.as_posix().casefold() and suffix in SIDECAR_EXTENSIONS:
        return "sidecar"
    return None


def iter_inventory_files(root: Path) -> Iterable[tuple[Path, Path, str]]:
    for directory, names, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        names[:] = sorted(name for name in names if not (directory_path / name).is_symlink())
        for filename in sorted(filenames):
            path = directory_path / filename
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError as exc:
                raise InventoryError(f"Archivo fuera del Kindle: {path}") from exc
            source_type = _source_type(relative)
            if source_type is not None:
                yield resolved, relative, source_type


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _device_key(mount: MountStatus, root: Path) -> str:
    material = f"{mount.source}\0{root.stat().st_dev}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def run_inventory(
    kindle_root: Path | str,
    database: Path | str,
    *,
    mount_status: MountStatus | None = None,
) -> InventoryResult:
    root = validate_kindle_root(kindle_root)
    database_path = ensure_output_outside_kindle(root, database)
    mount = mount_status or inspect_mount(root)
    try:
        root.relative_to(mount.target)
    except ValueError as exc:
        raise InventoryError("El montaje detectado no contiene la ruta Kindle") from exc

    warnings = [] if mount.read_only else ["El montaje no está marcado como solo lectura"]
    migrate_database(database_path)
    connection = connect_database(database_path)
    snapshot_id = str(uuid.uuid4())
    started_at = _utc_now()
    connection.execute(
        """
        INSERT INTO device_snapshots(
            id, device_key, mount_point, mount_read_only, status,
            started_at, summary_json, warning_count
        ) VALUES (?, ?, ?, ?, 'running', ?, '{}', ?)
        """,
        (
            snapshot_id,
            _device_key(mount, root),
            str(root),
            int(mount.read_only),
            started_at,
            len(warnings),
        ),
    )
    connection.commit()

    file_count = 0
    total_bytes = 0
    counts_by_type: dict[str, int] = {}
    try:
        for path, relative, source_type in iter_inventory_files(root):
            stat = path.stat()
            observed_at = _utc_now()
            connection.execute(
                """
                INSERT INTO source_observations(
                    id, snapshot_id, source_type, source_relative_path,
                    file_size, file_modified_at, file_hash, observed_at,
                    parse_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    str(uuid.uuid4()),
                    snapshot_id,
                    source_type,
                    relative.as_posix(),
                    stat.st_size,
                    datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    hash_file(path),
                    observed_at,
                ),
            )
            file_count += 1
            total_bytes += stat.st_size
            counts_by_type[source_type] = counts_by_type.get(source_type, 0) + 1

        summary = {
            "file_count": file_count,
            "total_bytes": total_bytes,
            "counts_by_type": counts_by_type,
            "warnings": warnings,
        }
        connection.execute(
            """
            UPDATE device_snapshots
            SET status = 'completed', completed_at = ?, summary_json = ?
            WHERE id = ?
            """,
            (_utc_now(), json.dumps(summary, sort_keys=True), snapshot_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        connection.execute(
            """
            UPDATE device_snapshots
            SET status = 'failed', completed_at = ?, warning_count = warning_count + 1
            WHERE id = ?
            """,
            (_utc_now(), snapshot_id),
        )
        connection.commit()
        raise
    finally:
        connection.close()

    return InventoryResult(
        snapshot_id=snapshot_id,
        file_count=file_count,
        total_bytes=total_bytes,
        warning_count=len(warnings),
    )

