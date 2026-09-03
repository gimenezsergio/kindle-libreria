from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.clippings import import_clippings
from biblioteca_kindle.db import connect_database
from biblioteca_kindle.inventory import MountStatus, run_inventory
from biblioteca_kindle.manifests import import_manifests
from biblioteca_kindle.reconcile import reconcile_provisional_titles
from biblioteca_kindle.sync import synchronize


CONTENT_ID = "TOKEN12345678901234567890123456"


class SyncTests(unittest.TestCase):
    def make_kindle(self, parent: Path) -> Path:
        root = parent / "Kindle"
        sidecar = root / "documents" / f"Known Book_{CONTENT_ID}.sdr"
        sidecar.mkdir(parents=True)
        (root / "system").mkdir()
        (root / "documents" / f"Known Book_{CONTENT_ID}.kfx").write_bytes(b"book")
        (sidecar / f"{CONTENT_ID}.mf").write_text(
            json.dumps(
                {
                    "content": {"id": CONTENT_ID, "type": "kindle.pdoc"},
                    "resources": [],
                }
            ),
            encoding="utf-8",
        )
        (root / "documents" / "My Clippings.txt").write_text(
            "\ufeffKnown Book (Author)\n"
            "- Your Highlight at location 10-11 | Added on Monday, January 1, 2024\n\n"
            "Text\n==========\n",
            encoding="utf-8",
        )
        return root

    def mount_status(self, root: Path) -> MountStatus:
        return MountStatus(
            source="/dev/test-kindle",
            target=root,
            filesystem="vfat",
            options=frozenset({"ro"}),
        )

    def test_two_full_syncs_do_not_duplicate_logical_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent)
            database = parent / "library.sqlite3"
            first = synchronize(root, database, mount_status=self.mount_status(root))
            second = synchronize(root, database, mount_status=self.mount_status(root))

            self.assertEqual(first.manifests.created, 1)
            self.assertEqual(second.manifests.updated, 1)
            self.assertEqual(first.clippings.created, 1)
            self.assertEqual(second.clippings.existing, 1)
            self.assertEqual(second.summary.works, 1)
            self.assertEqual(second.summary.deliveries_present, 1)
            self.assertEqual(second.summary.deliveries_absent, 0)
            self.assertEqual(second.summary.annotations, 1)
            self.assertEqual(second.summary.highlights, 1)
            self.assertEqual(second.summary.notes, 0)
            connection = connect_database(database)
            try:
                counts = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "device_snapshots",
                        "works",
                        "editions",
                        "kindle_deliveries",
                        "annotations",
                        "annotation_occurrences",
                    )
                }
            finally:
                connection.close()
            self.assertEqual(
                counts,
                {
                    "device_snapshots": 2,
                    "works": 1,
                    "editions": 1,
                    "kindle_deliveries": 1,
                    "annotations": 1,
                    "annotation_occurrences": 1,
                },
            )

    def test_reconciliation_moves_provisional_clippings_to_unique_edition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent)
            database = parent / "library.sqlite3"
            snapshot = run_inventory(root, database, mount_status=self.mount_status(root))
            import_clippings(root, database, snapshot_id=snapshot.snapshot_id)
            import_manifests(root, database, snapshot_id=snapshot.snapshot_id)

            connection = connect_database(database)
            try:
                with connection:
                    result = reconcile_provisional_titles(connection)
                works = connection.execute("SELECT COUNT(*) FROM works").fetchone()[0]
                editions = connection.execute("SELECT COUNT(*) FROM editions").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(result.resolved_aliases, 1)
            self.assertEqual(result.moved_annotations, 1)
            self.assertEqual((works, editions), (1, 1))

    def test_completed_sync_marks_missing_delivery_absent_without_deleting_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent)
            database = parent / "library.sqlite3"
            synchronize(root, database, mount_status=self.mount_status(root))
            book = root / "documents" / f"Known Book_{CONTENT_ID}.kfx"
            manifest = root / "documents" / f"Known Book_{CONTENT_ID}.sdr" / f"{CONTENT_ID}.mf"
            book.unlink()
            manifest.unlink()

            result = synchronize(root, database, mount_status=self.mount_status(root))

            self.assertEqual(result.marked_absent, 1)
            connection = connect_database(database)
            try:
                presence = connection.execute(
                    "SELECT presence FROM kindle_deliveries"
                ).fetchone()[0]
                annotations = connection.execute(
                    "SELECT COUNT(*) FROM annotations"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(presence, "absent")
            self.assertEqual(annotations, 1)
            self.assertEqual(result.summary.works, 1)
            self.assertEqual(result.summary.deliveries_present, 0)
            self.assertEqual(result.summary.deliveries_absent, 1)
            self.assertEqual(result.summary.annotations, 1)


if __name__ == "__main__":
    unittest.main()
