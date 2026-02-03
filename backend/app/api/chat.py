"""Chat API endpoint with Server-Sent Events streaming."""

import logging
import os
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.claude_service import claude_service
from app.services.demo_cache import DemoCache
from app.services.work_order_service import work_order_service
from app.services.doc_rag_service import search_documentation, get_doc_rag_system_prompt
from app.services.feature_request_logger import log_chat_query
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str
    conversation_id: str | None = None
    search_docs: bool = True  # Default to documentation RAG mode


class ChatMetadata(BaseModel):
    """Metadata about chat response."""

    response_type: str  # "ai_response", "command_executed", "work_order_created"
    command_result: dict | None = None
    work_order: dict | None = None
    citations: list[str] | None = None


def format_sse_chunk(chunk: str) -> str:
    """
    Format a chunk for SSE transmission, handling newlines properly.

    SSE format requires each line of multi-line content to have its own "data:" prefix.
    If we send "data: hello\\nworld\\n\\n", the client would see:
    - "data: hello" -> extracts "hello"
    - "world" -> doesn't start with "data:" so it gets IGNORED!

    This function handles newlines in chunks by sending each line with its own prefix.
    """
    if '\n' not in chunk:
        # Simple case - no newlines
        return f"data: {chunk}\n\n"

    # Multi-line chunk - send each line with its own data: prefix
    # The SSE spec says multi-line data should use multiple data: lines
    lines = chunk.split('\n')
    sse_lines = []
    for line in lines:
        sse_lines.append(f"data: {line}")
    # Join with \n and add final \n\n separator
    return '\n'.join(sse_lines) + '\n\n'


async def generate_sse_stream(user_message: str, use_tools: bool = True) -> AsyncGenerator[str, None]:
    """
    Generate SSE-formatted stream from Claude response.

    Args:
        user_message: The user's message to send to Claude
        use_tools: Whether to enable tool calling for device control

    Yields:
        SSE-formatted data chunks
    """
    messages = [{"role": "user", "content": user_message}]

    try:
        if use_tools:
            # Use tool-enabled streaming for device control capabilities
            async for chunk in claude_service.stream_response_with_tools(messages):
                # Format as SSE data with proper newline handling
                yield format_sse_chunk(chunk)
        else:
            # Use regular streaming without tools
            async for chunk in claude_service.stream_response(messages):
                # Format as SSE data with proper newline handling
                yield format_sse_chunk(chunk)

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


async def generate_static_sse(message: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE stream for a static (non-streaming) response.

    Args:
        message: The complete message to send

    Yields:
        SSE-formatted message followed by completion sentinel
    """
    # Use format_sse_chunk to properly handle newlines in the message
    yield format_sse_chunk(message)
    yield "data: [DONE]\n\n"


async def generate_docs_sse_stream(user_message: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE-formatted stream for documentation search mode.

    Searches the documentation RAG first, then uses Claude to answer
    based on the retrieved documentation + building context.

    Args:
        user_message: The user's question about SENTINEL documentation

    Yields:
        SSE-formatted data chunks
    """
    try:
        # Search documentation RAG for relevant content
        doc_results = await search_documentation(user_message)

        # Build system prompt with documentation context
        system_prompt = get_doc_rag_system_prompt(doc_results)

        messages = [{"role": "user", "content": user_message}]

        # Stream response with documentation context (no device control tools)
        async for chunk in claude_service.stream_response(
            messages,
            system_prompt=system_prompt,
            include_building_context=True  # Still include building data
        ):
            yield format_sse_chunk(chunk)

        # Send completion sentinel
        yield "data: [DONE]\n\n"

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        yield f"data: Error: {str(e)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Documentation chat error: {e}")
        yield f"data: Error: {str(e)}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Chat with Claude AI using Server-Sent Events streaming.

    The endpoint intelligently routes messages:
    1. Work order requests (equipment issues) -> Create work order and return confirmation
    2. General questions and device control -> Query Claude with building context and tool calling
       - Claude can control devices via list_devices, get_device_details, control_device tools
       - All device controls go through safety validation and are logged to audit trail

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

    user_message = request.message.strip()
    logger.info(f"Chat request: conversation_id={request.conversation_id}, search_docs={request.search_docs}, message={user_message[:50]}...")

    # 1. Documentation search mode takes priority - this is Q&A, not device control
    #    No work order detection or demo cache in docs mode
    if request.search_docs:
        if not claude_service.is_configured():
            raise HTTPException(
                status_code=503,
                detail="Claude AI is not configured. Set ANTHROPIC_API_KEY in environment.",
            )
        logger.info("Documentation search mode enabled")
        # Log query for feature request tracking
        log_chat_query(user_message)
        return StreamingResponse(
            generate_docs_sse_stream(user_message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Response-Type": "ai_response",
                "X-Search-Docs": "true",
            },
        )

    # 2. System chat mode (search_docs=false) - work orders and device control

    # Check for work order requests
    wo_detection = work_order_service.detect_work_order_request(user_message)
    if wo_detection and wo_detection.get("detected"):
        logger.info(f"Detected work order request: {wo_detection}")

        work_order = work_order_service.create_work_order(
            description=user_message,
            equipment_ref=wo_detection.get("equipment_ref"),
            category=wo_detection.get("category", "other"),
            priority=wo_detection.get("priority", "medium"),
        )

        response_message = work_order.format_confirmation()

        return StreamingResponse(
            generate_static_sse(response_message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Response-Type": "work_order_created",
                "X-Work-Order-Id": work_order.id,
            },
        )

    # Check demo cache if DEMO_MODE is enabled
    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
    if demo_mode:
        demo_cache = DemoCache()
        cached_response = demo_cache.get_cached_response(user_message)
        if cached_response:
            logger.info(f"Using cached demo response for query")
            citations = demo_cache.get_citations(user_message)

            async def stream_cached_response() -> AsyncGenerator[str, None]:
                yield format_sse_chunk(cached_response)
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                stream_cached_response(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Response-Type": "ai_response",
                    "X-Demo-Cached": "true",
                },
            )

    if not claude_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Claude AI is not configured. Set ANTHROPIC_API_KEY in environment.",
        )

    return StreamingResponse(
        generate_sse_stream(user_message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Response-Type": "ai_response",
        },
    )


@router.get("/chat/status")
async def chat_status():
    """Check if the chat service is configured and available."""
    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
    return {
        "configured": claude_service.is_configured(),
        "demo_mode": demo_mode,
        "model": settings.claude_model,
        "features": {
            "device_control": True,  # AI can control devices via tool calling
            "work_orders": True,
            "building_context": True,
            "demo_cache": demo_mode,
            "tool_calling": True,  # Claude tool use enabled
            "documentation_search": True,  # RAG-based documentation search
        },
    }


@router.get("/work-orders")
async def list_work_orders(site_id: str | None = None):
    """
    List work orders created through chat.

    Args:
        site_id: Optional site ID to filter by

    Returns:
        List of work orders
    """
    work_orders = work_order_service.get_work_orders(site_id)
    return {
        "total": len(work_orders),
        "work_orders": [wo.to_dict() for wo in work_orders],
    }
