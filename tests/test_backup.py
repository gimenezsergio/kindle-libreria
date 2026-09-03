from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.backup import BackupError, create_database_backup
from biblioteca_kindle.db import connect_database, migrate_database


class BackupTests(unittest.TestCase):
    def test_creates_private_consistent_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "live.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO works(id, preferred_title) VALUES ('work', 'Book')"
                    )
            finally:
                connection.close()
            result = create_database_backup(database, root / "backups" / "library.sqlite3")
            backup = connect_database(result.output)
            try:
                self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(backup.execute("SELECT preferred_title FROM works").fetchone()[0], "Book")
            finally:
                backup.close()
            self.assertEqual(result.integrity, "ok")
            self.assertEqual(stat.S_IMODE(result.output.stat().st_mode), 0o600)
            self.assertEqual(len(result.sha256), 64)

    def test_refuses_missing_source_or_active_database_as_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "live.sqlite3"
            with self.assertRaisesRegex(BackupError, "no existe"):
                create_database_backup(database, Path(directory) / "backup.sqlite3")
            migrate_database(database)
            with self.assertRaisesRegex(BackupError, "base activa"):
                create_database_backup(database, database)


if __name__ == "__main__":
    unittest.main()
