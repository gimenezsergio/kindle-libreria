from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .annotations import AnnotationImportResult, import_annotations
from .clippings import ClippingsImportResult, import_clippings
from .db import connect_database
from .inventory import InventoryResult, MountStatus, run_inventory
from .manifests import ManifestImportResult, import_manifests
from .progress import ProgressImportResult, import_progress
from .reconcile import ReconciliationResult, reconcile_provisional_titles
from .vocabulary import VocabularyImportResult, import_vocabulary


@dataclass(frozen=True)
class SyncResult:
    inventory: InventoryResult
    manifests: ManifestImportResult
    vocabulary: VocabularyImportResult | None
    clippings: ClippingsImportResult | None
    progress: ProgressImportResult
    annotations: AnnotationImportResult
    reconciliation: ReconciliationResult
    marked_absent: int


def _snapshot_has_path(
    database: Path, snapshot_id: str, relative_path: str
) -> bool:
    connection = connect_database(database)
    try:
        return (
            connection.execute(
                """
                SELECT 1 FROM source_observations
                WHERE snapshot_id = ? AND source_relative_path = ?
                """,
                (snapshot_id, relative_path),
            ).fetchone()
            is not None
        )
    finally:
        connection.close()


def _finish_reconciliation(database: Path, snapshot_id: str) -> tuple[ReconciliationResult, int]:
    connection = connect_database(database)
    try:
        with connection:
            result = reconcile_provisional_titles(connection)
            cursor = connection.execute(
                """
                UPDATE kindle_deliveries
                SET presence = 'absent'
                WHERE source_observation_id NOT IN (
                    SELECT id FROM source_observations WHERE snapshot_id = ?
                ) AND presence <> 'absent'
                """,
                (snapshot_id,),
            )
            marked_absent = cursor.rowcount
        return result, marked_absent
    finally:
        connection.close()


def synchronize(
    kindle_root: Path | str,
    database: Path | str,
    *,
    mount_status: MountStatus | None = None,
) -> SyncResult:
    database_path = Path(database).expanduser().resolve()
    inventory = run_inventory(
        kindle_root, database_path, mount_status=mount_status
    )

    snapshot_id = inventory.snapshot_id
    manifests = import_manifests(
        kindle_root, database_path, snapshot_id=snapshot_id
    )
    vocabulary = None
    if _snapshot_has_path(
        database_path, snapshot_id, "system/vocabulary/vocab.db"
    ):
        vocabulary = import_vocabulary(
            kindle_root, database_path, snapshot_id=snapshot_id
        )
    clippings = None
    if _snapshot_has_path(
        database_path, snapshot_id, "documents/My Clippings.txt"
    ):
        clippings = import_clippings(
            kindle_root, database_path, snapshot_id=snapshot_id
        )
    progress = import_progress(
        kindle_root, database_path, snapshot_id=snapshot_id
    )
    annotations = import_annotations(
        kindle_root, database_path, snapshot_id=snapshot_id
    )
    reconciliation, marked_absent = _finish_reconciliation(
        database_path, snapshot_id
    )
    return SyncResult(
        inventory=inventory,
        manifests=manifests,
        vocabulary=vocabulary,
        clippings=clippings,
        progress=progress,
        annotations=annotations,
        reconciliation=reconciliation,
        marked_absent=marked_absent,
    )
