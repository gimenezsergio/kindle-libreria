from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database
from biblioteca_kindle.inventory import MountStatus, run_inventory
from biblioteca_kindle.manifests import ManifestImportError, import_manifests


class ManifestImportTests(unittest.TestCase):
    def make_kindle(self, parent: Path, *, include_book: bool = True) -> Path:
        root = parent / "Kindle"
        sidecar = root / "documents" / "Example_TOKEN12345678901234567890123456.sdr"
        sidecar.mkdir(parents=True)
        (root / "system").mkdir()
        if include_book:
            (root / "documents" / "Example_TOKEN12345678901234567890123456.kfx").write_bytes(
                b"book"
            )
        (sidecar / "TOKEN12345678901234567890123456.mf").write_text(
            json.dumps(
                {
                    "content": {
                        "id": "TOKEN12345678901234567890123456",
                        "type": "kindle.pdoc",
                    },
                    "resources": [],
                }
            ),
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

    def test_import_creates_provisional_catalog_and_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent)
            database = parent / "library.sqlite3"
            snapshot = run_inventory(
                root, database, mount_status=self.mount_status(root)
            )

            result = import_manifests(root, database, snapshot_id=snapshot.snapshot_id)

            self.assertEqual((result.imported, result.created, result.updated), (1, 1, 0))
            connection = connect_database(database)
            try:
                delivery = connection.execute(
                    """
                    SELECT kindle_content_id, content_type, document_format,
                           relative_path, sidecar_relative_path, presence
                    FROM kindle_deliveries
                    """
                ).fetchone()
                work = connection.execute(
                    "SELECT preferred_title, merge_status FROM works"
                ).fetchone()
                parse_status = connection.execute(
                    "SELECT parse_status FROM source_observations "
                    "WHERE source_relative_path LIKE '%.mf'"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(delivery[0], "TOKEN12345678901234567890123456")
            self.assertEqual(delivery[1], "kindle.pdoc")
            self.assertEqual(delivery[2], "KFX")
            self.assertEqual(delivery[5], "present")
            self.assertEqual(tuple(work), ("Example", "provisional"))
            self.assertEqual(parse_status, "parsed")

    def test_reimport_updates_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent)
            database = parent / "library.sqlite3"
            first_snapshot = run_inventory(
                root, database, mount_status=self.mount_status(root)
            )
            import_manifests(root, database, snapshot_id=first_snapshot.snapshot_id)
            second_snapshot = run_inventory(
                root, database, mount_status=self.mount_status(root)
            )

            result = import_manifests(root, database, snapshot_id=second_snapshot.snapshot_id)

            self.assertEqual((result.created, result.updated), (0, 1))
            connection = connect_database(database)
            try:
                counts = [
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("works", "editions", "kindle_deliveries")
                ]
            finally:
                connection.close()
            self.assertEqual(counts, [1, 1, 1])

    def test_missing_matching_book_fails_without_catalog_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent, include_book=False)
            database = parent / "library.sqlite3"
            snapshot = run_inventory(
                root, database, mount_status=self.mount_status(root)
            )
            with self.assertRaisesRegex(ManifestImportError, "se encontraron 0"):
                import_manifests(root, database, snapshot_id=snapshot.snapshot_id)

            connection = connect_database(database)
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM kindle_deliveries"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()

