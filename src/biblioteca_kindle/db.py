from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def _load_migrations() -> list[Migration]:
    directory = files("biblioteca_kindle").joinpath("migrations")
    migrations: list[Migration] = []
    for resource in sorted(directory.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".sql"):
            continue
        prefix, separator, _ = resource.name.partition("_")
        if not separator or not prefix.isdigit():
            raise RuntimeError(f"Nombre de migración inválido: {resource.name}")
        sql = resource.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=int(prefix),
                name=resource.name,
                sql=sql,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
    versions = [migration.version for migration in migrations]
    if versions != sorted(set(versions)):
        raise RuntimeError("Las versiones de migración deben ser únicas")
    return migrations


def connect_database(path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate_database(path: Path | str) -> list[str]:
    database_path = Path(path).expanduser().resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect_database(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied_rows = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
        ).fetchall()
        applied = {row["version"]: row for row in applied_rows}
        completed: list[str] = []
        for migration in _load_migrations():
            existing = applied.get(migration.version)
            if existing is not None:
                if (
                    existing["name"] != migration.name
                    or existing["checksum"] != migration.checksum
                ):
                    raise RuntimeError(
                        f"La migración aplicada {migration.version} fue modificada"
                    )
                continue
            with connection:
                connection.executescript(migration.sql)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, checksum) "
                    "VALUES (?, ?, ?)",
                    (migration.version, migration.name, migration.checksum),
                )
            completed.append(migration.name)
        return completed
    finally:
        connection.close()

