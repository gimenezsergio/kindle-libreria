from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupResult:
    output: Path
    byte_count: int
    sha256: str
    integrity: str


def create_database_backup(database: Path | str, output: Path | str) -> BackupResult:
    source = Path(database).expanduser().resolve()
    destination = Path(output).expanduser().resolve()
    if not source.is_file():
        raise BackupError("La base SQLite de origen no existe")
    if source == destination:
        raise BackupError("El respaldo no puede sobrescribir la base activa")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        target_connection = sqlite3.connect(temporary)
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
            integrity = str(target_connection.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity != "ok":
                raise BackupError(f"El respaldo no superó integrity_check: {integrity}")
        finally:
            target_connection.close()
            source_connection.close()
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        os.replace(temporary, destination)
        return BackupResult(
            output=destination,
            byte_count=destination.stat().st_size,
            sha256=digest,
            integrity=integrity,
        )
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
