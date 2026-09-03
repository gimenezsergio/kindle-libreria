from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.library_search import LibrarySearchError, search_library


class LibrarySearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "library.sqlite3"
        migrate_database(self.database)
        connection = connect_database(self.database)
        with connection:
            connection.execute("INSERT INTO works(id,preferred_title) VALUES ('w1','La_sociedad_del_cansancio')")
            connection.execute("INSERT INTO works(id,preferred_title) VALUES ('w2','1984')")
            connection.execute("INSERT INTO editions(id,work_id,title) VALUES ('e1','w1','Sociedad')")
            connection.execute("INSERT INTO editions(id,work_id,title) VALUES ('e2','w2','1984')")
            connection.execute("INSERT INTO annotations(id,edition_id,kind,text) VALUES ('a1','e1','highlight','Quien vive de lo igual morirá de lo igual')")
            connection.execute("INSERT INTO annotations(id,edition_id,kind,text) VALUES ('a2','e2','highlight','El poder vigila el pensamiento')")
            connection.execute("INSERT INTO personal_notes(id,target_type,target_id,body) VALUES ('n1','work','w2','El poder también modifica el lenguaje')")
        connection.close()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_search_ranks_evidence_and_can_limit_scope(self) -> None:
        results = search_library(self.database, "poder y lenguaje")
        self.assertEqual(results[0]["source_id"], "n1")
        self.assertEqual(results[0]["work_title"], "1984")
        scoped = search_library(self.database, "igual", work_ids=["w1"])
        self.assertTrue(scoped)
        self.assertEqual({item["work_id"] for item in scoped}, {"w1"})

    def test_empty_queries_and_empty_scope_are_safe(self) -> None:
        with self.assertRaises(LibrarySearchError):
            search_library(self.database, "   ")
        self.assertEqual(search_library(self.database, "poder", work_ids=[]), [])


if __name__ == "__main__":
    unittest.main()
