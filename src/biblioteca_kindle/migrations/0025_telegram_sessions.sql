CREATE TABLE IF NOT EXISTS telegram_sessions (
    user_id INTEGER PRIMARY KEY,
    active_work_id TEXT REFERENCES works(id) ON DELETE SET NULL,
    active_conversation_id TEXT REFERENCES reading_conversations(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

PRAGMA optimize;
