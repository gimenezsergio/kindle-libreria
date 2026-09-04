from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.web import create_app


class OpenClawAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "library.sqlite3"
        migrate_database(self.database)
        connection = connect_database(self.database)
        with connection:
            connection.execute("INSERT INTO works(id,preferred_title) VALUES ('work','La_sociedad_del_cansancio')")
            connection.execute("INSERT INTO editions(id,work_id,title) VALUES ('edition','work','La sociedad del cansancio')")
            connection.execute("INSERT INTO contributors(id,display_name,normalized_name) VALUES ('author','Byung Chul Han','byung chul han')")
            connection.execute("INSERT INTO edition_contributors(edition_id,contributor_id,role) VALUES ('edition','author','author')")
            connection.execute("INSERT INTO annotations(id,edition_id,kind,text) VALUES ('annotation','edition','highlight','El exceso de positividad modifica la atención')")
            connection.execute("INSERT INTO personal_notes(id,target_type,target_id,body) VALUES ('note','work','work','Pensar la relación entre cansancio y libertad')")
        connection.close()
        environment = {
            "BIBLIOTECA_OPENCLAW_TOKEN": "openclaw-test-token",
            "BIBLIOTECA_AI_PROVIDER": "draft",
        }
        self.environment = patch.dict("os.environ", environment, clear=True)
        self.environment.start()
        self.client = create_app(self.database).test_client()
        self.headers = {"Authorization": "Bearer openclaw-test-token"}

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def test_requires_an_independent_bearer_token(self) -> None:
        self.assertEqual(self.client.get("/api/openclaw/v1/status").status_code, 401)
        response = self.client.get("/api/openclaw/v1/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["api_version"], 1)

    def test_can_find_a_work_and_list_profiles(self) -> None:
        works = self.client.get(
            "/api/openclaw/v1/works?q=Byung-Chul", headers=self.headers
        ).get_json()["items"]
        profiles = self.client.get(
            "/api/openclaw/v1/profiles", headers=self.headers
        ).get_json()["items"]
        self.assertEqual(works[0]["id"], "work")
        self.assertEqual(works[0]["title"], "La sociedad del cansancio")
        self.assertEqual(profiles[0]["id"], "companion")
        self.assertNotIn("prompt", profiles[0])

    def test_prepares_and_completes_a_traceable_turn_idempotently(self) -> None:
        created = self.client.post(
            "/api/openclaw/v1/works/work/conversations",
            headers=self.headers,
            json={"profile_id": "companion", "title": "Conversación por Telegram"},
        )
        self.assertEqual(created.status_code, 201)
        conversation_id = created.get_json()["id"]

        context = self.client.get(
            f"/api/openclaw/v1/conversations/{conversation_id}/context",
            headers=self.headers,
        ).get_json()
        self.assertEqual(context["annotations"][0]["id"], "annotation")

        prepared = self.client.post(
            f"/api/openclaw/v1/conversations/{conversation_id}/turns",
            headers=self.headers,
            json={
                "content": "¿Cómo se relacionan cansancio y libertad?",
                "personal_note_ids": ["note"],
                "annotation_ids": ["annotation"],
                "search_library": True,
                "search_scope": "library",
            },
        )
        self.assertEqual(prepared.status_code, 201)
        turn = prepared.get_json()
        self.assertIn("prompt", turn)
        self.assertIn("Pensar la relación", str(turn["prompt"]))
        self.assertTrue(turn["library_sources"])

        completed = self.client.post(
            f"/api/openclaw/v1/turns/{turn['turn_id']}/complete",
            headers=self.headers,
            json={"content": "Podemos pensarlo como una tensión, no como una conclusión."},
        )
        repeated = self.client.post(
            f"/api/openclaw/v1/turns/{turn['turn_id']}/complete",
            headers=self.headers,
            json={"content": "Esta respuesta duplicada no debe guardarse."},
        )
        self.assertEqual(completed.status_code, 201)
        self.assertEqual(repeated.status_code, 200)
        self.assertFalse(repeated.get_json()["created"])
        self.assertEqual(completed.get_json()["message_id"], repeated.get_json()["message_id"])

        detail = self.client.get(
            f"/api/openclaw/v1/conversations/{conversation_id}", headers=self.headers
        ).get_json()
        self.assertEqual([message["role"] for message in detail["messages"]], ["user", "assistant"])
        self.assertTrue(detail["messages"][-1]["library_sources"])
        self.assertNotIn("profile_prompt_snapshot", detail)


if __name__ == "__main__":
    unittest.main()
