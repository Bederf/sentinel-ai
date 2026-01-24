"""Chat API endpoint with Server-Sent Events streaming."""

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.claude_service import claude_service
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str
    conversation_id: str | None = None


async def generate_sse_stream(user_message: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE-formatted stream from Claude response.

    Args:
        user_message: The user's message to send to Claude

    Yields:
        SSE-formatted data chunks
    """
    messages = [{"role": "user", "content": user_message}]

    try:
        async for chunk in claude_service.stream_response(messages):
            # Format as SSE data
            yield f"data: {chunk}\n\n"

        # Send completion sentinel
        yield "data: [DONE]\n\n"

    except ValueError as e:
        # Configuration error (API key missing)
        logger.error(f"Configuration error: {e}")
        yield f"data: Error: {str(e)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        # API or unexpected errors
        logger.error(f"Chat error: {e}")
        yield f"data: Error: {str(e)}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Chat with Claude AI using Server-Sent Events streaming.

    The response is streamed as SSE with:
    - `data: <text chunk>` for each piece of the response
    - `data: [DONE]` as the final sentinel

    Args:
        request: ChatRequest with message and optional conversation_id

    Returns:
        StreamingResponse with SSE content type
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if not claude_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Claude AI is not configured. Set ANTHROPIC_API_KEY in environment.",
        )

    logger.info(f"Chat request: conversation_id={request.conversation_id}")

    return StreamingResponse(
        generate_sse_stream(request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/chat/status")
async def chat_status():
    """Check if the chat service is configured and available."""
    return {
        "configured": claude_service.is_configured(),
        "model": settings.claude_model,
    }
