from __future__ import annotations

import unittest

from biblioteca_kindle.remote_sync import (
    SyncPackageError,
    load_sync_schema,
    validate_sync_package,
    validate_sync_response,
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
            "deliveries": [{"id": "delivery-1"}],
            "source_observations": [],
            "annotations": [],
            "annotation_occurrences": [],
            "reading_states": [],
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


if __name__ == "__main__":
    unittest.main()
