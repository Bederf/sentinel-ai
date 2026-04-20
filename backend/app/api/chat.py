"""Chat API endpoint with Server-Sent Events streaming."""

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config.settings import SENTINEL_BOT_DEFAULT_CLASS, settings
from app.middleware.auth_middleware import get_current_auth
from app.models.auth import AuthContext
from app.repositories.chat_context_repository import chat_context_repository
from app.security.constants import MAX_CHAT_MESSAGE_LENGTH
from app.security.pipeline import prompt_guard, require_role
from app.security.sse_buffer import SecureSSEBuffer
from app.services import slash_command_router
from app.services.ai_interfaces import get_chat_tools
from app.services.claude_service import claude_service
from app.services.feature_request_logger import log_chat_query
from app.services.hybrid_ai_service import hybrid_ai_service
from app.services.model_gateway import model_gateway
from app.services.openai_service import openai_service
from app.services.popia_consent_guard import should_allow_cloud_processing
from app.services.site_ai_policy_service import get_site_ai_policy
from app.services.work_order_service import work_order_service
from app.utils.ai_provenance import get_cloud_llm_provenance, get_local_llm_provenance, provenance_headers

# Track Claude credit exhaustion so we skip it on subsequent requests (tools path only)
_claude_credits_exhausted = False

# In-memory context window: conversation_id -> list of message dicts
# Accumulates conversation history per session so Claude sees prior messages.

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., max_length=MAX_CHAT_MESSAGE_LENGTH)
    conversation_id: str | None = Field(
        None,
        description="Session ID for conversation continuity. "
        "If provided, prior messages are loaded and new messages stored for context.",
    )
    search_docs: bool = False  # Deprecated: doc search is now a tool, not a mode
    site_id: str | None = Field(None, pattern=r"^site-\d{3}$")  # Selected building/site
    include_system_docs: bool = Field(
        False,
        description="Include SENTINEL platform documentation in RAG retrieval. "
        "Off by default to avoid polluting operational answers.",
    )


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


def get_chat_provenance_headers(data_subject_id: str | None = None) -> dict[str, str]:
    """Return provenance headers for current chat execution mode."""
    if hybrid_ai_service.is_local_ai_only_mode() or not should_allow_cloud_processing(data_subject_id):
        return provenance_headers(get_local_llm_provenance(model="phi3:mini"))
    return provenance_headers(
        get_cloud_llm_provenance(
            provider=hybrid_ai_service.get_active_cloud_provider(),
            model=hybrid_ai_service.get_active_cloud_model(),
        )
    )


# Keywords that signal a knowledge/documentation query (not live building data).
# When detected, we pre-fetch doc search results and inject them into the
# first Claude call — saving one full API round-trip (~13s).
_KNOWLEDGE_KEYWORDS = {
    "compliance",
    "standard",
    "regulation",
    "procedure",
    "manual",
    "documentation",
    "guide",
    "policy",
    "protocol",
    "certification",
    "how does sentinel",
    "what is sentinel",
    "what can you do",
    "troubleshoot",
    "fault code",
    "maintenance procedure",
    "best practice",
    "specification",
    "requirement",
}


def _is_knowledge_query(message: str) -> bool:
    """Detect if a query is about documentation/knowledge (not live data)."""
    lower = message.lower()
    return any(kw in lower for kw in _KNOWLEDGE_KEYWORDS)


