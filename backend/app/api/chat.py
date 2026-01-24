"""Chat API endpoint with Server-Sent Events streaming."""

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.claude_service import claude_service
from app.services.command_executor import command_executor
from app.services.work_order_service import work_order_service
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str
    conversation_id: str | None = None


class ChatMetadata(BaseModel):
    """Metadata about chat response."""

    response_type: str  # "ai_response", "command_executed", "work_order_created"
    command_result: dict | None = None
    work_order: dict | None = None
    citations: list[str] | None = None


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


async def generate_static_sse(message: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE stream for a static (non-streaming) response.

    Args:
        message: The complete message to send

    Yields:
        SSE-formatted message followed by completion sentinel
    """
    yield f"data: {message}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Chat with Claude AI using Server-Sent Events streaming.

    The endpoint intelligently routes messages:
    1. Control commands (temperature, lighting, emergency) -> Execute and return result
    2. Work order requests (equipment issues) -> Create work order and return confirmation
    3. General questions -> Query Claude with building context

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
    logger.info(f"Chat request: conversation_id={request.conversation_id}, message={user_message[:50]}...")

    # 1. Check for control commands
    command = command_executor.parse_command(user_message)
    if command:
        logger.info(f"Detected command: {command['type']}")
        result = command_executor.execute_command(command)

        if result.success:
            response_message = f"{result.message}"
        else:
            response_message = f"Command failed: {result.message}"

        return StreamingResponse(
            generate_static_sse(response_message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Response-Type": "command_executed",
            },
        )

    # 2. Check for work order requests
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

    # 3. Regular AI chat with building context
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
    return {
        "configured": claude_service.is_configured(),
        "model": settings.claude_model,
        "features": {
            "control_commands": True,
            "work_orders": True,
            "building_context": True,
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
