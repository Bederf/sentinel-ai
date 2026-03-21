"""Hybrid Chat API endpoint - Routes between Ollama and Claude."""

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config.settings import SENTINEL_BOT_TECH_DEFAULT_CLASS
from app.middleware.auth_middleware import get_current_auth
from app.security.sse_buffer import SecureSSEBuffer
from app.services.model_gateway import model_gateway

logger = logging.getLogger(__name__)

router = APIRouter()


class HybridChatRequest(BaseModel):
    """Request model for hybrid chat endpoint."""

    message: str
    conversation_id: str | None = None
    use_tools: bool = False  # Force tool calling (Claude only)


class ChatMetadata(BaseModel):
    """Metadata about hybrid chat response."""

    response_type: str  # "ollama_local" or "claude_cloud"
    provider: str
    model: str
    estimated_cost: float
    routing_reason: str


async def generate_hybrid_sse_stream(
    user_message: str,
    use_tools: bool = False,
    data_subject_id: str | None = None,
    user_role: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE-formatted stream from Hybrid AI (Ollama or Claude).

    Args:
        user_message: The user's message
        use_tools: Whether to enable tool calling (forces Claude)
        user_role: Current user role (passed to output filter for PII gating)

    Yields:
        SSE-formatted data chunks
    """
    buffer = SecureSSEBuffer(user_role=user_role)

    try:
        # Route through model_gateway using the tech bot class
        messages = [{"role": "user", "content": user_message}]
        stream_gen = await model_gateway.call(
            task_class=SENTINEL_BOT_TECH_DEFAULT_CLASS,
            messages=messages,
            stream=True,
        )
        async for chunk in stream_gen:
            safe_text = buffer.add_token(chunk)
            if safe_text is not None:
                yield f"data: {safe_text}\n\n"
            if buffer.killed:
                break

        # Flush remaining buffer content
        final = buffer.finalize()
        if final:
            yield f"data: {final}\n\n"

    except Exception as e:
        logger.error("Hybrid chat stream error: %s", e, exc_info=True)
        yield "data: An error occurred processing your request.\n\n"


@router.post("/api/hybrid-chat")
async def hybrid_chat(request: HybridChatRequest, http_request: Request):
    """
    Hybrid chat endpoint that routes between Ollama (local) and Claude (cloud).

    Simple queries → Ollama (FREE, fast)
    Complex queries → Claude (paid, smart)

    Args:
        request: Chat request with message and optional tool calling

    Returns:
        StreamingResponse with SSE stream
    """

    async def stream():
        auth_ctx = get_current_auth(http_request)
        data_subject_id = getattr(auth_ctx, "email", None) or getattr(auth_ctx, "user_id", None)
        user_role = getattr(auth_ctx, "role", None)
        async for chunk in generate_hybrid_sse_stream(
            request.message,
            request.use_tools,
            data_subject_id=data_subject_id,
            user_role=user_role,
        ):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/hybrid-stats")
async def get_hybrid_stats():
    """
    Get statistics about hybrid AI routing.

    Returns:
        Statistics about model usage and cost savings
    """
    # This would be implemented with actual stats tracking
    # For now, return placeholder data
    return {
        "total_queries": 0,
        "ollama_queries": 0,
        "claude_queries": 0,
        "total_cost": 0.0,
        "savings_vs_all_claude": 0.0,
        "routing_distribution": {"tier1_local": 0.0, "tier2_cloud": 0.0},
        "note": "Stats tracking not yet implemented",
    }
