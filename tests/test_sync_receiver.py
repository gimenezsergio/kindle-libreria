from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.remote_sync import SyncPackageError
from biblioteca_kindle.sync_receiver import apply_sync_package
from biblioteca_kindle.web import create_app


def package() -> dict:
    return {
        "schema_version": 1,
        "package_id": "11111111-1111-4111-8111-111111111111",
        "created_at_utc": "2026-09-03T13:30:00Z",
        "agent_id": "22222222-2222-4222-8222-222222222222",
        "device_key": "device",
        "snapshot": {"kind": "full", "started_at_utc": "2026-09-03T13:00:00Z", "completed_at_utc": "2026-09-03T13:01:00Z", "mount_read_only": True, "source_timezone": "America/Argentina/Buenos_Aires"},
        "entities": {
            "works": [{"id": "work", "preferred_title": "Book", "merge_status": "normal", "created_at": "2026-09-03", "updated_at": "2026-09-03", "display_title": None}],
            "editions": [{"id": "edition", "work_id": "work", "title": "Book", "subtitle": None, "language": None, "publication_date": None, "publisher": None, "format_hint": "KFX", "created_at": "2026-09-03", "updated_at": "2026-09-03"}],
            "contributors": [], "edition_contributors": [],
            "deliveries": [{"id": "delivery", "edition_id": "edition", "source_observation_id": None, "kindle_content_id": "content", "content_type": "kindle.pdoc", "document_format": "KFX", "relative_path": "documents/book.kfx", "sidecar_relative_path": None, "file_size": 10, "file_modified_at": None, "content_hash": "hash", "first_seen_at": "2026-09-03", "last_seen_at": "2026-09-03", "presence": "present"}],
            "external_identifiers": [], "title_aliases": [], "device_snapshots": [], "source_observations": [],
            "annotations": [], "annotation_occurrences": [], "reading_states": [], "reading_history_records": [],
        },
        "present_delivery_ids": ["delivery"], "warnings": [],
    }


class SyncReceiverTests(unittest.TestCase):
    def test_applies_and_replays_package_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "server.sqlite3"
            first = apply_sync_package(database, package())
            second = apply_sync_package(database, package())
            self.assertEqual(first["status"], "applied")
            self.assertEqual(second["status"], "already_applied")
            connection = connect_database(database)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM works").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM remote_sync_packages").fetchone()[0], 1)
            finally:
                connection.close()

    def test_rejects_same_id_with_different_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "server.sqlite3"
            apply_sync_package(database, package())
            changed = copy.deepcopy(package())
            changed["warnings"] = ["changed"]
            with self.assertRaisesRegex(SyncPackageError, "contenido diferente"):
                apply_sync_package(database, changed)

    def test_endpoint_requires_token_and_returns_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"BIBLIOTECA_SYNC_TOKEN": "secret"}
        ):
            database = Path(directory) / "server.sqlite3"
            migrate_database(database)
            client = create_app(database).test_client()
            self.assertEqual(client.post("/api/sync/v1/packages", json=package()).status_code, 401)
            headers = {"Authorization": "Bearer secret"}
            first = client.post("/api/sync/v1/packages", json=package(), headers=headers)
            second = client.post("/api/sync/v1/packages", json=package(), headers=headers)
            self.assertEqual(first.status_code, 201)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.get_json()["status"], "already_applied")

    def test_invalid_foreign_key_rolls_back_everything(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "server.sqlite3"
            broken = package()
            broken["entities"]["editions"][0]["work_id"] = "missing"
            with self.assertRaises(Exception):
                apply_sync_package(database, broken)
            connection = connect_database(database)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM works").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM remote_sync_packages").fetchone()[0], 0)
            finally:
                connection.close()

    def test_complete_snapshot_marks_absent_without_deleting_private_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "server.sqlite3"
            apply_sync_package(database, package())
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO personal_notes(id,target_type,target_id,body) VALUES ('note','work','work','Private')"
                    )
            finally:
                connection.close()
            next_package = copy.deepcopy(package())
            next_package["package_id"] = "33333333-3333-4333-8333-333333333333"
            next_package["present_delivery_ids"] = []
            response = apply_sync_package(database, next_package)
            connection = connect_database(database)
            try:
                presence = connection.execute("SELECT presence FROM kindle_deliveries").fetchone()[0]
                notes = connection.execute("SELECT COUNT(*) FROM personal_notes").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(response["changes"]["books_marked_absent"], 1)
            self.assertEqual(presence, "absent")
            self.assertEqual(notes, 1)

    def test_malformed_or_oversized_http_body_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {"BIBLIOTECA_SYNC_TOKEN": "secret", "BIBLIOTECA_SYNC_MAX_BYTES": "100"},
        ):
            database = Path(directory) / "server.sqlite3"
            migrate_database(database)
            client = create_app(database).test_client()
            headers = {"Authorization": "Bearer secret", "Content-Type": "application/json"}
            malformed = client.post("/api/sync/v1/packages", data=b'{"broken":', headers=headers)
            oversized = client.post("/api/sync/v1/packages", data=b'{' + b' ' * 200 + b'}', headers=headers)
            self.assertEqual(malformed.status_code, 400)
            self.assertEqual(oversized.status_code, 413)
            connection = connect_database(database)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM remote_sync_packages").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM works").fetchone()[0], 0)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
