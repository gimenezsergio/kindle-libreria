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
            self.assertIsNone(works.get_json()["items"][0]["cover"])

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
                    connection.execute(
                        """INSERT INTO device_snapshots(id, device_key, mount_point, mount_read_only, status, started_at)
                           VALUES ('snapshot', 'kindle', '/media/kindle', 1, 'completed', '2026-01-01')"""
                    )
                    connection.execute(
                        """INSERT INTO source_observations(id, snapshot_id, source_type, source_relative_path,
                               file_size, file_hash, observed_at, parse_status)
                           VALUES ('source', 'snapshot', 'clippings', 'documents/My Clippings.txt',
                               1, 'hash', '2026-01-01', 'parsed')"""
                    )
                    connection.execute(
                        """INSERT INTO annotation_occurrences(id, annotation_id, source_observation_id,
                               source_kind, source_record_key, original_position, original_date, observed_at)
                           VALUES ('occurrence', 'annotation', 'source', 'clippings', 'record',
                               '- Your Highlight on page 65',
                               'location 768-770 | Added on Saturday', '2026-01-01')"""
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
            page_text = page.get_data(as_text=True)
            self.assertIn("Subrayados y notas", page_text)
            self.assertIn("Datos del documento", page_text)
            self.assertIn("Seguimiento de lectura", page_text)
            self.assertNotIn("Progreso disponible", page_text)
            self.assertEqual(detail.get_json()["title"], "Libro")
            self.assertEqual(detail.get_json()["annotations"]["highlight"], 1)
            self.assertEqual(annotations.get_json()["items"][0]["text"], "Texto privado")
            self.assertEqual(
                annotations.get_json()["items"][0]["reference"],
                {"page": 65, "location_start": 768, "location_end": 770,
                 "label": "Página 65 · Ubicación 768–770"},
            )
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

    def test_ai_profiles_can_be_created_edited_and_selected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            client = create_app(database).test_client()
            page = client.get("/settings/ai-profiles")
            initial = client.get("/api/ai-profiles").get_json()["items"]
            created = client.post(
                "/api/ai-profiles",
                json={"name": "Jenna", "description": "Perspectiva personal", "prompt": "Un prompt completo", "is_default": True},
            )
            profile_id = created.get_json()["id"]
            profiles = client.get("/api/ai-profiles").get_json()["items"]
            archived = client.patch(f"/api/ai-profiles/{profile_id}", json={"is_archived": True, "is_default": False})
            remaining = client.get("/api/ai-profiles").get_json()["items"]
            self.assertEqual(page.status_code, 200)
            self.assertIn("Perfiles de conversación", page.get_data(as_text=True))
            self.assertEqual(initial[0]["name"], "Compañero de lectura")
            self.assertEqual(created.status_code, 201)
            self.assertEqual(profiles[0]["name"], "Jenna")
            self.assertEqual(profiles[0]["prompt"], "Un prompt completo")
            self.assertEqual(archived.status_code, 200)
            self.assertEqual([item["name"] for item in remaining], ["Compañero de lectura"])

    def test_reading_conversation_can_be_created_and_messages_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            with connection:
                connection.execute(
                    "INSERT INTO works(id, preferred_title) VALUES ('work', 'Libro')"
                )
            connection.close()
            client = create_app(database).test_client()

            page = client.get("/library/work")
            created = client.post(
                "/api/works/work/conversations",
                json={"profile_id": "companion"},
            )
            conversation_id = created.get_json()["id"]
            message = client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"content": "¿Qué tensión organiza el libro?"},
            )
            conversations = client.get(
                "/api/works/work/conversations"
            ).get_json()["items"]
            detail = client.get(
                f"/api/conversations/{conversation_id}"
            ).get_json()

            self.assertIn("Acompañante de lectura", page.get_data(as_text=True))
            self.assertEqual(created.status_code, 201)
            self.assertEqual(message.status_code, 201)
            self.assertEqual(conversations[0]["message_count"], 1)
            self.assertEqual(detail["profile_name_snapshot"], "Compañero de lectura")
            self.assertEqual(detail["messages"][0]["role"], "user")
            self.assertEqual(detail["messages"][0]["content"], "¿Qué tensión organiza el libro?")

    def test_configured_ai_provider_saves_its_answer(self) -> None:
        class FakeProvider:
            name = "test"
            ready = True

            def respond(self, packet):
                self.packet = packet
                return "Podríamos explorar esa hipótesis."

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            with connection:
                connection.execute("INSERT INTO works(id, preferred_title) VALUES ('work', 'Libro')")
                connection.execute("INSERT INTO personal_notes(id, target_type, target_id, body) VALUES ('note', 'work', 'work', 'Mi nota sobre el poder')")
            connection.close()
            provider = FakeProvider()
            client = create_app(database, ai_provider=provider).test_client()
            conversation_id = client.post("/api/works/work/conversations", json={"profile_id": "companion"}).get_json()["id"]
            response = client.post(f"/api/conversations/{conversation_id}/respond", json={"content": "¿Qué relación ves?", "personal_note_ids": ["note"], "annotation_ids": []})
            detail = client.get(f"/api/conversations/{conversation_id}").get_json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["mode"], "test")
            self.assertEqual([item["role"] for item in detail["messages"]], ["user", "assistant"])
            self.assertIn("MATERIAL SELECCIONADO", provider.packet.input[0]["content"])
            self.assertIn("Mi nota sobre el poder", provider.packet.input[0]["content"])

    def test_chat_can_preview_and_use_library_search(self) -> None:
        class FakeProvider:
            name = "test"
            ready = True

            def respond(self, packet):
                self.packet = packet
                return "Veo una conexión respaldada por [B1]."

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            with connection:
                connection.execute("INSERT INTO works(id,preferred_title) VALUES ('source','Origen')")
                connection.execute("INSERT INTO works(id,preferred_title) VALUES ('other','Otra_obra')")
                connection.execute("INSERT INTO editions(id,work_id,title) VALUES ('edition','other','Otra obra')")
                connection.execute("INSERT INTO annotations(id,edition_id,kind,text) VALUES ('annotation','edition','highlight','El poder modifica el lenguaje común')")
            connection.close()
            provider = FakeProvider()
            client = create_app(database, ai_provider=provider).test_client()
            conversation_id = client.post(
                "/api/works/source/conversations", json={"profile_id": "companion"}
            ).get_json()["id"]
            preview = client.post(
                f"/api/conversations/{conversation_id}/library-search",
                json={"search_query": "poder y lenguaje", "search_scope": "library"},
            )
            key = preview.get_json()["items"][0]["key"]
            response = client.post(
                f"/api/conversations/{conversation_id}/respond",
                json={"content": "Compará el poder y el lenguaje", "search_library": True,
                      "search_scope": "library", "library_source_keys": [key]},
            )
            detail = client.get(f"/api/conversations/{conversation_id}").get_json()
            self.assertEqual(response.status_code, 200)
            self.assertIn("[B1]", provider.packet.input[0]["content"])
            self.assertEqual(detail["messages"][-1]["library_sources"][0]["source_id"], "annotation")
            self.assertIn("Buscar conexiones en mi biblioteca", client.get("/library/source").get_data(as_text=True))

    def test_automatic_and_manual_display_titles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO works(id, preferred_title) VALUES ('work', 'Jugarse_la_piel')"
                    )
            finally:
                connection.close()
            client = create_app(database).test_client()
            automatic = client.get("/api/works/work").get_json()
            edited = client.patch(
                "/api/works/work/display-title", json={"title": "Jugarse la piel — Nassim Taleb"}
            )
            listed = client.get("/api/works?q=Nassim").get_json()
            restored = client.patch("/api/works/work/display-title", json={"title": None})
            self.assertEqual(automatic["title"], "Jugarse la piel")
            self.assertEqual(automatic["original_title"], "Jugarse_la_piel")
            self.assertEqual(edited.get_json()["title"], "Jugarse la piel — Nassim Taleb")
            self.assertEqual(listed["items"][0]["title"], "Jugarse la piel — Nassim Taleb")
            self.assertEqual(restored.get_json()["title"], "Jugarse la piel")

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
