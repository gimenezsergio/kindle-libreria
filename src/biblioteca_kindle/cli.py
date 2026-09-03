from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Sequence

from .db import migrate_database
from .inventory import InventoryError, run_inventory
from .manifests import ManifestImportError, import_manifests
from .vocabulary import VocabularyImportError, import_vocabulary
from .clippings import ClippingsImportError, import_clippings
from .progress import ProgressImportError, import_progress
from .annotations import AnnotationImportError, import_annotations
from .sync import synchronize
from .personal import (
    PersonalDataError,
    add_work_note,
    add_work_relation,
    assign_work_to_collection,
    create_collection,
)
from .reports import ReportError, library_summary, work_card
from .web import run_server
from .remote_sync import SyncPackageError, build_sync_package, write_sync_package
from .remote_client import RemotePushError, push_sync
from .backup import BackupError, create_database_backup


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

    clippings = subparsers.add_parser(
        "import-clippings", help="Importar My Clippings.txt con procedencia"
    )
    clippings.add_argument("mount", type=Path, help="Punto de montaje del Kindle")
    clippings.add_argument(
        "--database", required=True, type=Path, help="Base SQLite fuera del Kindle"
    )
    clippings.add_argument("--snapshot", help="ID de instantánea; usa la última si se omite")

    progress = subparsers.add_parser(
        "import-progress", help="Importar posiciones y métricas KRDS"
    )
    progress.add_argument("mount", type=Path, help="Punto de montaje del Kindle")
    progress.add_argument(
        "--database", required=True, type=Path, help="Base SQLite fuera del Kindle"
    )
    progress.add_argument("--snapshot", help="ID de instantánea; usa la última si se omite")

    annotations = subparsers.add_parser(
        "import-annotations", help="Importar anotaciones locales KRDS y HAN"
    )
    annotations.add_argument("mount", type=Path, help="Punto de montaje del Kindle")
    annotations.add_argument(
        "--database", required=True, type=Path, help="Base SQLite fuera del Kindle"
    )
    annotations.add_argument("--snapshot", help="ID de instantánea; usa la última si se omite")

    sync = subparsers.add_parser(
        "sync", help="Ejecutar la sincronización completa de solo lectura"
    )
    sync.add_argument("mount", type=Path, help="Punto de montaje del Kindle")
    sync.add_argument(
        "--database", required=True, type=Path, help="Base SQLite fuera del Kindle"
    )

    export_sync = subparsers.add_parser(
        "export-sync", help="Crear un paquete local para sincronización remota"
    )
    export_sync.add_argument("--database", required=True, type=Path)
    export_sync.add_argument("--output", required=True, type=Path)
    export_sync.add_argument("--agent-id", required=True)
    export_sync.add_argument(
        "--timezone",
        default=os.environ.get("KINDLE_TIMEZONE", "America/Argentina/Buenos_Aires"),
        help="Zona IANA configurada en el Kindle",
    )

    push = subparsers.add_parser(
        "push", help="Leer el Kindle y enviar una sincronización al servidor"
    )
    push.add_argument("mount", type=Path, help="Punto de montaje del Kindle")
    push.add_argument("--database", required=True, type=Path)
    push.add_argument("--server")
    push.add_argument("--state-dir", type=Path)
    push.add_argument(
        "--timezone",
        default=None,
    )

    backup = subparsers.add_parser(
        "backup", help="Crear una copia consistente y verificable de SQLite"
    )
    backup.add_argument("--database", required=True, type=Path)
    backup.add_argument("--output", required=True, type=Path)

    collection_add = subparsers.add_parser(
        "collection-add", help="Crear una colección local"
    )
    collection_add.add_argument("name")
    collection_add.add_argument("--database", required=True, type=Path)
    collection_add.add_argument("--parent")
    collection_add.add_argument("--description")

    collection_assign = subparsers.add_parser(
        "collection-assign", help="Asignar una obra a una colección"
    )
    collection_assign.add_argument("work_id")
    collection_assign.add_argument("collection_id")
    collection_assign.add_argument("--database", required=True, type=Path)
    collection_assign.add_argument("--note")
    collection_assign.add_argument("--order", type=int, default=0)

    note_add = subparsers.add_parser("note-add", help="Añadir una nota propia a una obra")
    note_add.add_argument("work_id")
    note_add.add_argument("body")
    note_add.add_argument("--database", required=True, type=Path)

    relation_add = subparsers.add_parser(
        "relation-add", help="Relacionar dos obras"
    )
    relation_add.add_argument("source_work_id")
    relation_add.add_argument("target_work_id")
    relation_add.add_argument("relation_type")
    relation_add.add_argument("--database", required=True, type=Path)
    relation_add.add_argument("--label")
    relation_add.add_argument("--explanation")
    relation_add.add_argument("--symmetric", action="store_true")

    report = subparsers.add_parser("report", help="Mostrar el resumen local de la biblioteca")
    report.add_argument("--database", required=True, type=Path)

    work_show = subparsers.add_parser("work-show", help="Mostrar la ficha textual de una obra")
    work_show.add_argument("work_id")
    work_show.add_argument("--database", required=True, type=Path)
    work_show.add_argument("--include-private", action="store_true")

    serve = subparsers.add_parser("serve", help="Abrir el servidor web local")
    serve.add_argument("--database", required=True, type=Path)
    serve.add_argument("--port", type=int, default=8000)
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
    if args.command == "export-sync":
        try:
            package = build_sync_package(
                args.database, agent_id=args.agent_id, source_timezone=args.timezone
            )
            result = write_sync_package(package, args.output)
        except (SyncPackageError, OSError) as error:
            print(f"Error de exportación: {error}")
            return 1
        print(
            f"Paquete creado: {result.output} ({result.entity_count} entidades; "
            f"{result.byte_count} bytes; sha256 {result.sha256}; id {result.package_id})."
        )
        return 0
    if args.command == "backup":
        try:
            result = create_database_backup(args.database, args.output)
        except (BackupError, OSError, sqlite3.Error) as error:
            print(f"Error de respaldo: {error}")
            return 1
        print(
            f"Respaldo verificado: {result.output} ({result.byte_count} bytes; "
            f"integridad {result.integrity}; sha256 {result.sha256})."
        )
        return 0
    if args.command == "push":
        load_environment_file(args.database.parent / ".env")
        server_url = args.server or os.environ.get("BIBLIOTECA_SERVER_URL")
        source_timezone = args.timezone or os.environ.get(
            "KINDLE_TIMEZONE", "America/Argentina/Buenos_Aires"
        )
        if not server_url:
            print("Error de envío: falta BIBLIOTECA_SERVER_URL o --server")
            return 1
        try:
            local = synchronize(args.mount, args.database)
            pushed = push_sync(
                args.database,
                server_url=server_url,
                token=os.environ.get("BIBLIOTECA_SYNC_TOKEN", ""),
                state_directory=args.state_dir or args.database.parent / "sync-agent",
                source_timezone=source_timezone,
            )
        except (InventoryError, ManifestImportError, VocabularyImportError,
                ClippingsImportError, ProgressImportError, AnnotationImportError,
                SyncPackageError, RemotePushError, OSError) as error:
            print(f"Error de envío: {error}")
            return 1
        response = pushed.response
        changes, totals = response["changes"], response["totals"]
        print(
            f"Sincronización remota confirmada en {pushed.attempts} intento(s): "
            f"{changes.get('works_created', 0)} obras nuevas; "
            f"{changes.get('annotations_created', 0)} anotaciones nuevas; "
            f"{changes.get('books_marked_absent', 0)} libros ausentes."
        )
        print(
            f"Servidor: {totals.get('works', 0)} obras; "
            f"{totals.get('books_present', 0)} libros presentes; "
            f"{totals.get('annotations', 0)} anotaciones. "
            f"Kindle local: {local.inventory.file_count} fuentes leídas."
        )
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
    if args.command == "sync":
        try:
            result = synchronize(args.mount, args.database)
        except (InventoryError, ManifestImportError, VocabularyImportError,
                ClippingsImportError, ProgressImportError, AnnotationImportError) as error:
            print(f"Error de sincronización: {error}")
            return 1
        clippings_created = result.clippings.created if result.clippings else 0
        new_annotations = clippings_created + result.annotations.created
        existing_clippings = result.clippings.existing if result.clippings else 0
        existing_annotations = existing_clippings + result.annotations.existing
        print("Sincronización completa.")
        print(
            f"Cambios: {result.manifests.created} libros nuevos; "
            f"{result.manifests.updated} libros ya conocidos actualizados; "
            f"{new_annotations} registros de anotación nuevos; "
            f"{existing_annotations} registros de fuente ya conocidos; "
            f"{result.marked_absent} libros marcados como ausentes."
        )
        print(
            f"Biblioteca: {result.summary.works} obras; "
            f"{result.summary.deliveries_present} libros presentes; "
            f"{result.summary.deliveries_absent} ausentes."
        )
        print(
            f"Anotaciones Kindle: {result.summary.annotations} en total "
            f"({result.summary.highlights} subrayados; "
            f"{result.summary.notes} notas; "
            f"{result.summary.bookmarks} marcadores; "
            f"{result.summary.other_annotations} otras)."
        )
        print(
            f"Datos complementarios: {result.progress.imported} estados de lectura; "
            f"{result.summary.personal_notes} notas propias; "
            f"{result.reconciliation.resolved_aliases} identidades reconciliadas; "
            f"{result.reconciliation.merged_annotations} duplicados entre fuentes unificados; "
            f"{result.reconciliation.revised_annotations} revisiones de subrayado unificadas; "
            f"{result.inventory.warning_count + result.annotations.warnings + result.progress.warnings} advertencias."
        )
        return 0
    if args.command == "collection-add":
        try:
            result = create_collection(
                args.database,
                args.name,
                parent_id=args.parent,
                description=args.description,
            )
        except PersonalDataError as error:
            print(f"Error de colección: {error}")
            return 1
        print(f"Colección {'creada' if result.created else 'actualizada'}: {result.id}")
        return 0
    if args.command == "collection-assign":
        try:
            created = assign_work_to_collection(
                args.database,
                args.work_id,
                args.collection_id,
                note=args.note,
                display_order=args.order,
            )
        except PersonalDataError as error:
            print(f"Error de asignación: {error}")
            return 1
        print("Asignación creada." if created else "Asignación actualizada.")
        return 0
    if args.command == "note-add":
        try:
            identifier = add_work_note(args.database, args.work_id, args.body)
        except PersonalDataError as error:
            print(f"Error de nota: {error}")
            return 1
        print(f"Nota creada: {identifier}")
        return 0
    if args.command == "relation-add":
        try:
            result = add_work_relation(
                args.database,
                args.source_work_id,
                args.target_work_id,
                args.relation_type,
                label=args.label,
                explanation=args.explanation,
                symmetric=args.symmetric,
            )
        except PersonalDataError as error:
            print(f"Error de relación: {error}")
            return 1
        print(f"Relación {'creada' if result.created else 'actualizada'}: {result.id}")
        return 0
    if args.command == "report":
        try:
            print(library_summary(args.database))
        except ReportError as error:
            print(f"Error de reporte: {error}")
            return 1
        return 0
    if args.command == "work-show":
        try:
            print(work_card(args.database, args.work_id, include_private=args.include_private))
        except ReportError as error:
            print(f"Error de ficha: {error}")
            return 1
        return 0
    if args.command == "serve":
        try:
            run_server(args.database, port=args.port)
        except ValueError as error:
            print(f"Error del servidor: {error}")
            return 1
        return 0
    if args.command == "import-annotations":
        try:
            result = import_annotations(
                args.mount, args.database, snapshot_id=args.snapshot
            )
        except (AnnotationImportError, InventoryError) as error:
            print(f"Error de anotaciones: {error}")
            return 1
        print(
            f"KRDS: {result.krds_annotations} anotaciones en {result.krds_files} archivos; "
            f"HAN: {result.han_annotations} en {result.han_files}; nuevas: "
            f"{result.created}; existentes: {result.existing}; fuentes sin entrega: "
            f"{result.unmatched_files}; advertencias: {result.warnings}."
        )
        return 0
    if args.command == "import-progress":
        try:
            result = import_progress(
                args.mount, args.database, snapshot_id=args.snapshot
            )
        except (ProgressImportError, InventoryError) as error:
            print(f"Error de progreso: {error}")
            return 1
        print(
            f"Sidecars de progreso: {result.files}; importados: {result.imported}; "
            f"sin entrega: {result.unmatched}; con fpr: "
            f"{result.with_furthest_position}; con temporizador: {result.with_timer}; "
            f"historiales: {result.history_records}; advertencias: {result.warnings}."
        )
        return 0
    if args.command == "import-clippings":
        try:
            result = import_clippings(
                args.mount, args.database, snapshot_id=args.snapshot
            )
        except (ClippingsImportError, InventoryError) as error:
            print(f"Error de clippings: {error}")
            return 1
        print(
            f"Clippings: {result.entries}; nuevos: {result.created}; "
            f"existentes: {result.existing}; encabezados vinculados: "
            f"{result.matched_headings}; provisionales: {result.provisional_headings}; "
            f"ambiguos: {result.ambiguous_headings}."
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
