from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.personal import (
    PersonalDataError,
    add_work_note,
    add_work_relation,
    assign_work_to_collection,
    create_collection,
    set_work_display_title,
)


class PersonalDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "library.sqlite3"
        migrate_database(self.database)
        connection = connect_database(self.database)
        try:
            with connection:
                connection.executemany(
                    "INSERT INTO works(id, preferred_title) VALUES (?, ?)",
                    [("work-a", "Obra A"), ("work-b", "Obra B")],
                )
        finally:
            connection.close()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_root_and_nested_collections_idempotently(self) -> None:
        root = create_collection(self.database, "  Temas   políticos  ")
        repeated = create_collection(
            self.database, "Temas políticos", description="Lecturas relacionadas"
        )
        child = create_collection(
            self.database, "Poder", parent_id=root.id
        )
        repeated_child = create_collection(
            self.database, "Poder", parent_id=root.id
        )

        self.assertTrue(root.created)
        self.assertFalse(repeated.created)
        self.assertEqual(root.id, repeated.id)
        self.assertTrue(child.created)
        self.assertFalse(repeated_child.created)
        self.assertEqual(child.id, repeated_child.id)

        connection = connect_database(self.database)
        try:
            count = connection.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
            description = connection.execute(
                "SELECT description FROM collections WHERE id = ?", (root.id,)
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 2)
        self.assertEqual(description, "Lecturas relacionadas")

    def test_assign_work_updates_existing_assignment(self) -> None:
        collection = create_collection(self.database, "Drama")

        self.assertTrue(
            assign_work_to_collection(
                self.database, "work-a", collection.id, note="Primera", display_order=2
            )
        )
        self.assertFalse(
            assign_work_to_collection(
                self.database, "work-a", collection.id, note="Revisada", display_order=1
            )
        )

        connection = connect_database(self.database)
        try:
            row = connection.execute(
                "SELECT note, display_order FROM work_collections"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual((row["note"], row["display_order"]), ("Revisada", 1))

    def test_personal_notes_are_distinct_and_empty_note_is_rejected(self) -> None:
        first = add_work_note(self.database, "work-a", "  Una interpretación.  ")
        second = add_work_note(self.database, "work-a", "Una interpretación.")

        self.assertNotEqual(first, second)
        connection = connect_database(self.database)
        try:
            rows = connection.execute(
                "SELECT body FROM personal_notes ORDER BY created_at, id"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual([row["body"] for row in rows], ["Una interpretación."] * 2)
        with self.assertRaises(PersonalDataError):
            add_work_note(self.database, "work-a", "   ")

    def test_display_title_can_be_set_and_restored_to_automatic(self) -> None:
        self.assertEqual(
            set_work_display_title(self.database, "work-a", "  Obra   corregida "),
            "Obra corregida",
        )
        self.assertIsNone(set_work_display_title(self.database, "work-a", None))
        connection = connect_database(self.database)
        try:
            value = connection.execute(
                "SELECT display_title FROM works WHERE id = 'work-a'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertIsNone(value)

    def test_reversed_symmetric_relation_updates_the_same_relation(self) -> None:
        first = add_work_relation(
            self.database,
            "work-a",
            "work-b",
            "Tema común",
            explanation="Primera lectura",
            symmetric=True,
        )
        reversed_relation = add_work_relation(
            self.database,
            "work-b",
            "work-a",
            "tema común",
            explanation="Explicación revisada",
            symmetric=True,
        )

        self.assertTrue(first.created)
        self.assertFalse(reversed_relation.created)
        self.assertEqual(first.id, reversed_relation.id)
        connection = connect_database(self.database)
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS total, explanation FROM work_relations"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row["total"], 1)
        self.assertEqual(row["explanation"], "Explicación revisada")

    def test_invalid_references_and_self_relation_are_rejected(self) -> None:
        collection = create_collection(self.database, "Ideas")
        with self.assertRaises(PersonalDataError):
            create_collection(self.database, "Hija", parent_id="missing")
        with self.assertRaises(PersonalDataError):
            assign_work_to_collection(self.database, "missing", collection.id)
        with self.assertRaises(PersonalDataError):
            assign_work_to_collection(self.database, "work-a", "missing")
        with self.assertRaises(PersonalDataError):
            add_work_note(self.database, "missing", "Nota")
        with self.assertRaises(PersonalDataError):
            add_work_relation(self.database, "work-a", "work-a", "eco")


if __name__ == "__main__":
    unittest.main()
