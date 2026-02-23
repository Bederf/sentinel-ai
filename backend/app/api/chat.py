"""Chat API endpoint with Server-Sent Events streaming."""

import logging
import os
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request as FastAPIRequest
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.claude_service import claude_service
from app.services.demo_cache import DemoCache
from app.services.work_order_service import work_order_service
from app.services.doc_rag_service import search_documentation, get_doc_rag_system_prompt
from app.services.feature_request_logger import log_chat_query
from app.services.prompt_injection_guard import check_query_safety
from app.config.settings import settings
from app.middleware.auth_middleware import get_current_auth
from app.utils.ai_provenance import get_claude_provenance, provenance_headers

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str
    conversation_id: str | None = None
    search_docs: bool = True  # Default to documentation RAG mode
    site_id: str | None = None  # Selected building/site for context


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
    if "\n" not in chunk:
        # Simple case - no newlines
        return f"data: {chunk}\n\n"

    # Multi-line chunk - send each line with its own data: prefix
    # The SSE spec says multi-line data should use multiple data: lines
    lines = chunk.split("\n")
    sse_lines = []
    for line in lines:
        sse_lines.append(f"data: {line}")
    # Join with \n and add final \n\n separator
    return "\n".join(sse_lines) + "\n\n"


async def generate_sse_stream(
    user_message: str,
    use_tools: bool = True,
    site_id: str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE-formatted stream from Claude response.

    Args:
        user_message: The user's message to send to Claude
        use_tools: Whether to enable tool calling for device control
        site_id: Selected building/site for context (e.g., "site-002")

    Yields:
        SSE-formatted data chunks
    """
    # Add site context to the message if provided
    if site_id:
        context_prefix = f"[Context: User is asking about building/site '{site_id}']\n\n"
        message_with_context = context_prefix + user_message
    else:
        message_with_context = user_message

    messages = [{"role": "user", "content": message_with_context}]

    try:
        if use_tools:
            # Use tool-enabled streaming for device control capabilities
            async for chunk in claude_service.stream_response_with_tools(
                messages,
                site_id=site_id,
                user_email=user_email,
                user_role=user_role,
            ):
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


async def generate_docs_sse_stream(user_message: str, site_id: str | None = None) -> AsyncGenerator[str, None]:
    """
    Generate SSE-formatted stream for documentation search mode.

    Searches the documentation RAG first, then uses Claude to answer
    based on the retrieved documentation + building context.

    Args:
        user_message: The user's question about SENTINEL documentation
        site_id: Selected building/site for context (e.g., "site-002")

    Yields:
        SSE-formatted data chunks
    """
    try:
        # Convert site_id (building code) to building_id (UUID) for RAG filtering
        building_id = None
        if site_id:
            try:
                from app.database.supabase_client import get_supabase_client

                client = get_supabase_client()
                result = client.table("buildings").select("id").eq("code", site_id).single().execute()
                building_id = result.data["id"] if result.data else None
            except Exception as e:
                logger.warning(f"Failed to resolve building code '{site_id}' to UUID: {e}")
                # Continue without building filter

        # Search documentation RAG for relevant content (with optional building scope)
        doc_results = await search_documentation(user_message, building_id=building_id)

        # Build system prompt with documentation context
        system_prompt = get_doc_rag_system_prompt(doc_results)

        # Add site context to the message if provided
        if site_id:
            context_prefix = f"[Context: User is asking about building/site '{site_id}']\n\n"
            message_with_context = context_prefix + user_message
        else:
            message_with_context = user_message

        messages = [{"role": "user", "content": message_with_context}]

        # Stream response with documentation context (no device control tools)
        async for chunk in claude_service.stream_response(
            messages,
            system_prompt=system_prompt,
            include_building_context=True,  # Still include building data
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
@limiter.limit("20/minute")
async def chat(request: FastAPIRequest, chat_request: ChatRequest) -> StreamingResponse:
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
    if not chat_request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_message = chat_request.message.strip()

    # Security: Check for prompt injection attempts
    is_safe, rejection_reason, injections = check_query_safety(user_message)
    if not is_safe:
        logger.warning(f"Prompt injection blocked: {injections[0].pattern} - {injections[0].description}")
        logger.warning(f"Query: {user_message[:100]}...")
        raise HTTPException(
            status_code=400,
            detail={"error": "Security concern", "message": rejection_reason, "code": "PROMPT_INJECTION_DETECTED"},
        )

    logger.info(
        f"Chat request: conversation_id={chat_request.conversation_id}, "
        f"search_docs={chat_request.search_docs}, site_id={chat_request.site_id}, "
        f"message={user_message[:50]}..."
    )

    # 1. Documentation search mode takes priority - this is Q&A, not device control
    #    No work order detection or demo cache in docs mode
    if chat_request.search_docs:
        if not claude_service.is_configured():
            raise HTTPException(
                status_code=503,
                detail="Claude AI is not configured. Set ANTHROPIC_API_KEY in environment.",
            )
        logger.info(f"Documentation search mode enabled, site_id={chat_request.site_id}")
        # Log query for feature request tracking
        log_chat_query(user_message)
        return StreamingResponse(
            generate_docs_sse_stream(user_message, chat_request.site_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Response-Type": "ai_response",
                "X-Search-Docs": "true",
                **provenance_headers(get_claude_provenance()),
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
                "X-AI-Assisted": "true",
                **provenance_headers(get_claude_provenance()),
            },
        )

    # Check demo cache if DEMO_MODE is enabled
    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
    if demo_mode:
        demo_cache = DemoCache()
        cached_response = demo_cache.get_cached_response(user_message)
        if cached_response:
            logger.info("Using cached demo response for query")
            _citations = demo_cache.get_citations(user_message)

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
                    **provenance_headers(get_claude_provenance()),
                },
            )

    if not claude_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Claude AI is not configured. Set ANTHROPIC_API_KEY in environment.",
        )

    auth_ctx = get_current_auth(request)
    return StreamingResponse(
        generate_sse_stream(
            user_message,
            use_tools=True,
            site_id=chat_request.site_id,
            user_email=getattr(auth_ctx, "email", None),
            user_role=getattr(auth_ctx, "role", None),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Response-Type": "ai_response",
            **provenance_headers(get_claude_provenance()),
        },
    )


@router.get("/chat/status")
async def chat_status():
    """Check if the chat service is configured and available."""
    from app.services.tts_service import get_tts_service

    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
    tts = get_tts_service()
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
            "tts": tts.is_configured(),  # Voice chat TTS
        },
    }


class TTSRequest(BaseModel):
    """Request model for text-to-speech endpoint."""

    text: str


@router.post("/chat/tts")
@limiter.limit("10/minute")
async def chat_tts(request: FastAPIRequest, tts_request: TTSRequest):
    """Convert chat response text to speech audio.

    Summarizes the text to 1-2 sentences, then synthesizes speech via ElevenLabs.
    Returns MP3 audio bytes.

    Rate limited to 10 requests per minute.
    """
    from app.services.tts_service import get_tts_service

    tts = get_tts_service()

    if not tts.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Text-to-speech is not configured. Set ELEVENLABS_API_KEY and ELEVENLABS_TTS_ENABLED=true.",
        )

    text = tts_request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    audio = await tts.text_to_speech(text)
    if audio is None:
        raise HTTPException(status_code=502, detail="Speech synthesis failed")

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=response.mp3"},
    )


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
