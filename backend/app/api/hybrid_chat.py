"""Hybrid Chat API endpoint - Routes between Ollama and Claude."""

import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.hybrid_ai_service import hybrid_ai_service

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
    use_tools: bool = False
) -> AsyncGenerator[str, None]:
    """
    Generate SSE-formatted stream from Hybrid AI (Ollama or Claude).

    Args:
        user_message: The user's message
        use_tools: Whether to enable tool calling (forces Claude)

    Yields:
        SSE-formatted data chunks
    """
    try:
        # Route and stream from appropriate model
        async for chunk in hybrid_ai_service.stream_response(user_message, use_tools):
            # Format as SSE data
            yield f"data: {chunk}\n\n"

    except Exception as e:
        logger.error(f"Hybrid chat error: {e}")
        yield f"data: Error: {str(e)}\n\n"


@router.post("/api/hybrid-chat")
async def hybrid_chat(request: HybridChatRequest):
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
        async for chunk in generate_hybrid_sse_stream(
            request.message,
            request.use_tools
        ):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
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
        "routing_distribution": {
            "tier1_local": 0.0,
            "tier2_cloud": 0.0
        },
        "note": "Stats tracking not yet implemented"
    }
