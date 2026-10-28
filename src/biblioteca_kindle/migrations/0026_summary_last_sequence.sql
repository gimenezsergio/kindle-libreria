ALTER TABLE conversation_summaries ADD COLUMN last_message_sequence INTEGER;

UPDATE conversation_summaries
SET last_message_sequence = (
    SELECT COALESCE(MAX(sequence), 0)
    FROM conversation_messages
    WHERE conversation_id = conversation_summaries.conversation_id
);
