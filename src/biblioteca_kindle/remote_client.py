from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from .remote_sync import (
    build_sync_package,
    validate_sync_package,
    validate_sync_response,
    write_sync_package,
)


class RemotePushError(RuntimeError):
    pass


@dataclass(frozen=True)
class PushResult:
    response: dict[str, Any]
    attempts: int
    reused_pending: bool


def _endpoint(server_url: str) -> str:
    parsed = urlparse(server_url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise RemotePushError("El servidor remoto debe usar HTTPS; HTTP solo se admite en localhost")
    if not parsed.hostname or parsed.username or parsed.password:
        raise RemotePushError("La URL del servidor no es válida")
    return server_url.rstrip("/") + "/api/sync/v1/packages"


def _agent_id(state_directory: Path) -> str:
    path = state_directory / "agent-id"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    identifier = str(uuid4())
    state_directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(identifier + "\n")
    return identifier


def push_sync(
    database: Path | str,
    *,
    server_url: str,
    token: str,
    state_directory: Path | str,
    source_timezone: str,
    attempts: int = 3,
    opener: Callable[..., Any] = urlopen,
) -> PushResult:
    if not token:
        raise RemotePushError("Falta BIBLIOTECA_SYNC_TOKEN")
    endpoint = _endpoint(server_url)
    state = Path(state_directory).expanduser().resolve()
    pending = state / "pending-sync-package.json"
    reused = pending.is_file()
    if reused:
        package = json.loads(pending.read_text(encoding="utf-8"))
        validate_sync_package(package)
    else:
        package = build_sync_package(
            database, agent_id=_agent_id(state), source_timezone=source_timezone
        )
        write_sync_package(package, pending)
        package.pop("_local_mount_point", None)
    body = json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for number in range(1, max(1, attempts) + 1):
        try:
            with opener(request, timeout=60) as response:
                received = json.loads(response.read().decode("utf-8"))
            validate_sync_response(received, expected_package_id=package["package_id"])
            pending.unlink()
            return PushResult(received, number, reused)
        except HTTPError as error:
            if error.code < 500:
                raise RemotePushError(f"El servidor rechazó el paquete (HTTP {error.code})") from error
            last_error = error
        except (URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            last_error = error
    raise RemotePushError(
        f"No se confirmó el paquete después de {max(1, attempts)} intentos; quedó pendiente"
    ) from last_error
