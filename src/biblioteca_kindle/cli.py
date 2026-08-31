from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .db import migrate_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="biblioteca-kindle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser(
        "init-db", help="Crear o actualizar una base SQLite local"
    )
    init_db.add_argument("database", type=Path, help="Ruta del archivo SQLite")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init-db":
        applied = migrate_database(args.database)
        if applied:
            print(f"Migraciones aplicadas: {', '.join(applied)}")
        else:
            print("La base ya estaba actualizada.")
        return 0
    return 2

