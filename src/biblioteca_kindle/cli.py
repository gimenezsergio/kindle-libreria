from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .db import migrate_database
from .inventory import InventoryError, run_inventory
from .manifests import ManifestImportError, import_manifests
from .vocabulary import VocabularyImportError, import_vocabulary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="biblioteca-kindle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser(
        "init-db", help="Crear o actualizar una base SQLite local"
    )
    init_db.add_argument("database", type=Path, help="Ruta del archivo SQLite")

    inventory = subparsers.add_parser(
        "inventory", help="Inventariar un Kindle sin modificarlo"
    )
    inventory.add_argument("mount", type=Path, help="Punto de montaje del Kindle")
    inventory.add_argument(
        "--database", required=True, type=Path, help="Base SQLite fuera del Kindle"
    )

    manifests = subparsers.add_parser(
        "import-manifests", help="Importar entregas desde una instantánea completa"
    )
    manifests.add_argument("mount", type=Path, help="Punto de montaje del Kindle")
    manifests.add_argument(
        "--database", required=True, type=Path, help="Base SQLite fuera del Kindle"
    )
    manifests.add_argument("--snapshot", help="ID de instantánea; usa la última si se omite")

    vocabulary = subparsers.add_parser(
        "import-vocabulary", help="Enriquecer el catálogo desde vocab.db"
    )
    vocabulary.add_argument("mount", type=Path, help="Punto de montaje del Kindle")
    vocabulary.add_argument(
        "--database", required=True, type=Path, help="Base SQLite fuera del Kindle"
    )
    vocabulary.add_argument("--snapshot", help="ID de instantánea; usa la última si se omite")
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
    if args.command == "inventory":
        try:
            result = run_inventory(args.mount, args.database)
        except InventoryError as error:
            print(f"Error de inventario: {error}")
            return 1
        print(
            f"Instantánea completa: {result.file_count} archivos, "
            f"{result.total_bytes} bytes, {result.warning_count} advertencias."
        )
        return 0
    if args.command == "import-vocabulary":
        try:
            result = import_vocabulary(
                args.mount, args.database, snapshot_id=args.snapshot
            )
        except (VocabularyImportError, InventoryError) as error:
            print(f"Error de vocabulario: {error}")
            return 1
        print(
            f"BOOK_INFO: {result.rows}; vinculados: {result.matched}; "
            f"sin entrega coincidente: {result.unmatched}."
        )
        return 0
    if args.command == "import-manifests":
        try:
            result = import_manifests(
                args.mount, args.database, snapshot_id=args.snapshot
            )
        except (ManifestImportError, InventoryError) as error:
            print(f"Error de manifiestos: {error}")
            return 1
        print(
            f"Manifiestos importados: {result.imported}; "
            f"entregas nuevas: {result.created}; actualizadas: {result.updated}."
        )
        return 0
    return 2
