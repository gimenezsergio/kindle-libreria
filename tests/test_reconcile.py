from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.reconcile import reconcile_provisional_titles


class AnnotationSourceReconciliationTests(unittest.TestCase):
    def test_merges_superseded_clipping_into_native_backed_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute("INSERT INTO works(id,preferred_title) VALUES ('work','Book')")
                    connection.execute("INSERT INTO editions(id,work_id,title) VALUES ('edition','work','Book')")
                    connection.execute("INSERT INTO device_snapshots(id,device_key,mount_point,mount_read_only,status,started_at) VALUES ('snapshot','device','/Kindle',1,'completed','2026-09-03')")
                    for source, source_type in (("old-source","clippings"),("new-source","clippings"),("native-source","sidecar")):
                        connection.execute("INSERT INTO source_observations(id,snapshot_id,source_type,source_relative_path,file_size,file_hash,observed_at,parse_status) VALUES (?,'snapshot',?,?,1,?,'2026-09-03','parsed')", (source,source_type,source,source))
                    connection.execute("INSERT INTO annotations(id,edition_id,kind,text,native_created_at) VALUES ('old','edition','highlight','escribe: «Quien vive de lo igual»','Location 122-123 | Added on Thursday, 13 August 2026 15:35:30')")
                    connection.execute("INSERT INTO annotations(id,edition_id,kind,text,native_created_at) VALUES ('current','edition','highlight','«Quien vive de lo igual»','Location 122-123 | Added on Thursday, 13 August 2026 15:35:47')")
                    connection.execute("INSERT INTO annotation_occurrences(id,annotation_id,source_observation_id,source_kind,source_record_key,observed_at) VALUES ('old-occ','old','old-source','clippings','old','2026-09-03')")
                    connection.execute("INSERT INTO annotation_occurrences(id,annotation_id,source_observation_id,source_kind,source_record_key,observed_at) VALUES ('new-occ','current','new-source','clippings','new','2026-09-03')")
                    connection.execute("INSERT INTO annotation_occurrences(id,annotation_id,source_observation_id,source_kind,source_record_key,observed_at) VALUES ('native-occ','current','native-source','krds','native','2026-09-03')")
                    result = reconcile_provisional_titles(connection)
                    second = reconcile_provisional_titles(connection)
                annotations = connection.execute("SELECT id,text FROM annotations").fetchall()
                occurrences = connection.execute("SELECT COUNT(*) FROM annotation_occurrences WHERE annotation_id='current'").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(result.revised_annotations, 1)
            self.assertEqual(second.revised_annotations, 0)
            self.assertEqual([tuple(row) for row in annotations], [("current", "«Quien vive de lo igual»")])
            self.assertEqual(occurrences, 3)

    def test_merges_exact_cross_source_match_and_preserves_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO works(id, preferred_title, merge_status) VALUES ('work', 'Book', 'normal')"
                    )
                    connection.execute(
                        "INSERT INTO editions(id, work_id, title) VALUES ('edition', 'work', 'Book')"
                    )
                    connection.execute(
                        "INSERT INTO device_snapshots(id, device_key, mount_point, mount_read_only, status, started_at) VALUES ('snapshot', 'device', '/Kindle', 1, 'completed', '2026-09-03')"
                    )
                    for identifier, kind in (("clip-source", "clippings"), ("krds-source", "sidecar")):
                        connection.execute(
                            "INSERT INTO source_observations(id, snapshot_id, source_type, source_relative_path, file_size, file_modified_at, file_hash, observed_at, parse_status) VALUES (?, 'snapshot', ?, ?, 1, '2026-09-03', ?, '2026-09-03', 'parsed')",
                            (identifier, kind, identifier, identifier),
                        )
                    connection.execute(
                        "INSERT INTO annotations(id, edition_id, kind, text, native_created_at) VALUES ('clip', 'edition', 'highlight', 'Selected text', 'Location 10 | Added on Thursday, 3 September 2026 10:20:30')"
                    )
                    connection.execute(
                        "INSERT INTO annotations(id, edition_id, kind, start_position_native, end_position_native, native_created_at) VALUES ('native', 'edition', 'highlight', 'start', 'end', '2026-09-03T13:20:30.432000+00:00')"
                    )
                    connection.execute(
                        "INSERT INTO annotation_occurrences(id, annotation_id, source_observation_id, source_kind, source_record_key, observed_at) VALUES ('clip-occurrence', 'clip', 'clip-source', 'clippings', 'clip-key', '2026-09-03')"
                    )
                    connection.execute(
                        "INSERT INTO annotation_occurrences(id, annotation_id, source_observation_id, source_kind, source_record_key, observed_at) VALUES ('native-occurrence', 'native', 'krds-source', 'krds', 'native-key', '2026-09-03')"
                    )
                    result = reconcile_provisional_titles(connection)
                    second = reconcile_provisional_titles(connection)

                annotation = connection.execute(
                    "SELECT text, start_position_native, end_position_native FROM annotations"
                ).fetchone()
                occurrences = connection.execute(
                    "SELECT annotation_id, COUNT(*) AS total FROM annotation_occurrences GROUP BY annotation_id"
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(result.merged_annotations, 1)
            self.assertEqual(second.merged_annotations, 0)
            self.assertEqual(tuple(annotation), ("Selected text", "start", "end"))
            self.assertEqual(tuple(occurrences), ("clip", 2))

    def test_does_not_merge_ambiguous_native_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute("INSERT INTO works(id, preferred_title) VALUES ('work', 'Book')")
                    connection.execute("INSERT INTO editions(id, work_id, title) VALUES ('edition', 'work', 'Book')")
                    connection.execute(
                        "INSERT INTO device_snapshots(id, device_key, mount_point, mount_read_only, status, started_at) VALUES ('snapshot', 'device', '/Kindle', 1, 'completed', '2026-09-03')"
                    )
                    for index in range(3):
                        source = f"source-{index}"
                        connection.execute(
                            "INSERT INTO source_observations(id, snapshot_id, source_type, source_relative_path, file_size, file_modified_at, file_hash, observed_at, parse_status) VALUES (?, 'snapshot', 'sidecar', ?, 1, '2026-09-03', ?, '2026-09-03', 'parsed')",
                            (source, source, source),
                        )
                    connection.execute(
                        "INSERT INTO annotations(id, edition_id, kind, text, native_created_at) VALUES ('clip', 'edition', 'highlight', 'Text', 'Location 10 | Added on Thursday, 3 September 2026 10:20:30')"
                    )
                    connection.execute(
                        "INSERT INTO annotation_occurrences(id, annotation_id, source_observation_id, source_kind, source_record_key, observed_at) VALUES ('occ-clip', 'clip', 'source-0', 'clippings', 'clip', '2026-09-03')"
                    )
                    for index in (1, 2):
                        connection.execute(
                            "INSERT INTO annotations(id, edition_id, kind, native_created_at) VALUES (?, 'edition', 'highlight', '2026-09-03T13:20:30+00:00')",
                            (f"native-{index}",),
                        )
                        connection.execute(
                            "INSERT INTO annotation_occurrences(id, annotation_id, source_observation_id, source_kind, source_record_key, observed_at) VALUES (?, ?, ?, 'krds', ?, '2026-09-03')",
                            (f"occ-{index}", f"native-{index}", f"source-{index}", f"key-{index}"),
                        )
                    result = reconcile_provisional_titles(connection)
                total = connection.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(result.merged_annotations, 0)
            self.assertEqual(total, 3)


if __name__ == "__main__":
    unittest.main()
