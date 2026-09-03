CREATE TABLE remote_sync_packages (
    package_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    device_key TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    response_json TEXT NOT NULL CHECK (json_valid(response_json))
) STRICT;
