from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.reports import ReportError, library_summary, work_card


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "library.sqlite3"
        migrate_database(self.database)
        connection = connect_database(self.database)
        try:
            with connection:
                connection.execute(
                    "INSERT INTO works(id, preferred_title, merge_status) VALUES ('work', 'Título', 'provisional')"
                )
                connection.execute(
                    "INSERT INTO editions(id, work_id, title, language) VALUES ('edition', 'work', 'Título', 'es')"
                )
                connection.execute(
                    "INSERT INTO personal_notes(id, target_type, target_id, body) VALUES ('note', 'work', 'work', 'Secreto')"
                )
        finally:
            connection.close()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_summary_reports_counts_without_private_content(self) -> None:
        report = library_summary(self.database)
        self.assertIn("Última sincronización: ninguna", report)
        self.assertIn("Obras: 1", report)
        self.assertIn("Obras provisionales: 1", report)
        self.assertIn("Notas propias: 1", report)
        self.assertNotIn("Secreto", report)

    def test_work_card_hides_private_notes_by_default(self) -> None:
        public = work_card(self.database, "work")
        private = work_card(self.database, "work", include_private=True)
        self.assertIn("contenido privado oculto", public)
        self.assertNotIn("Secreto", public)
        self.assertIn("Secreto", private)

    def test_unknown_work_is_rejected(self) -> None:
        with self.assertRaises(ReportError):
            work_card(self.database, "missing")


if __name__ == "__main__":
    unittest.main()
