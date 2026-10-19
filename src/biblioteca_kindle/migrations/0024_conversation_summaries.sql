CREATE TABLE IF NOT EXISTS conversation_summaries (
    conversation_id TEXT PRIMARY KEY REFERENCES reading_conversations(id) ON DELETE CASCADE,
    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL REFERENCES ai_profiles(id) ON DELETE CASCADE,
    profile_name_snapshot TEXT NOT NULL,
    title_snapshot TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;

CREATE INDEX IF NOT EXISTS conversation_summaries_work_idx
    ON conversation_summaries(work_id, updated_at DESC);

CREATE TABLE conversation_context_sources_new (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES reading_conversations(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('work', 'personal_note', 'annotation', 'conversation_summary')),
    source_id TEXT NOT NULL,
    label_snapshot TEXT NOT NULL,
    content_snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_pinned INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0, 1)),
    UNIQUE (conversation_id, source_type, source_id)
);

INSERT INTO conversation_context_sources_new (
    id, conversation_id, source_type, source_id, label_snapshot, content_snapshot, created_at, is_pinned
)
SELECT id, conversation_id, source_type, source_id, label_snapshot, content_snapshot, created_at, is_pinned
FROM conversation_context_sources;

DROP TABLE conversation_context_sources;

ALTER TABLE conversation_context_sources_new RENAME TO conversation_context_sources;

CREATE INDEX idx_conversation_context_conversation
ON conversation_context_sources(conversation_id, source_type);

PRAGMA optimize;
