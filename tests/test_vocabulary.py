from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database
from biblioteca_kindle.inventory import MountStatus, run_inventory
from biblioteca_kindle.manifests import import_manifests
from biblioteca_kindle.vocabulary import VocabularyImportError, import_vocabulary


CONTENT_ID = "TOKEN12345678901234567890123456"


class VocabularyImportTests(unittest.TestCase):
    def make_kindle(self, parent: Path) -> Path:
        root = parent / "Kindle"
        sidecar = root / "documents" / f"Filename title_{CONTENT_ID}.sdr"
        sidecar.mkdir(parents=True)
        (root / "system" / "vocabulary").mkdir(parents=True)
        (root / "documents" / f"Filename title_{CONTENT_ID}.kfx").write_bytes(b"book")
        (sidecar / f"{CONTENT_ID}.mf").write_text(
            json.dumps(
                {
                    "content": {"id": CONTENT_ID, "type": "kindle.pdoc"},
                    "resources": [],
                }
            ),
            encoding="utf-8",
        )
        vocab = sqlite3.connect(root / "system" / "vocabulary" / "vocab.db")
        try:
            vocab.execute(
                """
                CREATE TABLE BOOK_INFO(
                    id TEXT, asin TEXT, guid TEXT, lang TEXT,
                    title TEXT, authors TEXT
                )
                """
            )
            vocab.executemany(
                "INSERT INTO BOOK_INFO VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("book-key", CONTENT_ID, "guid-1", "es", "Canonical title", "Author Name"),
                    ("other-key", "UNMATCHED", "guid-2", "en", "Other title", "Other Author"),
                ],
            )
            vocab.commit()
        finally:
            vocab.close()
        return root

    def mount_status(self, root: Path) -> MountStatus:
        return MountStatus(
            source="/dev/test-kindle",
            target=root,
            filesystem="vfat",
            options=frozenset({"ro"}),
        )

    def prepare(self, parent: Path) -> tuple[Path, Path, str]:
        root = self.make_kindle(parent)
        database = parent / "library.sqlite3"
        snapshot = run_inventory(root, database, mount_status=self.mount_status(root))
        import_manifests(root, database, snapshot_id=snapshot.snapshot_id)
        return root, database, snapshot.snapshot_id

    def test_import_enriches_only_matching_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            result = import_vocabulary(root, database, snapshot_id=snapshot_id)

            self.assertEqual((result.rows, result.matched, result.unmatched), (2, 1, 1))
            connection = connect_database(database)
            try:
                edition = connection.execute(
                    "SELECT title, language FROM editions"
                ).fetchone()
                work = connection.execute(
                    "SELECT preferred_title, merge_status FROM works"
                ).fetchone()
                contributor = connection.execute(
                    "SELECT display_name, normalized_name FROM contributors"
                ).fetchone()
                namespaces = {
                    row[0]
                    for row in connection.execute(
                        "SELECT namespace FROM external_identifiers"
                    )
                }
            finally:
                connection.close()
            self.assertEqual(tuple(edition), ("Canonical title", "es"))
            self.assertEqual(tuple(work), ("Canonical title", "provisional"))
            self.assertEqual(tuple(contributor), ("Author Name", "author name"))
            self.assertIn("kindle_vocab_id", namespaces)
            self.assertIn("kindle_vocab_guid", namespaces)
            self.assertNotIn("asin", namespaces)

    def test_reimport_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            import_vocabulary(root, database, snapshot_id=snapshot_id)
            import_vocabulary(root, database, snapshot_id=snapshot_id)
            connection = connect_database(database)
            try:
                counts = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("contributors", "edition_contributors", "title_aliases")
                }
            finally:
                connection.close()
            self.assertEqual(counts, {"contributors": 1, "edition_contributors": 1, "title_aliases": 1})

    def test_changed_source_after_snapshot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            source = root / "system" / "vocabulary" / "vocab.db"
            with source.open("ab") as output:
                output.write(b"changed")
            with self.assertRaisesRegex(VocabularyImportError, "cambió"):
                import_vocabulary(root, database, snapshot_id=snapshot_id)


if __name__ == "__main__":
    unittest.main()

