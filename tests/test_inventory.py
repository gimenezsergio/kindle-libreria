from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biblioteca_kindle.db import connect_database
from biblioteca_kindle.inventory import (
    InventoryError,
    MountStatus,
    inspect_mount,
    run_inventory,
)


class InventoryTests(unittest.TestCase):
    def make_kindle(self, parent: Path) -> Path:
        root = parent / "Kindle"
        (root / "documents" / "Book.sdr").mkdir(parents=True)
        (root / "system" / "vocabulary").mkdir(parents=True)
        (root / "documents" / "Book.kfx").write_bytes(b"book")
        (root / "documents" / "Book.sdr" / "Book.yjf").write_bytes(b"sidecar")
        (root / "documents" / "Book.sdr" / "manifest.mf").write_text(
            '{}', encoding="utf-8"
        )
        (root / "documents" / "My Clippings.txt").write_text(
            "Clipping", encoding="utf-8"
        )
        (root / "system" / "vocabulary" / "vocab.db").write_bytes(b"database")
        (root / "ignored.txt").write_text("ignored", encoding="utf-8")
        return root

    def mount_status(self, root: Path, *, read_only: bool = True) -> MountStatus:
        return MountStatus(
            source="/dev/test-kindle",
            target=root,
            filesystem="vfat",
            options=frozenset({"ro" if read_only else "rw"}),
        )

    def tree_contents(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_inventory_records_relevant_files_and_completes_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent)
            database = parent / "library.sqlite3"
            before = self.tree_contents(root)

            result = run_inventory(
                root, database, mount_status=self.mount_status(root)
            )

            self.assertEqual(result.file_count, 5)
            self.assertEqual(result.warning_count, 0)
            connection = connect_database(database)
            try:
                snapshot = connection.execute(
                    "SELECT status, mount_read_only FROM device_snapshots"
                ).fetchone()
                paths = {
                    row[0]
                    for row in connection.execute(
                        "SELECT source_relative_path FROM source_observations"
                    )
                }
            finally:
                connection.close()
            self.assertEqual(tuple(snapshot), ("completed", 1))
            self.assertIn("documents/Book.kfx", paths)
            self.assertIn("documents/Book.sdr/Book.yjf", paths)
            self.assertNotIn("ignored.txt", paths)
            self.assertEqual(self.tree_contents(root), before)

    def test_database_inside_kindle_is_rejected_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_kindle(Path(directory))
            database = root / "work" / "library.sqlite3"
            with self.assertRaisesRegex(InventoryError, "dentro del Kindle"):
                run_inventory(root, database, mount_status=self.mount_status(root))
            self.assertFalse(database.exists())

    def test_writable_mount_is_recorded_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent)
            database = parent / "library.sqlite3"
            result = run_inventory(
                root,
                database,
                mount_status=self.mount_status(root, read_only=False),
            )
            self.assertEqual(result.warning_count, 1)

    def test_failure_marks_snapshot_failed_without_partial_observations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = self.make_kindle(parent)
            database = parent / "library.sqlite3"

            with patch(
                "biblioteca_kindle.inventory.hash_file",
                side_effect=OSError("simulated read failure"),
            ):
                with self.assertRaisesRegex(OSError, "simulated read failure"):
                    run_inventory(
                        root, database, mount_status=self.mount_status(root)
                    )

            connection = connect_database(database)
            try:
                status = connection.execute(
                    "SELECT status FROM device_snapshots"
                ).fetchone()[0]
                observation_count = connection.execute(
                    "SELECT COUNT(*) FROM source_observations"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(status, "failed")
            self.assertEqual(observation_count, 0)

    def test_inspect_mount_uses_most_specific_mount(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            mount = parent / "Kindle"
            mount.mkdir()
            mountinfo = parent / "mountinfo"
            mountinfo.write_text(
                "1 0 8:1 / / rw - ext4 /dev/root rw\n"
                f"2 1 8:16 / {mount} ro,nosuid - vfat /dev/sdb ro\n",
                encoding="utf-8",
            )
            status = inspect_mount(mount, mountinfo)
            self.assertEqual(status.source, "/dev/sdb")
            self.assertEqual(status.target, mount)
            self.assertTrue(status.read_only)


if __name__ == "__main__":
    unittest.main()
