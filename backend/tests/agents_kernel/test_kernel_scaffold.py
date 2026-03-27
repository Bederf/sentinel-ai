"""Tests for the advisory kernel scaffold."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents_kernel.checkpointer import get_thread_config, get_thread_id
from app.agents_kernel.graph_runner import compile_graph, reset_runtime_graph, run_smoke_graph
from app.agents_kernel.nodes.draft_summary import draft_summary_node
from app.agents_kernel.nodes.finalize import finalize_node
from app.agents_kernel.nodes.intake import intake_node
from app.agents_kernel.nodes.retrieve_context import retrieve_context_node
from app.agents_kernel.state import get_request_id, new_kernel_state
from app.agents_kernel.tools.file_tools import list_virtual_files, read_virtual_file, write_virtual_file
from app.agents_kernel.tools.think_tool import think_step
from app.agents_kernel.tools.todo_tools import read_todos, write_todos
from app.agents_kernel.trace import record_error, record_node_end, record_node_start


def test_new_kernel_state_initializes_trimmed_shape():
    state = new_kernel_state(
        message="Investigate AHU-3 energy spike.",
        conversation_id="conv-123",
        mode="investigation",
        site_id="site-002",
        equipment_id="S002-AHU-L2-003",
        time_range={"relative": "last 24 hours"},
    )

    assert state["domain_context"]["conversation_id"] == "conv-123"
    assert state["domain_context"]["site_id"] == "site-002"
    assert state["domain_context"]["equipment_id"] == "S002-AHU-L2-003"
    assert state["domain_context"]["time_range"] == {"relative": "last 24 hours"}
    assert state["domain_context"]["requested_output"] == "investigation"
    assert state["messages"]
    assert state["evidence_bundle"] == {
        "hybrid": [],
        "brick": [],
        "docs": [],
        "memory": [],
        "notes": [],
    }
    assert state["todos"] == []
    assert state["files"] == {}
    assert state["node_trace"] == []
    assert state["tool_calls_trace"] == []
    assert state["errors"] == []
    assert get_request_id(state).startswith("kernel-")


def test_trace_helpers_append_structured_entries():
    state = new_kernel_state(message="test")

    start = record_node_start(state, "start_node", input_summary="incoming message")
    end = record_node_end(state, "start_node", output_summary="todo written")
    error = record_error(state, "boom", node_name="start_node")

    assert start["event"] == "node_start"
    assert end["event"] == "node_end"
    assert state["node_trace"][0]["node_name"] == "start_node"
    assert state["errors"][0]["message"] == "boom"
    assert error["node_name"] == "start_node"


def test_todo_tools_are_state_backed():
    state = new_kernel_state(message="test")

    write_todos(state, ["Check telemetry", "Review docs"])
    todos = read_todos(state)

    assert todos == ["Check telemetry", "Review docs"]
    assert state["tool_calls_trace"][-1]["tool_name"] == "read_todos"


def test_virtual_file_tools_are_state_backed():
    state = new_kernel_state(message="test")

    write_virtual_file(state, "analysis.md", "Smoke graph notes")
    content = read_virtual_file(state, "analysis.md")
    listing = list_virtual_files(state)
    thought = think_step(state, "Need more evidence.")

    assert content == "Smoke graph notes"
    assert listing == [{"filename": "analysis.md", "size": 17}]
    assert thought == "Need more evidence."


def test_thread_config_uses_conversation_id():
    assert get_thread_id("conv-abc") == "conv-abc"
    assert get_thread_config("conv-abc") == {"configurable": {"thread_id": "conv-abc"}}
    assert get_thread_config("conv-abc") == {"configurable": {"thread_id": "conv-abc"}}
    generated = get_thread_id()
    assert generated.startswith("kernel-thread-")


def test_intake_node_initializes_domain_context():
    state = new_kernel_state(message="Investigate S002-AHU-L2-003 at site-002 over the last 24 hours.")

    updates = intake_node(state)

    assert updates["domain_context"]["site_id"] == "site-002"
    assert updates["domain_context"]["equipment_id"] == "S002-AHU-L2-003"
    assert updates["domain_context"]["time_range"] == {"relative": "last 24 hours"}
    assert updates["todos"] == [
        "Gather allowed context sources",
        "Draft a bounded operator-facing summary",
    ]
    assert "intake_request.txt" in updates["files"]


@pytest.mark.asyncio
async def test_retrieve_context_calls_only_allowed_services(monkeypatch):
    state = new_kernel_state(
        message="Investigate S002-AHU-L2-003 at site-002 over the last 24 hours.",
        site_id="site-002",
        equipment_id="S002-AHU-L2-003",
    )

    class HybridStub:
        async def query(self, **kwargs):
            return SimpleNamespace(
                to_dict=lambda: {
                    "equipment_id": kwargs["equipment_id"],
                    "sources_used": ["hybrid"],
                    "documents": [],
                }
            )

    class BrickStub:
        def get_context(self, equipment_id, include_points=True):
            return SimpleNamespace(
                to_dict=lambda: {
                    "equipment_id": equipment_id,
                    "points": [{"label": "Supply Temp"}] if include_points else [],
                }
            )

    class MemoryStub:
        def get_by_equipment(self, equipment_code, limit=5):
            return [{"equipment_code": equipment_code, "key": "quirk", "value": "Needs morning warm-up"}]

        def get_by_site(self, site_id, limit=5):
            return [{"site_id": site_id, "key": "quirk", "value": "Site-wide note"}]

    monkeypatch.setattr(
        "app.agents_kernel.nodes.retrieve_context.get_hybrid_query_service", lambda site_id: HybridStub()
    )
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.get_brick_service", lambda site_id: BrickStub())
    monkeypatch.setattr(
        "app.agents_kernel.nodes.retrieve_context.search_documentation",
        AsyncMock(return_value=[{"title": "AHU SOP", "content": "Inspect filters first."}]),
    )
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.get_agent_memory_repository", lambda: MemoryStub())

    updates = await retrieve_context_node(state)

    assert updates["evidence_bundle"]["hybrid"][0]["sources_used"] == ["hybrid"]
    assert updates["evidence_bundle"]["brick"][0]["equipment_id"] == "S002-AHU-L2-003"
    assert updates["evidence_bundle"]["docs"][0]["title"] == "AHU SOP"
    assert updates["evidence_bundle"]["memory"][0]["equipment_code"] == "S002-AHU-L2-003"
    assert "evidence_bundle.json" in updates["files"]
    assert updates["output_state"]["status"] == "context_retrieved"


@pytest.mark.asyncio
async def test_draft_summary_uses_model_gateway_not_provider_client(monkeypatch):
    state = new_kernel_state(message="Investigate AHU-3")
    state["evidence_bundle"]["hybrid"] = [{"equipment_id": "S002-AHU-L2-003"}]
    state["evidence_bundle"]["notes"] = ["documentation_context_empty"]
    state["output_state"]["confidence_score"] = 0.45

    gateway_call = AsyncMock(return_value="AHU context found, but supporting documentation is limited.")
    monkeypatch.setattr("app.agents_kernel.nodes.draft_summary.model_gateway.call", gateway_call)

    updates = await draft_summary_node(state)

    assert updates["output_state"]["summary"] == "AHU context found, but supporting documentation is limited."
    gateway_call.assert_awaited_once()
    assert gateway_call.await_args.kwargs["task_class"] == "light"


def test_finalize_returns_kernel_response_shape():
    state = new_kernel_state(message="Investigate AHU-3")
    state["evidence_bundle"]["hybrid"] = [{"equipment_id": "S002-AHU-L2-003"}]
    state["evidence_bundle"]["notes"] = ["documentation_context_empty"]
    state["output_state"]["summary"] = "AHU context found."
    state["output_state"]["confidence_score"] = 0.45
    write_virtual_file(state, "evidence_bundle.json", "{}")

    updates = finalize_node(state)

    assert updates["output_state"]["status"] == "completed"
    assert updates["output_state"]["next_step"]
    assert "Evidence sources:" in updates["output_state"]["summary"]


@pytest.mark.asyncio
async def test_smoke_graph_compiles_and_runs():
    reset_runtime_graph()
    compiled = compile_graph()
    assert compiled is not None

    class HybridStub:
        async def query(self, **kwargs):
            return SimpleNamespace(
                to_dict=lambda: {
                    "equipment_id": kwargs.get("equipment_id"),
                    "sources_used": ["hybrid"],
                    "documents": [],
                }
            )

    class BrickStub:
        def get_context(self, equipment_id, include_points=True):
            return SimpleNamespace(
                to_dict=lambda: {
                    "equipment_id": equipment_id,
                    "points": [{"label": "Supply Temp"}] if include_points else [],
                }
            )

    class MemoryStub:
        def get_by_equipment(self, equipment_code, limit=5):
            return [{"equipment_code": equipment_code, "key": "quirk", "value": "Needs morning warm-up"}]

        def get_by_site(self, site_id, limit=5):
            return [{"site_id": site_id, "key": "quirk", "value": "Site-wide note"}]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.agents_kernel.nodes.retrieve_context.get_hybrid_query_service", lambda site_id: HybridStub()
    )
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.get_brick_service", lambda site_id: BrickStub())
    monkeypatch.setattr(
        "app.agents_kernel.nodes.retrieve_context.search_documentation",
        AsyncMock(return_value=[{"title": "AHU SOP", "content": "Inspect filters first."}]),
    )
    monkeypatch.setattr("app.agents_kernel.nodes.retrieve_context.get_agent_memory_repository", lambda: MemoryStub())
    monkeypatch.setattr(
        "app.agents_kernel.nodes.draft_summary.model_gateway.call",
        AsyncMock(return_value="Bounded advisory summary."),
    )

    final_state = await run_smoke_graph(
        message="Investigate S002-AHU-L2-003 over the last 24 hours.",
        conversation_id="conv-smoke",
        mode="investigation",
        site_id="site-002",
        equipment_id="S002-AHU-L2-003",
    )
    monkeypatch.undo()

    assert final_state["output_state"]["status"] == "completed"
    assert "Bounded advisory summary." in final_state["output_state"]["summary"]
    assert final_state["output_state"]["next_step"]
    assert final_state["evidence_bundle"]["hybrid"]
    assert any(entry["event"] == "node_start" for entry in final_state["node_trace"])
    assert any(entry["event"] == "node_end" for entry in final_state["node_trace"])
    assert any(entry["metadata"]["selected_task_class"] == "light" for entry in final_state["node_trace"])


@pytest.mark.asyncio
async def test_conversation_id_maps_to_same_thread_id_across_invocations(monkeypatch):
    reset_runtime_graph()

    class HybridStub:
        async def query(self, **kwargs):
            return SimpleNamespace(
                to_dict=lambda: {"equipment_id": kwargs.get("equipment_id"), "sources_used": ["hybrid"]}
            )

    class BrickStub:
        def get_context(self, equipment_id, include_points=True):
            return SimpleNamespace(to_dict=lambda: {"equipment_id": equipment_id, "points": []})

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

    first = await run_smoke_graph(
        message="Investigate S002-AHU-L2-003.",
        conversation_id="conv-thread",
        mode="investigation",
        site_id="site-002",
        equipment_id="S002-AHU-L2-003",
    )
    second = await run_smoke_graph(
        message="Investigate S002-AHU-L2-003 again.",
        conversation_id="conv-thread",
        mode="investigation",
        site_id="site-002",
        equipment_id="S002-AHU-L2-003",
    )

    assert first["domain_context"]["conversation_id"] == "conv-thread"
    assert second["domain_context"]["conversation_id"] == "conv-thread"
    assert len(second["messages"]) >= len(first["messages"])
