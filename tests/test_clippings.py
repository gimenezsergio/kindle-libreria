from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.clippings import import_clippings, parse_clippings
from biblioteca_kindle.db import connect_database
from biblioteca_kindle.inventory import MountStatus, run_inventory
from biblioteca_kindle.manifests import import_manifests


CONTENT_ID = "TOKEN12345678901234567890123456"


class ClippingsImportTests(unittest.TestCase):
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
            "- Your Highlight on page 10 | Added on Monday, January 1, 2024\n\n"
            "Highlighted text\n"
            "==========\n"
            "Known Book (Author)\n"
            "- Your Note at location 20 | Added on Monday, January 1, 2024\n\n"
            "Personal note\n"
            "==========\n"
            "Historical Book (Someone)\n"
            "- Your Bookmark at location 30 | Added on Monday, January 1, 2024\n"
            "==========\n",
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

    def prepare(self, parent: Path) -> tuple[Path, Path, str]:
        root = self.make_kindle(parent)
        database = parent / "library.sqlite3"
        snapshot = run_inventory(root, database, mount_status=self.mount_status(root))
        import_manifests(root, database, snapshot_id=snapshot.snapshot_id)
        return root, database, snapshot.snapshot_id

    def test_parser_preserves_three_entry_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_kindle(Path(directory))
            records = parse_clippings(
                (root / "documents" / "My Clippings.txt").read_bytes()
            )
            self.assertEqual([record.kind for record in records], ["highlight", "note", "bookmark"])
            self.assertEqual(records[0].content, "Highlighted text")
            self.assertEqual(records[2].content, None)
            self.assertEqual(len({record.source_key for record in records}), 3)

    def test_import_matches_known_and_creates_provisional_historical_book(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            result = import_clippings(root, database, snapshot_id=snapshot_id)
            self.assertEqual((result.entries, result.created), (3, 3))
            self.assertEqual((result.matched_headings, result.provisional_headings), (1, 1))

            connection = connect_database(database)
            try:
                kinds = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM annotations GROUP BY kind"
                    )
                }
                occurrences = connection.execute(
                    "SELECT COUNT(*) FROM annotation_occurrences"
                ).fetchone()[0]
                works = connection.execute("SELECT COUNT(*) FROM works").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(kinds, {"highlight": 1, "note": 1, "bookmark": 1})
            self.assertEqual(occurrences, 3)
            self.assertEqual(works, 2)

    def test_reimport_does_not_duplicate_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            first = import_clippings(root, database, snapshot_id=snapshot_id)
            second = import_clippings(root, database, snapshot_id=snapshot_id)
            self.assertEqual((first.created, first.existing), (3, 0))
            self.assertEqual((second.created, second.existing), (0, 3))
            connection = connect_database(database)
            try:
                annotations = connection.execute(
                    "SELECT COUNT(*) FROM annotations"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(annotations, 3)


if __name__ == "__main__":
    unittest.main()

