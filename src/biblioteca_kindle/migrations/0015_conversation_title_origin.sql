ALTER TABLE reading_conversations
ADD COLUMN title_origin TEXT NOT NULL DEFAULT 'legacy'
CHECK (title_origin IN ('legacy', 'pending', 'automatic', 'manual'));

CREATE INDEX idx_reading_conversations_title_origin
ON reading_conversations(title_origin);
