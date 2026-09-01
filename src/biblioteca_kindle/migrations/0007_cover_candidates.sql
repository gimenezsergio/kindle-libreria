CREATE TABLE cover_candidates (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    local_path TEXT NOT NULL,
    source_label TEXT NOT NULL,
    isbn TEXT,
    edition_label TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('high', 'medium', 'low')),
    display_order INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'available'
        CHECK (status IN ('available', 'rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (work_id, local_path)
) STRICT;

CREATE INDEX idx_cover_candidates_work_status
    ON cover_candidates(work_id, status, display_order);
