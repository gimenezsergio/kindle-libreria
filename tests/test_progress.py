from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database
from biblioteca_kindle.inventory import MountStatus, run_inventory
from biblioteca_kindle.manifests import import_manifests
from biblioteca_kindle.progress import import_progress


CONTENT_ID = "TOKEN12345678901234567890123456"
SIGNATURE = b"\x00\x00\x00\x00\x00\x1a\xb1\x26"


def krds_int(value: int) -> bytes:
    return b"\x01" + struct.pack(">i", value)


def krds_long(value: int) -> bytes:
    return b"\x02" + struct.pack(">q", value)


def krds_double(value: float) -> bytes:
    return b"\x04" + struct.pack(">d", value)


def krds_utf(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return b"\x03\x00" + struct.pack(">H", len(encoded)) + encoded


def krds_object(name: str, *values: bytes) -> bytes:
    name_bytes = name.encode("utf-8")
    return (
        b"\xfe\x00"
        + struct.pack(">H", len(name_bytes))
        + name_bytes
        + b"".join(values)
        + b"\xff"
    )


def progress_fixture() -> bytes:
    average = krds_object(
        "timer.average.calculator",
        krds_int(0),
        krds_int(0),
        krds_int(0),
        krds_int(0),
    )
    objects = [
        krds_object("lpr", krds_int(2), krds_utf("position:10"), krds_long(1_700_000_000_000)),
        krds_object(
            "fpr",
            krds_utf("position:15"),
            krds_long(1_700_000_001_000),
            krds_int(-180),
            krds_utf("AR"),
            krds_utf("device"),
        ),
        krds_object(
            "timer.model",
            krds_long(1),
            krds_long(60_000),
            krds_long(250),
            krds_double(3.0),
            average,
        ),
        krds_object(
            "page.history.store",
            krds_int(1),
            krds_object(
                "page.history.record",
                krds_utf("position:9"),
                krds_long(1_700_000_000_000),
            ),
        ),
    ]
    return SIGNATURE + krds_int(1) + krds_int(len(objects)) + b"".join(objects)


class ProgressImportTests(unittest.TestCase):
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
        (sidecar / f"Book_{CONTENT_ID}.yjf").write_bytes(progress_fixture())
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

    def test_import_preserves_native_positions_and_ignores_timer_percent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            result = import_progress(root, database, snapshot_id=snapshot_id)
            self.assertEqual(
                (
                    result.files,
                    result.imported,
                    result.unmatched,
                    result.with_furthest_position,
                    result.with_timer,
                    result.history_records,
                ),
                (1, 1, 0, 1, 1, 1),
            )
            connection = connect_database(database)
            try:
                state = connection.execute(
                    """
                    SELECT last_position_native, last_position_type,
                           furthest_position_native, progress_fraction,
                           reading_time_ms, words_read
                    FROM reading_states
                    """
                ).fetchone()
                history = connection.execute(
                    "SELECT position_native FROM reading_history_records"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(state[0], "position:10")
            self.assertEqual(state[1], "kfx")
            self.assertEqual(state[2], "position:15")
            self.assertIsNone(state[3])
            self.assertEqual((state[4], state[5]), (60_000, 250))
            self.assertEqual(history, "position:9")

    def test_reimport_same_snapshot_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, database, snapshot_id = self.prepare(Path(directory))
            import_progress(root, database, snapshot_id=snapshot_id)
            import_progress(root, database, snapshot_id=snapshot_id)
            connection = connect_database(database)
            try:
                states = connection.execute("SELECT COUNT(*) FROM reading_states").fetchone()[0]
                history = connection.execute(
                    "SELECT COUNT(*) FROM reading_history_records"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual((states, history), (1, 1))


if __name__ == "__main__":
    unittest.main()

