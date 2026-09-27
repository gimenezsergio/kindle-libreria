from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.manual_works import (
    ManualWorkError,
    create_manual_work,
    delete_work,
    search_external_books,
)
from biblioteca_kindle.web import create_app


class ManualWorksTests(unittest.TestCase):
    def test_create_manual_work_creates_db_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)

            result = create_manual_work(
                database,
                title="El Aleph",
                author="Jorge Luis Borges",
                display_title="El Aleph (Borges)",
            )

            self.assertTrue(result["id"])
            self.assertEqual(result["title"], "El Aleph (Borges)")
            self.assertEqual(result["author"], "Jorge Luis Borges")

            connection = connect_database(database)
            try:
                work = connection.execute(
                    "SELECT preferred_title, display_title, merge_status FROM works WHERE id = ?",
                    (result["id"],),
                ).fetchone()
                self.assertIsNotNone(work)
                self.assertEqual(work["preferred_title"], "El Aleph")
                self.assertEqual(work["display_title"], "El Aleph (Borges)")
                self.assertEqual(work["merge_status"], "normal")


                edition = connection.execute(
                    "SELECT format_hint FROM editions WHERE work_id = ?",
                    (result["id"],),
                ).fetchone()
                self.assertEqual(edition["format_hint"], "MANUAL")

                contributor = connection.execute(
                    "SELECT display_name FROM contributors WHERE display_name = ?",
                    ("Jorge Luis Borges",),
                ).fetchone()
                self.assertIsNotNone(contributor)
            finally:
                connection.close()

    def test_delete_work_removes_work_and_editions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)

            result = create_manual_work(
                database,
                title="Libro Para Borrar",
                author="Autor Prueba",
            )
            work_id = result["id"]

            delete_work(database, work_id)

            connection = connect_database(database)
            try:
                work = connection.execute("SELECT 1 FROM works WHERE id = ?", (work_id,)).fetchone()
                self.assertIsNone(work)
                editions = connection.execute("SELECT 1 FROM editions WHERE work_id = ?", (work_id,)).fetchall()
                self.assertEqual(len(editions), 0)
            finally:
                connection.close()

    def test_create_manual_work_validates_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)

            with self.assertRaises(ManualWorkError):
                create_manual_work(database, title="   ")

    def test_search_external_books_mocked(self) -> None:
        mock_response_data = {
            "docs": [
                {
                    "key": "/works/OL123W",
                    "title": "Don Quijote",
                    "author_name": ["Miguel de Cervantes"],
                    "first_publish_year": 1605,
                    "cover_i": 12345,
                    "isbn": ["9788424115456"],
                }
            ]
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_cm = MagicMock()
            mock_cm.__enter__.return_value.read.return_value = (
                __import__("json").dumps(mock_response_data).encode("utf-8")
            )
            mock_urlopen.return_value = mock_cm

            results = search_external_books("Quijote")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["title"], "Don Quijote")
            self.assertEqual(results[0]["authors"], ["Miguel de Cervantes"])
            self.assertEqual(results[0]["cover_i"], 12345)
            self.assertIn("12345-M.jpg", results[0]["cover_url"])

    def test_api_create_work_and_search_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)

            client = create_app(database).test_client()

            # Test POST /api/works
            res = client.post(
                "/api/works",
                json={
                    "title": "Ficciones",
                    "author": "Jorge Luis Borges",
                },
            )
            self.assertEqual(res.status_code, 201)
            data = res.get_json()
            work_id = data["id"]
            self.assertEqual(data["title"], "Ficciones")
            self.assertEqual(data["author"], "Jorge Luis Borges")

            # Verify it shows in GET /api/works
            catalog_res = client.get("/api/works?q=Ficciones")
            self.assertEqual(catalog_res.status_code, 200)
            self.assertEqual(catalog_res.get_json()["total"], 1)

            # Test DELETE /api/works/<work_id>
            del_res = client.delete(f"/api/works/{work_id}")
            self.assertEqual(del_res.status_code, 200)

            # Verify it is no longer in GET /api/works
            catalog_after = client.get("/api/works?q=Ficciones")
            self.assertEqual(catalog_after.get_json()["total"], 0)

            # Test POST /api/works validation error
            bad_res = client.post("/api/works", json={"title": ""})
            self.assertEqual(bad_res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
