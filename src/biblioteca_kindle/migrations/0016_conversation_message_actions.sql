ALTER TABLE conversation_messages
ADD COLUMN companion_action_id TEXT;

ALTER TABLE conversation_messages
ADD COLUMN companion_action_label_snapshot TEXT;

CREATE INDEX idx_conversation_messages_action
ON conversation_messages(conversation_id, companion_action_id)
WHERE companion_action_id IS NOT NULL;

PRAGMA optimize;
