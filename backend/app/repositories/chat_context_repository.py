"""Chat context repository — stores conversation history for AI contextual memory."""

from app.database.supabase_client import get_supabase_client

# No cap — keep full conversation history per session
MAX_CHAT_HISTORY_PAIRS = 999999


class ChatContextRepository:
    """Repository for chat message history."""

    def get_history(self, conversation_id: str) -> list[dict]:
        """Load recent messages for a conversation, oldest first (capped at MAX_CHAT_HISTORY_PAIRS pairs)."""
        supabase = get_supabase_client()
        result = (
            supabase.table("chat_messages")
            .select("role, content, status")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .execute()
        )
        # Cap at MAX_CHAT_HISTORY_PAIRS*2 messages (last N complete exchanges)
        return [{"role": r["role"], "content": r["content"]} for r in result.data[-MAX_CHAT_HISTORY_PAIRS * 2 :]]

    def add_message(self, conversation_id: str, role: str, content: str, status: str = "complete") -> None:
        """Store a message using atomic function that handles pair-trimming in one transaction."""
        supabase = get_supabase_client()
        supabase.rpc(
            "chat_append_message",
            {
                "p_conversation_id": conversation_id,
                "p_role": role,
                "p_content": content,
                "p_status": status,
                "p_max_pairs": MAX_CHAT_HISTORY_PAIRS,
            },
        ).execute()

    def get_history_as_prompt(self, conversation_id: str) -> str:
        """Load history formatted for prompt injection: 'User: ...\nAssistant: ...' lines."""
        messages = self.get_history(conversation_id)
        return "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in messages)


chat_context_repository = ChatContextRepository()
