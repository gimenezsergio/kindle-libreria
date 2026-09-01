from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from .db import connect_database


class ProfileError(RuntimeError):
    pass


def _open_database(path: Path | str) -> sqlite3.Connection:
    database = Path(path).expanduser().resolve()
    if not database.is_file():
        raise ProfileError("La base SQLite todavía no existe")
    return connect_database(database)


def _text(value: object, label: str, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ProfileError(f"{label} debe ser texto")
    normalized = value.strip()
    if required and not normalized:
        raise ProfileError(f"{label} no puede quedar vacío")
    return normalized


def create_profile(database: Path | str, *, name: object, description: object = "",
                   prompt: object, is_default: bool = False) -> str:
    profile_name = _text(name, "El nombre", required=True)
    profile_description = _text(description, "La descripción")
    profile_prompt = _text(prompt, "El prompt", required=True)
    identifier = str(uuid.uuid4())
    connection = _open_database(database)
    try:
        with connection:
            if is_default:
                connection.execute("UPDATE ai_profiles SET is_default = 0")
            connection.execute(
                "INSERT INTO ai_profiles(id, name, description, prompt, is_default) VALUES (?, ?, ?, ?, ?)",
                (identifier, profile_name, profile_description, profile_prompt, int(is_default)),
            )
        return identifier
    except sqlite3.IntegrityError as error:
        raise ProfileError("Ya existe un perfil activo con ese nombre") from error
    finally:
        connection.close()


def update_profile(database: Path | str, profile_id: str, payload: dict) -> None:
    connection = _open_database(database)
    try:
        current = connection.execute("SELECT * FROM ai_profiles WHERE id = ?", (profile_id,)).fetchone()
        if current is None:
            raise ProfileError("El perfil no existe")
        name = _text(payload.get("name", current["name"]), "El nombre", required=True)
        description = _text(payload.get("description", current["description"] or ""), "La descripción")
        prompt = _text(payload.get("prompt", current["prompt"]), "El prompt", required=True)
        is_archived = bool(payload.get("is_archived", current["is_archived"]))
        is_default = bool(payload.get("is_default", current["is_default"]))
        if is_archived and is_default:
            raise ProfileError("Un perfil archivado no puede ser el predeterminado")
        with connection:
            if is_default:
                connection.execute("UPDATE ai_profiles SET is_default = 0 WHERE id != ?", (profile_id,))
            connection.execute(
                """UPDATE ai_profiles SET name = ?, description = ?, prompt = ?,
                   is_default = ?, is_archived = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (name, description, prompt, int(is_default), int(is_archived), profile_id),
            )
    except sqlite3.IntegrityError as error:
        raise ProfileError("Ya existe un perfil activo con ese nombre") from error
    finally:
        connection.close()