# Keywords that signal a platform/architecture question — suggest enabling system docs.
# Covers SENTINEL platform docs AND IT/risk/bank/FSR/security vocabulary.
# When detected: enables search_system_documents + injects Bombard-with-Facts prompt.
_PLATFORM_DOC_KEYWORDS = {
    # SENTINEL platform docs
    "how do i upload",
    "how does sentinel",
    "how does the security",
    "how does onboarding",
    "compliance controls",
    "platform architecture",
    "security architecture",
    "system design",
    "building upload",
    "configuration guide",
    "onboarding",
    "how to configure",
    "how to set up",
    "what compliance",
    "audit framework",
    "data privacy",
    "deployment guide",
    # IT / Risk / Compliance / FSR / Bank vocabulary
    "fsr",
    "fsr assessment",
    "fsr questionnaire",
    "financial sector risk",
    "firstrand",
    "bank network",
    "banking network",
    "network architecture",
    "network security",
    "network design",
    "iso 27001",
    "iso 42001",
    "iso 42001 ai",
    "iso 42001 controls",
    "nist",
    "nist ai",
    "nist ai rmf",
    "mitre att",
    "mitre att&ck",
    "mitre att&ck framework",
    "owasp",
    "owasp top",
    "owasp zap",
    "owasp testing",
    "siem",
    "siem tool",
    "splunk",
    "wazuh",
    "elastic siem",
    "penetration test",
    "pen test",
    "pentest",
    "vulnerability scan",
    "vulnerability assessment",
    "cve",
    "cvss",
    "zero day",
    "zero-day",
    "security audit",
    "security assessment",
    "security review",
    "threat model",
    "threat modelling",
    "attack surface",
    "threat intelligence",
    "ransomware",
    "phishing",
    "social engineering",
    "ddos",
    "firewall",
    "next-gen firewall",
    "ngfw",
    "web app firewall",
    "waf",
    "waf rules",
    "mfa",
    "multi-factor",
    "2fa",
    "totp",
    "sso",
    "saml",
    "oauth",
    "identity provider",
    "idp",
    "privileged access",
    "pam",
    "just-in-time access",
    "jit access",
    "least privilege",
    "zero trust",
    "zero trust architecture",
    "microsegmentation",
    "encryption",
    "encrypt",
    "tls",
    "ssl",
    "certificate",
    "pki",
    "key management",
    "secret management",
    "hashiCorp vault",
    "vault secrets",
    "popia",
    "po pia",
    "protection of personal",
    "gdpr",
    "data protection",
    "cross-border",
    "cross border data",
    "privacy impact",
    "data classification",
    "data sovereignty",
    "eu ai act",
    "eu ai",
    "ai act compliance",
    "ai risk",
    "ai governance",
    "ai oversight",
    "ai explainability",
    "ai audit",
    "ai transparency",
    "ai incident",
    "incident response",
    "ir plan",
    "incident response plan",
    "soc",
    "security operations",
    "security ops",
    "threat hunting",
    "endpoint detection",
    "edr",
    "xdr",
    "antivirus",
    "malware",
    "back-up",
    "backup",
    "dr plan",
    "disaster recovery",
    "bcp",
    "business continuity",
    "bcdr",
    "backup and recovery",
    "rto",
    "rpo",
    "recovery time",
    "recovery point",
    "sla",
    "availability sla",
    "uptime",
    "simbiot",
    "sim biot",
    "bacnet",
    "dali-2",
    "dali2",
    "protocol",
    "building automation",
    "standards",
    "audit trail",
    "audit log",
    "log management",
    "sast",
    "dast",
    "static analysis",
    "dynamic analysis",
    "code review",
    "secure coding",
    "supply chain",
    "supply chain security",
    "sbom",
    "software bill",
    "third-party",
    "third party risk",
    "vendor risk",
    "patch management",
    "patching",
    "security patch",
    "common vulnerability",
    " hardening",
    "security hardening",
    "baseline",
    "cis benchmark",
    "disa stig",
    "stig",
    "pen test report",
    "penetration testing report",
    "security report",
    "audit report",
    "compliance report",
    "controls",
    "control effectiveness",
    "control testing",
    "effectiveness review",
    "maturity model",
    "capability maturity",
    "cmmi",
    "risk register",
    "risk matrix",
    "risk assessment",
    "risk treatment",
    "residual risk",
    "risk appetite",
    "risk tolerance",
    "it risk",
    "cyber risk",
    "operational risk",
    "information security",
    "infosec",
    "cybersecurity",
    "cyber security",
    "cyber resilience",
    "data breach",
    "breach notification",
    "breach response",
    "forensics",
    "digital forensics",
}


def _is_platform_doc_query(message: str) -> bool:
    """Detect if a query is about SENTINEL platform docs (architecture, onboarding, etc.)."""
    lower = message.lower()
    return any(kw in lower for kw in _PLATFORM_DOC_KEYWORDS)


_NO_RESULTS_SENTINEL = "__NO_RESULTS__"


async def _prefetch_doc_results(query: str) -> str | None:
    """Run doc search and format results as context for injection.

    Returns:
        _NO_RESULTS_SENTINEL if search ran but found nothing (caller can fast-path).
        A context string with results if docs were found.
        None if search failed (caller should fall through to normal path).
    """
    try:
        from app.services.chat_tools import search_documents

        result = await search_documents(query=query, n_results=5)
        if not result.get("success") or not result.get("results"):
            return _NO_RESULTS_SENTINEL
        docs = result["results"]
        lines = [f'[Pre-fetched documentation search results for: "{query}"]']
        for i, doc in enumerate(docs, 1):
            title = doc.get("title", "Unknown")
            content = doc.get("content", "")[:1200]
            relevance = doc.get("relevance", 0)
            lines.append(f"\n--- Result {i} (relevance: {relevance}) ---\n{title}\n{content}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Doc pre-fetch failed: {e}")
        return None


