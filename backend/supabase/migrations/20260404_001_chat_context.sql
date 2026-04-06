-- Chat Context Table
-- Stores conversation history per session for AI contextual memory.

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN ('complete', 'partial')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conv_id
    ON chat_messages (conversation_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conv_time
    ON chat_messages (conversation_id, created_at DESC);

-- Atomic add message + pair-trim function
-- Keeps MAX_CHAT_HISTORY/2 exchange pairs (user+assistant = 1 pair)
CREATE OR REPLACE FUNCTION chat_append_message(
    p_conversation_id TEXT,
    p_role TEXT,
    p_content TEXT,
    p_status TEXT DEFAULT 'complete',
    p_max_pairs INTEGER DEFAULT 4
) RETURNS VOID AS $$
DECLARE
    v_count INTEGER;
    v_pairs_to_delete INTEGER;
BEGIN
    -- Insert the new message
    INSERT INTO chat_messages (id, conversation_id, role, content, status)
    VALUES ('msg-' || substr(md5(random()::text), 1, 16), p_conversation_id, p_role, p_content, p_status);

    -- Count total messages for this conversation
    SELECT COUNT(*) INTO v_count FROM chat_messages WHERE conversation_id = p_conversation_id;

    -- If over capacity, delete oldest pair(s)
    IF v_count > (p_max_pairs * 2) THEN
        v_pairs_to_delete := v_count - (p_max_pairs * 2);

        DELETE FROM chat_messages WHERE id IN (
            SELECT id FROM chat_messages
            WHERE conversation_id = p_conversation_id
            ORDER BY created_at ASC
            LIMIT (v_pairs_to_delete * 2)
        );
    END IF;
END;
$$ LANGUAGE plpgsql;
