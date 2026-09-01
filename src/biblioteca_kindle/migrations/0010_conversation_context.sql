CREATE TABLE conversation_context_sources (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES reading_conversations(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('work', 'personal_note', 'annotation')),
    source_id TEXT NOT NULL,
    label_snapshot TEXT NOT NULL,
    content_snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (conversation_id, source_type, source_id)
);

CREATE INDEX idx_conversation_context_conversation
ON conversation_context_sources(conversation_id, source_type);

INSERT INTO conversation_context_sources(
    id, conversation_id, source_type, source_id, label_snapshot, content_snapshot
)
SELECT lower(hex(randomblob(16))), rc.id, 'work', w.id, 'Ficha del libro',
       'Título: ' || COALESCE(NULLIF(TRIM(w.display_title), ''), REPLACE(w.preferred_title, '_', ' '))
FROM reading_conversations rc
JOIN works w ON w.id = rc.work_id;

PRAGMA optimize;
