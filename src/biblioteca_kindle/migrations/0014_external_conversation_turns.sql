CREATE TABLE external_conversation_turns (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES reading_conversations(id) ON DELETE CASCADE,
    user_message_id TEXT NOT NULL UNIQUE REFERENCES conversation_messages(id) ON DELETE CASCADE,
    assistant_message_id TEXT UNIQUE REFERENCES conversation_messages(id) ON DELETE SET NULL,
    source_snapshot_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'prepared' CHECK (status IN ('prepared', 'completed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE INDEX idx_external_turns_conversation
ON external_conversation_turns(conversation_id, created_at DESC);

PRAGMA optimize;
