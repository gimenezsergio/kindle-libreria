from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.ai import PromptPacket
from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.laboratorio import (
    create_inquiry,
    get_inquiry,
    list_work_inquiries,
    add_inquiry_message,
    generate_tutor_response,
    generate_synthesis_outline,
    save_final_reflection,
    save_inquiry_draft,
    LaboratorioError,
)



class MockProvider:
    name = "mock"
    ready = True

    def __init__(self, response: str = "Respuesta del tutor"):
        self.response = response
        self.last_packet: PromptPacket | None = None

    def respond(self, packet: PromptPacket) -> str:
        self.last_packet = packet
        return self.response


class LaboratorioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        migrate_database(self.database_path)

        # Crear obra y edición de prueba
        conn = connect_database(self.database_path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO works (id, preferred_title) VALUES ('work-1', 'La Odisea')"
                )
                conn.execute(
                    "INSERT INTO editions (id, work_id, title) VALUES ('ed-1', 'work-1', 'La Odisea')"
                )
                conn.execute(
                    """
                    INSERT INTO annotations (id, edition_id, kind, text, status)
                    VALUES ('ann-1', 'ed-1', 'highlight', 'Todo forastero e indigente viene de parte de Zeus', 'active')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO annotation_contexts (annotation_id, chapter_title, surrounding_before, surrounding_after)
                    VALUES ('ann-1', 'Canto XIV', 'Eumeo recibió al huésped.', 'Y dio de comer al porquerizo.')
                    """
                )
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_and_get_inquiry(self) -> None:
        inquiry = create_inquiry(
            self.database_path,
            work_id="work-1",
            dilemma_question="¿Es la hospitalidad un deber incondicional?",
            chapter_or_section="Canto XIV",
            annotation_ids=["ann-1"],
        )

        self.assertEqual(inquiry["work_id"], "work-1")
        self.assertEqual(inquiry["dilemma_question"], "¿Es la hospitalidad un deber incondicional?")
        self.assertEqual(inquiry["chapter_or_section"], "Canto XIV")
        self.assertEqual(inquiry["status"], "sparring")
        self.assertEqual(len(inquiry["annotations"]), 1)
        self.assertEqual(inquiry["annotations"][0]["id"], "ann-1")
        self.assertEqual(inquiry["annotations"][0]["chapter_title"], "Canto XIV")
        self.assertIn("Eumeo recibió", inquiry["annotations"][0]["surrounding_before"])

    def test_add_messages_and_sequence(self) -> None:
        inquiry = create_inquiry(
            self.database_path,
            work_id="work-1",
            dilemma_question="¿Es la hospitalidad un deber?",
        )

        m1 = add_inquiry_message(
            self.database_path,
            inquiry_id=inquiry["id"],
            role="user",
            content="Creo que sí, porque el forastero está indefenso.",
        )
        self.assertEqual(m1["sequence"], 1)
        self.assertEqual(m1["role"], "user")

        m2 = add_inquiry_message(
            self.database_path,
            inquiry_id=inquiry["id"],
            role="tutor",
            content="¿Incluso si el forastero es una amenaza probada para la aldea?",
        )
        self.assertEqual(m2["sequence"], 2)
        self.assertEqual(m2["role"], "tutor")

        updated = get_inquiry(self.database_path, inquiry["id"])
        self.assertEqual(len(updated["messages"]), 2)
        self.assertEqual(updated["messages"][0]["content"], m1["content"])
        self.assertEqual(updated["messages"][1]["content"], m2["content"])

    def test_generate_tutor_response(self) -> None:
        inquiry = create_inquiry(
            self.database_path,
            work_id="work-1",
            dilemma_question="¿Deber de hospitalidad?",
            annotation_ids=["ann-1"],
        )
        add_inquiry_message(
            self.database_path,
            inquiry_id=inquiry["id"],
            role="user",
            content="La hospitalidad debe ser total.",
        )

        mock = MockProvider("¿Y qué ocurre cuando los recursos de la comunidad son escasos?")
        resp = generate_tutor_response(
            self.database_path,
            inquiry_id=inquiry["id"],
            provider=mock,
            work_title="La Odisea",
        )

        self.assertEqual(resp["role"], "tutor")
        self.assertEqual(resp["content"], "¿Y qué ocurre cuando los recursos de la comunidad son escasos?")
        self.assertIn("COLEGA DE LECTURA EXIGENTE", mock.last_packet.instructions)
        self.assertIn("La Odisea", mock.last_packet.instructions)
        self.assertIn("Todo forastero e indigente", mock.last_packet.instructions)

    def test_generate_synthesis_outline(self) -> None:
        inquiry = create_inquiry(
            self.database_path,
            work_id="work-1",
            dilemma_question="¿Deber de hospitalidad?",
        )
        add_inquiry_message(
            self.database_path,
            inquiry_id=inquiry["id"],
            role="user",
            content="La hospitalidad es un imperativo ético.",
        )

        mock_json = """
        {
          "outline_thesis": "La hospitalidad es un imperativo que define la humanidad de quien recibe.",
          "outline_objection": "El riesgo de seguridad y escasez en la comunidad anfitriona.",
          "outline_counterargument": "El deber persiste si no hay evidencia manifiesta de agresión."
        }
        """
        mock = MockProvider(mock_json)
        outline = generate_synthesis_outline(
            self.database_path,
            inquiry_id=inquiry["id"],
            provider=mock,
        )

        self.assertEqual(outline["outline_thesis"], "La hospitalidad es un imperativo que define la humanidad de quien recibe.")
        updated = get_inquiry(self.database_path, inquiry["id"])
        self.assertEqual(updated["status"], "ready_to_write")
        self.assertEqual(updated["outline_objection"], "El riesgo de seguridad y escasez en la comunidad anfitriona.")

    def test_save_final_reflection(self) -> None:
        inquiry = create_inquiry(
            self.database_path,
            work_id="work-1",
            dilemma_question="¿Deber de hospitalidad?",
        )

        text = "La hospitalidad en Homero no es beneficencia sino un pacto sagrado que civiliza el encuentro con el otro."
        updated = save_final_reflection(
            self.database_path,
            inquiry_id=inquiry["id"],
            final_text=text,
            tags=["Hospitalidad", "Comunidad", "Zeus"],
        )

        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["final_text"], text)
        self.assertEqual(updated["word_count"], len(text.split()))
        self.assertEqual(updated["tags"], ["Comunidad", "Hospitalidad", "Zeus"])

        inquiries = list_work_inquiries(self.database_path, "work-1")
        self.assertEqual(len(inquiries), 1)
        self.assertEqual(inquiries[0]["id"], inquiry["id"])
        self.assertEqual(inquiries[0]["tags"], ["Comunidad", "Hospitalidad", "Zeus"])

    def test_save_inquiry_draft(self) -> None:
        inquiry = create_inquiry(
            self.database_path,
            work_id="work-1",
            dilemma_question="¿Deber de hospitalidad?",
        )

        draft_text = "Primer borrador incompleto..."
        updated = save_inquiry_draft(
            self.database_path,
            inquiry_id=inquiry["id"],
            draft_text=draft_text,
            tags=["Borrador", "Hospitalidad"],
        )

        self.assertEqual(updated["status"], "ready_to_write")
        self.assertEqual(updated["final_text"], draft_text)
        self.assertEqual(updated["word_count"], 3)
        self.assertIsNone(updated["completed_at"])
        self.assertEqual(updated["tags"], ["Borrador", "Hospitalidad"])


if __name__ == "__main__":
    unittest.main()

