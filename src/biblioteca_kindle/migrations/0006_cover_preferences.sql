CREATE TABLE work_cover_preferences (
    work_id TEXT PRIMARY KEY REFERENCES works(id) ON DELETE CASCADE,
    selected_path TEXT,
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'confirmed', 'none')),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
) STRICT;
