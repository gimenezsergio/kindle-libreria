CREATE TABLE reading_history_records (
    id TEXT PRIMARY KEY,
    reading_state_id TEXT NOT NULL REFERENCES reading_states(id) ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    position_native TEXT NOT NULL,
    recorded_at TEXT,
    UNIQUE (reading_state_id, sequence_number)
) STRICT;

CREATE INDEX reading_history_state_idx
    ON reading_history_records(reading_state_id, sequence_number);

