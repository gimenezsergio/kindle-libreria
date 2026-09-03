CREATE TABLE conversation_message_sources (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES conversation_messages(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    work_title_snapshot TEXT NOT NULL,
    label_snapshot TEXT NOT NULL,
    content_snapshot TEXT NOT NULL,
    reference_snapshot TEXT,
    relevance_score REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(message_id, source_type, source_id)
);

CREATE INDEX idx_conversation_message_sources_message
ON conversation_message_sources(message_id, relevance_score DESC);

PRAGMA optimize;
