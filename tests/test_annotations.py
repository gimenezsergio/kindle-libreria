from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.annotations import import_annotations
from biblioteca_kindle.db import connect_database
from biblioteca_kindle.inventory import MountStatus, run_inventory
from biblioteca_kindle.krds import read_krds
from biblioteca_kindle.manifests import import_manifests


CONTENT_ID = "TOKEN12345678901234567890123456"
SIGNATURE = b"\x00\x00\x00\x00\x00\x1a\xb1\x26"


def integer(value: int) -> bytes:
    return b"\x01" + struct.pack(">i", value)


def long_integer(value: int) -> bytes:
    return b"\x02" + struct.pack(">q", value)


def text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return b"\x03\x00" + struct.pack(">H", len(encoded)) + encoded


def obj(name: str, *values: bytes) -> bytes:
    encoded = name.encode("utf-8")
    return b"\xfe\x00" + struct.pack(">H", len(encoded)) + encoded + b"".join(values) + b"\xff"


def krds_with_highlight() -> bytes:
    highlight = obj(
        "annotation.personal.highlight",
        text("position:10"),
        text("position:20"),
        long_integer(1_700_000_000_000),
        long_integer(1_700_000_001_000),
        text("template"),
    )
    tree = obj("saved.avl.interval.tree", integer(1), highlight)
    cache = obj("annotation.cache.object", integer(1), integer(1), tree)
    return SIGNATURE + integer(1) + integer(1) + cache


def krds_empty_cache() -> bytes:
    cache = obj("annotation.cache.object")
    return SIGNATURE + integer(1) + integer(1) + cache


class AnnotationImportTests(unittest.TestCase):
    def make_kindle(self, parent: Path) -> Path:
        root = parent / "Kindle"
        sidecar = root / "documents" / f"Book_{CONTENT_ID}.sdr"
        sidecar.mkdir(parents=True)
        (root / "system").mkdir()
        (root / "documents" / f"Book_{CONTENT_ID}.kfx").write_bytes(b"book")
        (sidecar / f"{CONTENT_ID}.mf").write_text(
            json.dumps(
                {
                    "content": {"id": CONTENT_ID, "type": "kindle.pdoc"},
                    "resources": [],
                }
            ),
            encoding="utf-8",
        )
        (sidecar / f"Book_{CONTENT_ID}.yjr").write_bytes(krds_with_highlight())
        (sidecar / f"Book_{CONTENT_ID}.han").write_text(
            json.dumps(
                {
                    "md5": "checksum",
                    "payload": {
                        "key": CONTENT_ID,
                        "records": [
                            {
                                "annotationId": "han-annotation-1",
                                "type": "kindle.note",
                                "startPosition": "ABC",
                                "endPosition": "DEF",
                                "creationTime": "2024-01-01 10:00:00.0",
                                "lastModificationTime": "2024-01-01 10:01:00.0",
                                "text": "A note",
                            },
                            {
                                "annotationId": "position-only",
                                "type": "kindle.lpr",
                                "creationTime": "2024-01-01 10:02:00.0",
                            },
                        ],
                    },
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

    def prepare(self, parent: Path) -> tuple[Path, Path, str]:
        root = self.make_kindle(parent)
        database = parent / "library.sqlite3"
        snapshot = run_inventory(root, database, mount_status=self.mount_status(root))
        import_manifests(root, database, snapshot_id=snapshot.snapshot_id)
        return root, database, snapshot.snapshot_id

    def test_reader_accepts_empty_annotation_cache(self) -> None:
        decoded, warnings = read_krds(krds_empty_cache())
        self.assertEqual(decoded["annotation.cache.object"], {})
        self.assertEqual(warnings, [])

    def test_import_keeps_krds_and_han_as_separate_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            result = import_annotations(root, database, snapshot_id=snapshot_id)
            self.assertEqual(
                (
                    result.krds_annotations,
                    result.han_annotations,
                    result.created,
                    result.existing,
                ),
                (1, 1, 2, 0),
            )
            connection = connect_database(database)
            try:
                sources = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT source_kind, COUNT(*) FROM annotation_occurrences GROUP BY source_kind"
                    )
                }
                kinds = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM annotations GROUP BY kind"
                    )
                }
            finally:
                connection.close()
            self.assertEqual(sources, {"krds": 1, "han": 1})
            self.assertEqual(kinds, {"highlight": 1, "note": 1})

    def test_reimport_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            import_annotations(root, database, snapshot_id=snapshot_id)
            result = import_annotations(root, database, snapshot_id=snapshot_id)
            self.assertEqual((result.created, result.existing), (0, 2))
            connection = connect_database(database)
            try:
                count = connection.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()

