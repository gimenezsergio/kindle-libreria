ALTER TABLE conversation_context_sources
ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0, 1));

PRAGMA optimize;
