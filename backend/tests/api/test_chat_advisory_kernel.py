"""Tests for advisory-kernel chat feature flag routing."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.agents_kernel.graph_runner import reset_runtime_graph
from app.api.chat import (
    ChatRequest,
    _extract_kernel_observability,
    build_advisory_kernel_headers,
    build_advisory_kernel_response_payload,
    chat,
    format_advisory_kernel_message,
    generate_advisory_kernel_sse,
    is_advisory_kernel_request,
    log_advisory_kernel_response,
    run_advisory_kernel_chat,
)
from app.config.settings import settings
from app.models.auth import AuthContext, SentinelRole


def _build_request() -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "headers": [],
        }
    )
    request.state.auth = AuthContext(
        user_id="user-1",
        role=SentinelRole.OPERATOR,
        auth_method="test",
        source_ip="127.0.0.1",
        email="operator@example.com",
    )
    return request


async def _read_sse_body(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(chunk)
    return "".join(chunks)


def test_feature_flag_routing_disabled(monkeypatch):
    monkeypatch.setattr(settings, "sentinel_advisory_kernel_enabled", False)
    request = ChatRequest(message="Investigate AHU-3", mode="investigation")

    assert is_advisory_kernel_request(request) is False


def test_feature_flag_routing_enabled(monkeypatch):
    monkeypatch.setattr(settings, "sentinel_advisory_kernel_enabled", True)
    request = ChatRequest(message="Investigate AHU-3", mode="investigation")

    assert is_advisory_kernel_request(request) is True


@pytest.mark.asyncio
async def test_run_advisory_kernel_chat_formats_smoke_graph_output(monkeypatch):
    monkeypatch.setattr(settings, "sentinel_advisory_kernel_enabled", True)
    mock_run = AsyncMock(
        return_value={
            "domain_context": {"conversation_id": "conv-123"},
            "evidence_bundle": {
                "hybrid": [{"id": "h1"}],
                "brick": [],
                "docs": [],
                "memory": [],
                "notes": ["documentation_context_empty"],
            },
            "node_trace": [{"event": "node_start"}],
            "messages": [{"role": "user", "content": "Investigate AHU-3"}],
            "output_state": {
                "summary": "Kernel smoke graph completed.",
                "next_step": "Gather evidence before producing a recommendation.",
                "confidence_score": 0.25,
                "request_id": "kernel-test-123",
            },
        }
    )
    monkeypatch.setattr("app.api.chat.run_smoke_graph", mock_run)

    payload, body = await run_advisory_kernel_chat(
        ChatRequest(message="Investigate AHU-3", mode="investigation", conversation_id="conv-123"),
        "Investigate AHU-3",
    )

    assert payload["thread_id"] == "conv-123"
    assert payload["evidence_counts"] == {"hybrid": 1, "brick": 0, "docs": 0, "memory": 0}
    assert payload["domain_context"] == {
        "site_id": None,
        "equipment_id": None,
        "zone": None,
        "time_range": None,
    }
    assert "Kernel smoke graph completed." in body
    assert "Confidence: 0.25" in body
    assert "Evidence: hybrid=1, brick=0, docs=0, memory=0" in body
    assert "kernel-test-123" in body


@pytest.mark.asyncio
async def test_generate_advisory_kernel_sse_emits_metadata_then_output():
    payload = {
        "mode": "investigation",
        "status": "completed",
        "thread_id": "conv-123",
        "domain_context": {
            "site_id": "site-002",
            "equipment_id": "S002-AHU-L2-003",
            "zone": None,
            "time_range": {"relative": "last 24 hours"},
        },
        "summary": "Summary text",
        "next_step": "Next step text",
        "confidence_score": 0.45,
        "request_id": "kernel-abc",
        "evidence_counts": {"hybrid": 1, "brick": 0, "docs": 1, "memory": 0},
        "evidence_notes": ["documentation_context_empty"],
        "trace_count": 2,
        "message_count": 2,
        "observability": {
            "router_name": "ByConfidenceModelRouter",
            "selected_model": "phi3:mini",
        },
    }

    chunks = []
    async for chunk in generate_advisory_kernel_sse(payload, "kernel output"):
        chunks.append(chunk)
    body = "".join(chunks)

    assert "event: advisory_kernel_metadata" in body
    assert '"thread_id": "conv-123"' in body
    assert '"site_id": "site-002"' in body
    assert '"equipment_id": "S002-AHU-L2-003"' in body
    assert "event: advisory_kernel_output" in body
    assert "data: kernel output" in body
    assert "data: [DONE]" in body


def test_build_advisory_kernel_response_payload_uses_thread_id():
    payload = build_advisory_kernel_response_payload(
        ChatRequest(message="Investigate", mode="investigation", conversation_id="conv-123"),
        {
            "domain_context": {
                "conversation_id": "conv-123",
                "site_id": "site-002",
                "equipment_id": "S002-AHU-L2-003",
                "time_range": {"relative": "last 24 hours"},
            },
            "evidence_bundle": {
                "hybrid": [{"id": "h1"}],
                "brick": [],
                "docs": [{"id": "d1"}],
                "memory": [],
                "notes": ["documentation_context_empty"],
            },
            "node_trace": [
                {"event": "node_start"},
                {
                    "event": "node_end",
                    "metadata": {
                        "router_name": "ByConfidenceModelRouter",
                        "selected_model": "phi3:mini",
                        "selected_provider": "ollama",
                        "selected_task_class": "light",
                        "routing_reason": "default_lightweight_local_path",
                        "latency_ms": 12.5,
                    },
                },
            ],
            "messages": [{"role": "user"}, {"role": "assistant"}],
            "output_state": {
                "status": "completed",
                "summary": "Summary text",
                "next_step": "Next step text",
                "confidence_score": 0.45,
                "request_id": "kernel-abc",
            },
        },
    )

    assert payload["thread_id"] == "conv-123"
    assert payload["mode"] == "investigation"
    assert payload["domain_context"]["site_id"] == "site-002"
    assert payload["domain_context"]["equipment_id"] == "S002-AHU-L2-003"
    assert payload["evidence_counts"] == {"hybrid": 1, "brick": 0, "docs": 1, "memory": 0}
    assert payload["trace_count"] == 2
    assert payload["message_count"] == 2
    assert payload["observability"]["router_name"] == "ByConfidenceModelRouter"
    assert payload["observability"]["selected_model"] == "phi3:mini"


def test_build_advisory_kernel_headers_exposes_observability():
    payload = {
        "mode": "investigation",
        "status": "completed",
        "thread_id": "conv-123",
        "domain_context": {
            "site_id": "site-002",
            "equipment_id": "S002-AHU-L2-003",
            "zone": None,
            "time_range": {"relative": "last 24 hours"},
        },
        "summary": "Summary text",
        "next_step": "Next step text",
        "confidence_score": 0.45,
        "request_id": "kernel-abc",
        "evidence_counts": {"hybrid": 1, "brick": 0, "docs": 1, "memory": 0},
        "evidence_notes": ["documentation_context_empty"],
        "trace_count": 2,
        "message_count": 2,
        "observability": {
            "router_name": "ByConfidenceModelRouter",
            "selected_model": "phi3:mini",
            "selected_provider": "ollama",
            "selected_task_class": "light",
            "routing_reason": "default_lightweight_local_path",
            "hitl_required": False,
            "latency_ms": 14.2,
        },
    }

    headers = build_advisory_kernel_headers(payload)

    assert headers["X-Response-Type"] == "advisory_kernel"
    assert headers["X-Kernel-Thread-Id"] == "conv-123"
    assert headers["X-Kernel-Confidence"] == "0.45"
    assert headers["X-Kernel-Evidence-Counts"] == "hybrid=1, brick=0, docs=1, memory=0"
    assert headers["X-Kernel-Message-Count"] == "2"
    assert headers["X-Kernel-Router"] == "ByConfidenceModelRouter"
    assert headers["X-Kernel-Selected-Model"] == "phi3:mini"
    assert headers["X-Kernel-Selected-Provider"] == "ollama"
    assert headers["X-Kernel-Site-Id"] == "site-002"
    assert headers["X-Kernel-Equipment-Id"] == "S002-AHU-L2-003"


def test_extract_kernel_observability_reads_final_trace_metadata():
    observability = _extract_kernel_observability(
        {
            "node_trace": [
                {"event": "node_start", "metadata": {"selected_model": "ignored"}},
                {
                    "event": "node_end",
                    "metadata": {
                        "router_name": "ByConfidenceModelRouter",
                        "selected_model": "phi3:mini",
                        "selected_provider": "ollama",
                        "selected_task_class": "light",
                        "routing_reason": "default_lightweight_local_path",
                        "evidence_present": {"hybrid": 1},
                        "evidence_missing": ["documentation_context_empty"],
                        "hitl_required": False,
                        "latency_ms": 11.1,
                    },
                },
            ]
        }
    )

    assert observability["router_name"] == "ByConfidenceModelRouter"
    assert observability["selected_model"] == "phi3:mini"
    assert observability["evidence_present"] == {"hybrid": 1}
    assert observability["evidence_missing"] == ["documentation_context_empty"]


def test_log_advisory_kernel_response_emits_observability(caplog):
    payload = {
        "mode": "investigation",
        "status": "completed",
        "thread_id": "conv-123",
        "domain_context": {
            "site_id": "site-002",
            "equipment_id": "S002-AHU-L2-003",
        },
        "request_id": "kernel-abc",
        "confidence_score": 0.45,
        "trace_count": 2,
        "message_count": 2,
        "evidence_counts": {"hybrid": 1, "brick": 0, "docs": 1, "memory": 0},
        "observability": {
            "router_name": "ByConfidenceModelRouter",
            "selected_model": "phi3:mini",
            "selected_provider": "ollama",
            "selected_task_class": "light",
            "routing_reason": "default_lightweight_local_path",
            "latency_ms": 14.2,
        },
    }

    with caplog.at_level(logging.INFO):
        log_advisory_kernel_response(payload)

    assert "Advisory kernel response" in caplog.text
    assert "thread_id=conv-123" in caplog.text
    assert "site_id=site-002" in caplog.text
    assert "equipment_id=S002-AHU-L2-003" in caplog.text
    assert "model=phi3:mini" in caplog.text
    assert "router=ByConfidenceModelRouter" in caplog.text


def test_format_advisory_kernel_message_is_stable():
    body = format_advisory_kernel_message(
        {
            "mode": "investigation",
            "status": "completed",
            "thread_id": "conv-123",
            "domain_context": {
                "site_id": "site-002",
                "equipment_id": "S002-AHU-L2-003",
                "zone": None,
                "time_range": {"relative": "last 24 hours"},
            },
            "summary": "Summary text",
            "next_step": "Next step text",
            "confidence_score": 0.45,
            "request_id": "kernel-abc",
            "evidence_counts": {"hybrid": 1, "brick": 0, "docs": 1, "memory": 0},
            "evidence_notes": ["documentation_context_empty"],
            "trace_count": 2,
            "message_count": 2,
        }
    )

    assert "Mode: investigation" in body
    assert "Thread ID: conv-123" in body
    assert "Context: site_id=site-002, equipment_id=S002-AHU-L2-003" in body
    assert "Evidence: hybrid=1, brick=0, docs=1, memory=0" in body
    assert "Message count: 2" in body


@pytest.mark.asyncio
async def test_feature_flag_off_preserves_legacy_chat_path(monkeypatch):
    monkeypatch.setattr(settings, "sentinel_advisory_kernel_enabled", False)
    monkeypatch.setattr("app.api.chat.log_chat_query", lambda _message: None)
    monkeypatch.setattr("app.api.chat.slash_command_router.parse", lambda _message: None)
    monkeypatch.setattr("app.api.chat.model_gateway._resolve", lambda _task_class: ("local", "openai", "stub-model"))
    monkeypatch.setattr("app.api.chat.claude_service.is_configured", lambda: False)
    monkeypatch.setattr("app.api.chat.openai_service.is_configured", lambda: False)
    monkeypatch.setattr("app.api.chat.work_order_service.detect_work_order_request", lambda _message: None)

    async def _legacy_stream(*args, **kwargs):
        yield "data: legacy path\n\n"
        yield "data: [DONE]\n\n"

    monkeypatch.setattr("app.api.chat.generate_sse_stream", _legacy_stream)

    response = await chat(
        request=_build_request(),
        chat_request=ChatRequest(message="Investigate AHU-3", mode="investigation"),
        auth=_build_request().state.auth,
        guarded_message="Investigate AHU-3",
    )
    body = await _read_sse_body(response)

    assert response.headers["X-Response-Type"] == "ai_response"
    assert "legacy path" in body


@pytest.mark.asyncio
async def test_feature_flag_on_investigation_mode_routes_to_kernel(monkeypatch):
    monkeypatch.setattr(settings, "sentinel_advisory_kernel_enabled", True)
    monkeypatch.setattr("app.api.chat.log_chat_query", lambda _message: None)
    monkeypatch.setattr("app.api.chat.slash_command_router.parse", lambda _message: None)
    monkeypatch.setattr(
        "app.api.chat.run_advisory_kernel_chat",
        AsyncMock(
            return_value=(
                {
                    "mode": "investigation",
                    "status": "completed",
                    "thread_id": "conv-123",
                    "domain_context": {
                        "site_id": "site-002",
                        "equipment_id": "S002-AHU-L2-003",
                        "zone": None,
                        "time_range": {"relative": "last 24 hours"},
                    },
                    "summary": "kernel summary",
                    "next_step": "kernel next step",
                    "confidence_score": 0.25,
                    "request_id": "kernel-123",
                    "evidence_counts": {"hybrid": 1, "brick": 0, "docs": 0, "memory": 0},
                    "evidence_notes": [],
                    "trace_count": 2,
                    "message_count": 1,
                    "observability": {
                        "router_name": "ByConfidenceModelRouter",
                        "selected_model": "phi3:mini",
                        "selected_provider": "ollama",
                        "selected_task_class": "light",
                        "routing_reason": "default_lightweight_local_path",
                        "hitl_required": False,
                        "latency_ms": 14.2,
                    },
                },
                "kernel path",
            )
        ),
    )

    request = _build_request()
    response = await chat(
        request=request,
        chat_request=ChatRequest(message="Investigate AHU-3", mode="investigation", conversation_id="conv-123"),
        auth=request.state.auth,
        guarded_message="Investigate AHU-3",
    )
    body = await _read_sse_body(response)

    assert response.headers["X-Response-Type"] == "advisory_kernel"
    assert response.headers["X-Kernel-Thread-Id"] == "conv-123"
    assert response.headers["X-Kernel-Status"] == "completed"
    assert response.headers["X-Kernel-Router"] == "ByConfidenceModelRouter"
    assert response.headers["X-Kernel-Selected-Model"] == "phi3:mini"
    assert response.headers["X-Kernel-Site-Id"] == "site-002"
    assert response.headers["X-Kernel-Equipment-Id"] == "S002-AHU-L2-003"
    assert "event: advisory_kernel_metadata" in body
    assert "event: advisory_kernel_output" in body
    assert "kernel path" in body


@pytest.mark.asyncio
async def test_feature_flag_on_investigation_mode_preserves_domain_context_in_metadata(monkeypatch):
    reset_runtime_graph()
    monkeypatch.setattr(settings, "sentinel_advisory_kernel_enabled", True)
    monkeypatch.setattr("app.api.chat.log_chat_query", lambda _message: None)
    monkeypatch.setattr("app.api.chat.slash_command_router.parse", lambda _message: None)

    class HybridStub:
        async def query(self, **kwargs):
            return type(
                "HybridResult",
                (),
                {"to_dict": lambda self: {"equipment_id": kwargs.get("equipment_id"), "sources_used": ["hybrid"]}},
            )()

    class BrickStub:
        def get_context(self, equipment_id, include_points=True):
            return type("BrickResult", (), {"to_dict": lambda self: {"equipment_id": equipment_id, "points": []}})()

    class MemoryStub:
        def get_by_equipment(self, equipment_code, limit=5):
            return []

        def get_by_site(self, site_id, limit=5):
            return []

    monkeypatch.setattr(
        "app.agents_kernel.nodes.retrieve_context.get_hybrid_query_service", lambda site_id: HybridStub()
    )
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.get_brick_service", lambda site_id: BrickStub())
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.search_documentation", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.get_agent_memory_repository", lambda: MemoryStub())
    monkeypatch.setattr(
        "app.agents_kernel.nodes.draft_summary.model_gateway.call", AsyncMock(return_value="Bounded advisory summary.")
    )

    request = _build_request()
    response = await chat(
        request=request,
        chat_request=ChatRequest(
            message="Investigate S002-AHU-L2-003 over the last 24 hours",
            mode="investigation",
            conversation_id="conv-domain",
            site_id="site-002",
            equipment_id="S002-AHU-L2-003",
            time_range={"relative": "last 24 hours"},
        ),
        auth=request.state.auth,
        guarded_message="Investigate S002-AHU-L2-003 over the last 24 hours",
    )
    body = await _read_sse_body(response)

    assert response.headers["X-Kernel-Site-Id"] == "site-002"
    assert response.headers["X-Kernel-Equipment-Id"] == "S002-AHU-L2-003"
    assert '"site_id": "site-002"' in body
    assert '"equipment_id": "S002-AHU-L2-003"' in body
    assert '"relative": "last 24 hours"' in body


@pytest.mark.asyncio
async def test_feature_flag_on_repeated_conversation_id_preserves_thread_identity(monkeypatch):
    reset_runtime_graph()
    monkeypatch.setattr(settings, "sentinel_advisory_kernel_enabled", True)
    monkeypatch.setattr("app.api.chat.log_chat_query", lambda _message: None)
    monkeypatch.setattr("app.api.chat.slash_command_router.parse", lambda _message: None)

    class HybridStub:
        async def query(self, **kwargs):
            return type(
                "HybridResult",
                (),
                {"to_dict": lambda self: {"equipment_id": kwargs.get("equipment_id"), "sources_used": ["hybrid"]}},
            )()

    class BrickStub:
        def get_context(self, equipment_id, include_points=True):
            return type("BrickResult", (), {"to_dict": lambda self: {"equipment_id": equipment_id, "points": []}})()

    class MemoryStub:
        def get_by_equipment(self, equipment_code, limit=5):
            return []

        def get_by_site(self, site_id, limit=5):
            return []

    monkeypatch.setattr(
        "app.agents_kernel.nodes.retrieve_context.get_hybrid_query_service", lambda site_id: HybridStub()
    )
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.get_brick_service", lambda site_id: BrickStub())
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.search_documentation", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.get_agent_memory_repository", lambda: MemoryStub())
    monkeypatch.setattr(
        "app.agents_kernel.nodes.draft_summary.model_gateway.call", AsyncMock(return_value="Bounded advisory summary.")
    )

    request_one = _build_request()
    response_one = await chat(
        request=request_one,
        chat_request=ChatRequest(
            message="Investigate S002-AHU-L2-003",
            mode="investigation",
            conversation_id="conv-thread",
            site_id="site-002",
            equipment_id="S002-AHU-L2-003",
        ),
        auth=request_one.state.auth,
        guarded_message="Investigate S002-AHU-L2-003",
    )
    _ = await _read_sse_body(response_one)

    request_two = _build_request()
    response_two = await chat(
        request=request_two,
        chat_request=ChatRequest(
            message="Investigate S002-AHU-L2-003 again",
            mode="investigation",
            conversation_id="conv-thread",
            site_id="site-002",
            equipment_id="S002-AHU-L2-003",
        ),
        auth=request_two.state.auth,
        guarded_message="Investigate S002-AHU-L2-003 again",
    )
    _ = await _read_sse_body(response_two)

    assert response_one.headers["X-Kernel-Thread-Id"] == "conv-thread"
    assert response_two.headers["X-Kernel-Thread-Id"] == "conv-thread"
    assert int(response_two.headers["X-Kernel-Message-Count"]) >= int(response_one.headers["X-Kernel-Message-Count"])
