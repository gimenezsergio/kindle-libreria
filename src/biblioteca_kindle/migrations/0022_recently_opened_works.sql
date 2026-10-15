CREATE TABLE IF NOT EXISTS recently_opened_works (
    work_id TEXT PRIMARY KEY REFERENCES works(id) ON DELETE CASCADE,
    opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dismissed INTEGER NOT NULL DEFAULT 0 CHECK (dismissed IN (0, 1))
) STRICT;

CREATE INDEX IF NOT EXISTS recently_opened_opened_at_idx
    ON recently_opened_works(opened_at DESC);
