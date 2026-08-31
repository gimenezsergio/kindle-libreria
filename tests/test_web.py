from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.web import create_app, run_server


class WebTests(unittest.TestCase):
    def test_home_page_and_database_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO works(id, preferred_title) VALUES ('work', 'Una obra')"
                    )
            finally:
                connection.close()

            client = create_app(database).test_client()
            page = client.get("/")
            status = client.get("/api/status")

            self.assertEqual(page.status_code, 200)
            self.assertIn("Biblioteca personal", page.get_data(as_text=True))
            self.assertEqual(
                status.get_json(), {"database_available": True, "works": 1}
            )

    def test_missing_database_is_reported_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "missing.sqlite3"
            response = create_app(database).test_client().get("/api/status")
            self.assertEqual(
                response.get_json(), {"database_available": False, "works": 0}
            )
            self.assertFalse(database.exists())

    def test_server_rejects_external_network_binding(self) -> None:
        with self.assertRaisesRegex(ValueError, "127.0.0.1"):
            run_server("unused.sqlite3", host="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
