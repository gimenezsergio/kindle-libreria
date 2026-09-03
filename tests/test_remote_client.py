from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from biblioteca_kindle.remote_client import RemotePushError, push_sync
from test_remote_sync import valid_package


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *_): return None
    def read(self): return json.dumps(self.payload).encode()


class RemoteClientTests(unittest.TestCase):
    def prepare_pending(self, root: Path) -> tuple[Path, dict]:
        state = root / "state"
        state.mkdir()
        package = valid_package()
        (state / "pending-sync-package.json").write_text(json.dumps(package), encoding="utf-8")
        return state, package

    def test_sends_pending_package_and_deletes_it_after_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, package = self.prepare_pending(Path(directory))
            captured = {}
            def opener(request, timeout):
                captured["url"] = request.full_url
                captured["authorization"] = request.get_header("Authorization")
                captured["timeout"] = timeout
                return FakeResponse({"schema_version": 1, "package_id": package["package_id"], "status": "applied", "changes": {}, "totals": {}, "warnings": []})
            result = push_sync("unused.sqlite3", server_url="http://127.0.0.1:8000", token="secret", state_directory=state, source_timezone="America/Argentina/Buenos_Aires", opener=opener)
            self.assertTrue(result.reused_pending)
            self.assertFalse((state / "pending-sync-package.json").exists())
            self.assertEqual(captured["authorization"], "Bearer secret")
            self.assertTrue(captured["url"].endswith("/api/sync/v1/packages"))

    def test_network_failure_preserves_exact_pending_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, package = self.prepare_pending(Path(directory))
            def failing(*_args, **_kwargs): raise URLError("offline")
            with self.assertRaisesRegex(RemotePushError, "quedó pendiente"):
                push_sync("unused.sqlite3", server_url="https://example.com", token="secret", state_directory=state, source_timezone="America/Argentina/Buenos_Aires", attempts=2, opener=failing)
            self.assertEqual(json.loads((state / "pending-sync-package.json").read_text()), package)

    def test_rejects_insecure_remote_url_and_missing_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RemotePushError, "HTTPS"):
                push_sync("unused", server_url="http://example.com", token="secret", state_directory=directory, source_timezone="UTC")
            with self.assertRaisesRegex(RemotePushError, "TOKEN"):
                push_sync("unused", server_url="https://example.com", token="", state_directory=directory, source_timezone="UTC")


if __name__ == "__main__": unittest.main()
