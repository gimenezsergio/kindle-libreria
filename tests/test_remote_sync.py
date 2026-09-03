from __future__ import annotations

import unittest
import tempfile
import json
from pathlib import Path

from biblioteca_kindle.db import connect_database, migrate_database
from biblioteca_kindle.remote_sync import (
    SyncPackageError,
    load_sync_schema,
    validate_sync_package,
    validate_sync_response,
    build_sync_package,
    write_sync_package,
)


def valid_package() -> dict:
    return {
        "schema_version": 1,
        "package_id": "11111111-1111-4111-8111-111111111111",
        "created_at_utc": "2026-09-03T13:30:00Z",
        "agent_id": "22222222-2222-4222-8222-222222222222",
        "device_key": "opaque-device",
        "snapshot": {
            "kind": "full",
            "started_at_utc": "2026-09-03T13:29:00Z",
            "completed_at_utc": "2026-09-03T13:29:40Z",
            "mount_read_only": True,
            "source_timezone": "America/Argentina/Buenos_Aires",
        },
        "entities": {
            "works": [{"id": "work-1"}],
            "editions": [{"id": "edition-1"}],
            "contributors": [],
            "edition_contributors": [],
            "deliveries": [{"id": "delivery-1"}],
            "external_identifiers": [],
            "title_aliases": [],
            "source_observations": [],
            "annotations": [],
            "annotation_occurrences": [],
            "reading_states": [],
            "reading_history_records": [],
        },
        "present_delivery_ids": ["delivery-1"],
        "warnings": [],
    }


class RemoteSyncContractTests(unittest.TestCase):
    def test_embedded_schemas_are_loadable(self) -> None:
        self.assertEqual(load_sync_schema()["properties"]["schema_version"]["const"], 1)
        self.assertEqual(load_sync_schema("response")["properties"]["schema_version"]["const"], 1)

    def test_accepts_valid_package(self) -> None:
        validate_sync_package(valid_package())

    def test_rejects_missing_and_unknown_top_level_fields(self) -> None:
        package = valid_package()
        del package["agent_id"]
        with self.assertRaisesRegex(SyncPackageError, "faltan campos: agent_id"):
            validate_sync_package(package)
        package = valid_package()
        package["surprise"] = True
        with self.assertRaisesRegex(SyncPackageError, "campos desconocidos: surprise"):
            validate_sync_package(package)

    def test_rejects_incompatible_version_and_writable_mount(self) -> None:
        package = valid_package()
        package["schema_version"] = 2
        with self.assertRaisesRegex(SyncPackageError, "versión 1"):
            validate_sync_package(package)
        package = valid_package()
        package["snapshot"]["mount_read_only"] = False
        with self.assertRaisesRegex(SyncPackageError, "solo lectura"):
            validate_sync_package(package)

    def test_rejects_duplicate_or_unknown_present_delivery(self) -> None:
        package = valid_package()
        package["present_delivery_ids"] *= 2
        with self.assertRaisesRegex(SyncPackageError, "contiene duplicados"):
            validate_sync_package(package)
        package = valid_package()
        package["present_delivery_ids"] = ["missing"]
        with self.assertRaisesRegex(SyncPackageError, "no incluidas"):
            validate_sync_package(package)

    def test_rejects_book_payload_at_any_depth(self) -> None:
        package = valid_package()
        package["entities"]["works"][0]["book_bytes"] = "base64"
        with self.assertRaisesRegex(SyncPackageError, "no se permite enviar"):
            validate_sync_package(package)

    def test_validates_server_confirmation_and_package_identity(self) -> None:
        response = {
            "schema_version": 1,
            "package_id": "11111111-1111-4111-8111-111111111111",
            "status": "applied",
            "changes": {"annotations_created": 2},
            "totals": {"works": 1},
            "warnings": [],
        }
        validate_sync_response(response, expected_package_id=response["package_id"])
        with self.assertRaisesRegex(SyncPackageError, "otro paquete"):
            validate_sync_response(
                response,
                expected_package_id="33333333-3333-4333-8333-333333333333",
            )

    def test_rejects_invalid_response_counts(self) -> None:
        response = {
            "schema_version": 1,
            "package_id": "11111111-1111-4111-8111-111111111111",
            "status": "already_applied",
            "changes": {"annotations_created": -1},
            "totals": {},
            "warnings": [],
        }
        with self.assertRaisesRegex(SyncPackageError, "no negativos"):
            validate_sync_response(response)

    def test_exports_latest_completed_snapshot_without_book_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "library.sqlite3"
            migrate_database(database)
            connection = connect_database(database)
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO device_snapshots(id, device_key, mount_point, mount_read_only, status, started_at, completed_at) VALUES ('snapshot', 'device', ?, 1, 'completed', '2026-09-03T13:00:00+00:00', '2026-09-03T13:01:00+00:00')",
                        (str(root / "Kindle"),),
                    )
                    connection.execute("INSERT INTO works(id, preferred_title) VALUES ('work', 'Book')")
                    connection.execute("INSERT INTO editions(id, work_id, title) VALUES ('edition', 'work', 'Book')")
                    connection.execute(
                        "INSERT INTO kindle_deliveries(id, edition_id, document_format, relative_path, file_size, first_seen_at, last_seen_at, presence) VALUES ('delivery', 'edition', 'KFX', 'documents/book.kfx', 999, '2026-09-03', '2026-09-03', 'present')"
                    )
            finally:
                connection.close()
            package = build_sync_package(
                database,
                agent_id="22222222-2222-4222-8222-222222222222",
                source_timezone="America/Argentina/Buenos_Aires",
            )
            output = root / "out" / "package.json"
            result = write_sync_package(package, output)
            loaded = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(loaded["present_delivery_ids"], ["delivery"])
            self.assertEqual(loaded["entities"]["works"][0]["preferred_title"], "Book")
            self.assertNotIn("_local_mount_point", loaded)
            self.assertEqual(result.entity_count, 3)
            self.assertGreater(result.byte_count, 0)

    def test_refuses_to_write_package_inside_kindle(self) -> None:
        package = valid_package()
        package["_local_mount_point"] = "/media/user/Kindle"
        with self.assertRaisesRegex(SyncPackageError, "dentro del Kindle"):
            write_sync_package(package, "/media/user/Kindle/package.json")


if __name__ == "__main__":
    unittest.main()
