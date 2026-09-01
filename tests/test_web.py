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
            library = client.get("/library")
            status = client.get("/api/status")
            summary = client.get("/api/summary")
            works = client.get("/api/works?q=Una&annotated=false")

            self.assertEqual(page.status_code, 200)
            self.assertIn("Biblioteca personal", page.get_data(as_text=True))
            self.assertEqual(library.status_code, 200)
            self.assertIn("Buscar por título o autor", library.get_data(as_text=True))
            self.assertEqual(
                status.get_json(), {"database_available": True, "works": 1}
            )
            self.assertEqual(summary.status_code, 200)
            self.assertEqual(summary.get_json()["catalog"]["works"], 1)
            self.assertEqual(summary.get_json()["annotations"]["total"], 0)
            self.assertIsNone(summary.get_json()["last_sync"])
            self.assertEqual(works.status_code, 200)
            self.assertEqual(works.get_json()["total"], 1)
            self.assertEqual(works.get_json()["items"][0]["title"], "Una obra")

    def test_works_api_validates_filters_and_paginates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.executemany(
                        "INSERT INTO works(id, preferred_title) VALUES (?, ?)",
                        [("a", "Alfa"), ("b", "Beta")],
                    )
            finally:
                connection.close()
            client = create_app(database).test_client()
            first = client.get("/api/works?page_size=1&page=1")
            second = client.get("/api/works?page_size=1&page=2")
            invalid = client.get("/api/works?presence=unknown")
            self.assertEqual(first.get_json()["items"][0]["title"], "Alfa")
            self.assertEqual(first.get_json()["pages"], 2)
            self.assertEqual(second.get_json()["items"][0]["title"], "Beta")
            self.assertEqual(invalid.status_code, 400)

    def test_work_detail_and_annotation_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute("INSERT INTO works(id, preferred_title) VALUES ('work', 'Libro')")
                    connection.execute("INSERT INTO editions(id, work_id, title, language) VALUES ('edition', 'work', 'Libro', 'es')")
                    connection.execute(
                        """
                        INSERT INTO annotations(id, edition_id, kind, text, start_position_native)
                        VALUES ('annotation', 'edition', 'highlight', 'Texto privado', '42')
                        """
                    )
            finally:
                connection.close()
            client = create_app(database).test_client()
            page = client.get("/library/work")
            detail = client.get("/api/works/work")
            annotations = client.get("/api/works/work/annotations?kind=highlight")
            missing = client.get("/api/works/missing")
            invalid = client.get("/api/works/work/annotations?source=invalid")
            self.assertEqual(page.status_code, 200)
            self.assertIn("Subrayados y notas", page.get_data(as_text=True))
            self.assertEqual(detail.get_json()["title"], "Libro")
            self.assertEqual(detail.get_json()["annotations"]["highlight"], 1)
            self.assertEqual(annotations.get_json()["items"][0]["text"], "Texto privado")
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(invalid.status_code, 400)

    def test_personal_web_actions_write_only_to_local_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.executemany(
                        "INSERT INTO works(id, preferred_title) VALUES (?, ?)",
                        [("source", "Origen"), ("target", "Destino")],
                    )
            finally:
                connection.close()
            client = create_app(database).test_client()
            collection = client.post("/api/collections", json={"name": "Ideas"})
            collection_id = collection.get_json()["id"]
            assignment = client.post(
                "/api/works/source/collections",
                json={"collection_id": collection_id, "note": "Eje central"},
            )
            note = client.post("/api/works/source/notes", json={"body": "Mi lectura"})
            relation = client.post(
                "/api/works/source/relations",
                json={"target_work_id": "target", "relation_type": "tema", "symmetric": True},
            )
            personal = client.get("/api/works/source/personal").get_json()
            self.assertEqual(collection.status_code, 201)
            self.assertEqual(assignment.status_code, 201)
            self.assertEqual(note.status_code, 201)
            self.assertEqual(relation.status_code, 201)
            self.assertEqual(personal["collections"][0]["name"], "Ideas")
            self.assertEqual(personal["notes"][0]["body"], "Mi lectura")
            self.assertEqual(personal["relations"][0]["other_title"], "Destino")

    def test_personal_web_actions_require_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            response = create_app(database).test_client().post(
                "/api/collections", data="name=Ideas",
                content_type="application/x-www-form-urlencoded",
            )
            self.assertEqual(response.status_code, 400)

    def test_missing_database_is_reported_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "missing.sqlite3"
            response = create_app(database).test_client().get("/api/status")
            summary = create_app(database).test_client().get("/api/summary")
            self.assertEqual(
                response.get_json(), {"database_available": False, "works": 0}
            )
            self.assertFalse(database.exists())
            self.assertEqual(summary.status_code, 404)
            self.assertEqual(summary.get_json(), {"database_available": False})

    def test_server_rejects_external_network_binding(self) -> None:
        with self.assertRaisesRegex(ValueError, "127.0.0.1"):
            run_server("unused.sqlite3", host="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