async def generate_sse_stream(
    user_message: str,
    use_tools: bool = True,
    site_id: str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
    data_subject_id: str | None = None,
    include_system_docs: bool = False,
    conversation_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE-formatted stream from Claude response.

    For knowledge queries (compliance, procedures, documentation), pre-fetches
    doc search results and injects them into the first Claude call — saving
    one full API round-trip (~13s).

    Conversation history is stored in the database per conversation_id, so Claude
    sees all prior messages in the same session for contextual memory.

    Args:
        user_message: The user's message to send to Claude
        use_tools: Whether to enable tool calling for device control
        site_id: Selected building/site for context (e.g., "site-002")
        conversation_id: Session ID for conversation continuity. If provided, prior
            messages are loaded from DB and new messages stored for context.

    Yields:
        SSE-formatted data chunks
    """
    # Add site context to the message if provided
    if site_id:
        context_prefix = f"[Context: User is asking about building/site '{site_id}']\n\n"
        message_with_context = context_prefix + user_message
    else:
        message_with_context = user_message

    # Build messages list — prepend prior conversation history if available
    messages = [{"role": "user", "content": message_with_context}]
    if conversation_id:
        try:
            prior = chat_context_repository.get_history(conversation_id)
            messages = prior + messages
        except Exception:
            pass  # Never fail chat due to storage errors

    # Suggest enabling platform documentation when relevant
    if not include_system_docs and _is_platform_doc_query(user_message):
        yield format_sse_chunk(
            "💡 This question may require SENTINEL platform documentation. "
            "Enable **Include SENTINEL platform documentation** toggle above for better results.\n\n---\n\n"
        )

    # Pre-fetch doc search for knowledge queries to avoid an extra Claude round-trip.
    # If search returns no results, fast-path with a static answer (skip Claude entirely).
    knowledge_fast_path = False
    if use_tools and _is_knowledge_query(user_message):
        doc_context = await _prefetch_doc_results(user_message)
        if doc_context == _NO_RESULTS_SENTINEL:
            knowledge_fast_path = True
        elif doc_context:
            # Inject docs into the last user message (most recent context)
            messages[-1] = {"role": "user", "content": f"{doc_context}\n\n---\n\n{message_with_context}"}

    if knowledge_fast_path:
        response_text = (
            "I don't have documentation about that topic in the system. "
            "You may need to upload the relevant documents or check with your facility manager."
        )
        yield format_sse_chunk(response_text)
        if conversation_id:
            try:
                chat_context_repository.add_message(conversation_id, "assistant", response_text)
            except Exception:
                pass
        yield "data: [DONE]\n\n"
        return

    # Accumulator for storing the complete assistant response
    assistant_parts: list[str] = []

    # Store user message optimistically (before stream) — if stream fails, partial handler saves assistant
    if conversation_id:
        try:
            chat_context_repository.add_message(conversation_id, "user", message_with_context)
        except Exception:
            pass

    # POPIA cross-border routing guard: fall back to local AI when cloud
    # processing consent is missing for the data subject.
    # Also respect per-site chat_local_ai_only policy.
    site_policy = get_site_ai_policy(site_id) if site_id else {}
    chat_local_only = bool(site_policy.get("chat_local_ai_only", False))
    use_local_fallback = chat_local_only or (
        not hybrid_ai_service.is_local_ai_only_mode() and not should_allow_cloud_processing(data_subject_id)
    )

    # Secure SSE buffer: filters output through the 5-stage pipeline
    buffer = SecureSSEBuffer(user_role=user_role)

    # Get tools if enabled (Minimax accepts OpenAI-format tools but won't use them)
    available_tools = None
    if use_tools:
        try:
            available_tools = get_chat_tools(site_id, user_email=user_email, user_role=user_role)
        except Exception:
            pass

    try:
        if use_local_fallback:
            async for chunk in hybrid_ai_service.stream_response(
                message_with_context,
                use_tools=False,
                data_subject_id=data_subject_id,
                site_id=site_id,
            ):
                safe_text = buffer.add_token(chunk)
                if safe_text is not None:
                    assistant_parts.append(safe_text)
                    yield format_sse_chunk(safe_text)
                if buffer.killed:
                    break
        else:
            # Route all LLM calls through model_gateway (Minimax for everything in cloud_dev/api_prod)
            try:
                stream_gen = await model_gateway.call(
                    task_class=SENTINEL_BOT_DEFAULT_CLASS,
                    messages=messages,
                    stream=True,
                    tools=available_tools,
                )
                async for chunk in stream_gen:
                    safe_text = buffer.add_token(chunk)
                    if safe_text is not None:
                        assistant_parts.append(safe_text)
                        yield format_sse_chunk(safe_text)
                    if buffer.killed:
                        break
            except Exception as gw_err:
                logger.error("Gateway chat stream error: %s", gw_err)
                msg = "AI services are temporarily unavailable. Please try again shortly."
                assistant_parts.append(msg)
                yield format_sse_chunk(msg)

        # Flush remaining buffer content
        final = buffer.finalize()
        if final:
            assistant_parts.append(final)
            yield format_sse_chunk(final)

        assistant_text = "".join(assistant_parts)

        # Store assistant response (user message already stored before stream)
        if conversation_id:
            try:
                chat_context_repository.add_message(conversation_id, "assistant", assistant_text)
            except Exception:
                pass

        # Send completion sentinel
        yield "data: [DONE]\n\n"

    except ValueError as e:
        # Configuration error (API key missing) — log details, send generic message
        logger.error("Configuration error in chat stream: %s", e, exc_info=True)
        yield format_sse_chunk("An error occurred processing your request.")
        yield "data: [DONE]\n\n"

    except Exception as e:
        # API or unexpected errors — save partial response if we have one
        logger.error("Chat stream error: %s", e, exc_info=True)
        if conversation_id and assistant_parts:
            try:
                chat_context_repository.add_message(
                    conversation_id, "assistant", "".join(assistant_parts), status="partial"
                )
            except Exception:
                pass
        yield format_sse_chunk("An error occurred processing your request.")
        yield "data: [DONE]\n\n"
        yield format_sse_chunk("An error occurred processing your request.")
        yield "data: [DONE]\n\n"

    except Exception as e:
        # API or unexpected errors — never expose str(e) to client
        logger.error("Chat stream error: %s", e, exc_info=True)
        yield format_sse_chunk("An error occurred processing your request.")
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


@router.post("/chat", tags=["llm_touching"])
@limiter.limit("20/minute")
async def chat(
    request: FastAPIRequest,
    chat_request: ChatRequest,
    auth: AuthContext = Depends(require_role(1)),
    guarded_message: str = Depends(prompt_guard(field="message", source="direct")),
) -> StreamingResponse:
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

    # Use guarded (possibly rewritten) message from prompt_guard dependency.
    # The old check_query_safety call is superseded by the new scoring engine.
    user_message = guarded_message.strip() if guarded_message else chat_request.message.strip()

    # --- Slash command interception (no AI needed) ---
    parsed_cmd = slash_command_router.parse(user_message)
    if parsed_cmd:
        command, equipment_code, extra_text = parsed_cmd
        auth_ctx = get_current_auth(request)
        user_email = getattr(auth_ctx, "email", None)
        logger.info("Slash command: /%s_%s (user=%s)", command, equipment_code, user_email)
        result = await slash_command_router.execute(command, equipment_code, extra_text, user_email)
        return StreamingResponse(
            generate_static_sse(result.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Response-Type": "command_executed",
            },
        )

    logger.info(
        f"Chat request: conversation_id={chat_request.conversation_id}, "
        f"search_docs={chat_request.search_docs}, site_id={chat_request.site_id}, "
        f"message={user_message[:50]}..."
    )
    auth_ctx = get_current_auth(request)
    user_email = getattr(auth_ctx, "email", None)
    data_subject_id = user_email or getattr(auth_ctx, "user_id", None)

    # Doc search is now a tool available in all chat modes (no separate docs-only path).
    # Log query for feature tracking
    log_chat_query(user_message)

    # Read per-site AI policy
    site_policy = get_site_ai_policy(chat_request.site_id) if chat_request.site_id else {}

    # When Claude tools are available, let Claude handle work orders
    # (better UX: confirms details, looks up equipment, validates).
    # Only fall back to direct detection when tools are not available.
    # Tools are enabled in api mode when Claude is configured.
    try:
        _mode, _provider, _model = model_gateway._resolve(SENTINEL_BOT_DEFAULT_CLASS)
        tools_enabled = _mode == "api" and _provider == "anthropic" and claude_service.is_configured()
    except Exception:
        tools_enabled = claude_service.is_configured() or openai_service.is_configured()
    # Respect per-site allow_tool_calling policy (default True if not set)
    tools_enabled = tools_enabled and bool(site_policy.get("allow_tool_calling", True))

    if not tools_enabled:
        wo_detection = work_order_service.detect_work_order_request(user_message)
        if wo_detection and wo_detection.get("detected"):
            logger.info(f"Detected work order request (no-tools fallback): {wo_detection}")

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
                    **get_chat_provenance_headers(data_subject_id),
                },
            )

    return StreamingResponse(
        generate_sse_stream(
            user_message,
            use_tools=tools_enabled,
            site_id=chat_request.site_id,
            user_email=user_email,
            user_role=getattr(auth_ctx, "role", None),
            data_subject_id=data_subject_id,
            include_system_docs=chat_request.include_system_docs,
            conversation_id=chat_request.conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Response-Type": "ai_response",
            **get_chat_provenance_headers(data_subject_id),
        },
    )


@router.get("/chat/status")
async def chat_status():
    """Check if the chat service is configured and available."""
    from app.services.tts_service import get_tts_service

    tts = get_tts_service()
    local_mode = hybrid_ai_service.is_local_ai_only_mode()
    cloud_provider = hybrid_ai_service.get_active_cloud_provider()
    configured = local_mode or hybrid_ai_service.is_cloud_configured()
    active_model = "phi3:mini (local-only)" if local_mode else hybrid_ai_service.get_active_cloud_model()
    tools_enabled = cloud_provider == "anthropic"

    return {
        "configured": configured,
        "model": active_model,
        "local_ai_only": local_mode,
        "cloud_provider": "sentinel-local" if local_mode else cloud_provider,
        "features": {
            "device_control": tools_enabled,  # Tool-based control is Claude-only
            "work_orders": True,
            "site_context": True,
            "demo_cache": settings.demo_mode,
            "tool_calling": tools_enabled,
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


# ---------------------------------------------------------------------------
# Voice summary — summarize AI response then speak it
# ---------------------------------------------------------------------------


class VoiceSummaryRequest(BaseModel):
    """Request model for summarised voice output."""

    text: str = Field(..., max_length=8000)


def _strip_markdown_for_speech(text: str) -> str:
    """Remove markdown formatting to get plain text for summarization."""
    import re

    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"^\s*>\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\|[^\n]+\|", "", text)
    text = re.sub(r"^\s*[-:|]+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


async def _summarize_for_voice(text: str) -> str:
    """Summarize text into 1-2 natural sentences for spoken output using Claude Haiku."""
    import re

    plain = _strip_markdown_for_speech(text)
    if len(plain) <= 350:
        match = re.search(r"^(.{0,350}[.!?])\s", plain)
        return match.group(1) if match else plain[:350]

    try:
        from anthropic import Anthropic

        from app.config.settings import settings

        if settings.anthropic_api_key:
            client = Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model="claude-3-haiku-20250707",
                max_tokens=100,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "You are a voice assistant. Convert this AI response into "
                            "1-2 short, natural sentences that sound good when spoken aloud. "
                            "Be direct and concise. No formatting. Max 25 words.\n\n"
                            f"Response:\n{plain[:3000]}\n\nSpoken summary:"
                        ),
                    }
                ],
            )
            summary = response.content[0].text.strip().strip('"').strip("'").strip()
            summary = _strip_markdown_for_speech(summary)
            if summary and len(summary) >= 10:
                return summary
    except Exception as e:
        logger.debug("Voice summary via Haiku failed (%s), using extraction fallback", e)

    sentences = re.findall(r"[^.!?]+[.!?]+", plain)
    result = ""
    for s in sentences:
        if len(result) + len(s) <= 350:
            result += s
        else:
            break
    return result.strip() if result else plain[:350]


@router.post("/chat/voice-summary", tags=["llm_touching"])
@limiter.limit("10/minute")
async def chat_voice_summary(request: FastAPIRequest, vs_request: VoiceSummaryRequest):
    """Summarize an AI chat response and return it as spoken audio."""
    import base64

    from app.services.tts_service import get_tts_service

    tts = get_tts_service()
    if not tts.is_configured():
        raise HTTPException(status_code=503, detail="Text-to-speech is not configured.")
    text = vs_request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    summary = await _summarize_for_voice(text)
    if not summary:
        summary = text[:350]
    audio = await tts.text_to_speech(summary)
    if audio is None:
        raise HTTPException(status_code=502, detail="Speech synthesis failed")
    b64 = base64.b64encode(audio).decode("utf-8")
    data_uri = f"data:audio/mpeg;base64,{b64}"
    logger.info("Voice summary: %d chars -> %d chars spoken", len(text), len(summary))
    return {"text": summary, "audio_url": data_uri}


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
