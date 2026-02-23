"""Tests for RecursiveAnalyzer — all with mocked InferenceClient."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import ResultSchema
from app.services.case_loader import CaseLoader
from app.services.inference_client import ChatResult, InferenceClient
from app.services.redaction_service import RedactionService
from app.services.recursive_analyzer import RecursiveAnalyzer
from app.services.run_manager import RunManager
from app.services.trace_builder import TraceBuilder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def evidence_case(tmp_path: Path) -> tuple[str, CaseLoader, Path]:
    """Create a test case with evidence files under tmp_path/cases."""
    cases_dir = tmp_path / "cases"
    case_id = "TESTCASE"
    case_dir = cases_dir / case_id
    evidence_dir = case_dir / "evidence"
    evidence_dir.mkdir(parents=True)

    # Manifest
    manifest = {
        "case_id": case_id,
        "created_at": "2026-02-23T10:00:00Z",
        "description": "Test case",
        "evidence_files": [],
    }
    (case_dir / "manifest.json").write_text(json.dumps(manifest))

    # Evidence files
    (evidence_dir / "events.json").write_text(
        json.dumps({"events": [{"type": "alarm", "msg": "High temp zone 101"}]})
    )
    (evidence_dir / "notes.txt").write_text("Chiller tripped at 14:00.")

    loader = CaseLoader(cases_dir=str(cases_dir))
    return case_id, loader, tmp_path


@pytest.fixture
def run_env(tmp_path: Path) -> tuple[RunManager, TraceBuilder]:
    """Set up RunManager with tmp output dir and a TraceBuilder that uses it."""
    output_dir = tmp_path / "rlm_out"
    output_dir.mkdir(exist_ok=True)
    rm = RunManager(output_dir=str(output_dir))
    tb = TraceBuilder(run_manager=rm)
    return rm, tb


def _make_chat_result(text: str, input_tokens: int = 10, output_tokens: int = 50) -> ChatResult:
    return ChatResult(text=text, input_tokens=input_tokens, output_tokens=output_tokens, model="phi3:mini")


def _complete_response(needs_deeper: bool = False, confidence: float = 0.85) -> str:
    """Build a JSON response from the mock LLM."""
    return json.dumps({
        "findings": ["High temperature detected in zone 101"],
        "anomalies": [{"description": "Chiller offline", "severity": "high"}],
        "timeline": [{"time": "14:00", "description": "Chiller tripped"}],
        "recommended_actions": ["Restart chiller and inspect coolant levels"],
        "confidence": confidence,
        "needs_deeper": needs_deeper,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_pass_analysis(evidence_case, run_env):
    """Mock LLM returns complete findings, analyzer stops at depth 1."""
    case_id, loader, tmp_path = evidence_case
    rm, tb = run_env

    # Create run
    run_id = await rm.create_run(case_id, "What happened?", "phi3:mini")

    # Mock InferenceClient
    mock_client = AsyncMock(spec=InferenceClient)
    mock_client.chat.return_value = _make_chat_result(_complete_response())

    # Patch run_manager and trace_builder to use test instances
    with patch("app.services.recursive_analyzer.trace_builder", tb), \
         patch("app.services.run_manager.run_manager", rm):
        analyzer = RecursiveAnalyzer(
            inference_client=mock_client,
            case_loader=loader,
            trace=tb,
        )
        result = await analyzer.analyze(case_id, "What happened?", "phi3:mini", run_id)

    assert result.status == "complete"
    assert len(result.findings) >= 1
    assert result.confidence >= 0.8
    assert result.trajectory.steps == 1
    assert result.needs_deeper_run is False


@pytest.mark.asyncio
async def test_recursive_passes(evidence_case, run_env):
    """Mock LLM returns 'need deeper analysis' first, then complete — verify 2 passes."""
    case_id, loader, tmp_path = evidence_case
    rm, tb = run_env
    run_id = await rm.create_run(case_id, "Root cause?", "phi3:mini")

    call_count = 0

    async def mock_chat(messages, model=None, max_tokens=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_chat_result(_complete_response(needs_deeper=True, confidence=0.5))
        return _make_chat_result(_complete_response(needs_deeper=False, confidence=0.9))

    mock_client = AsyncMock(spec=InferenceClient)
    mock_client.chat = mock_chat

    with patch("app.services.recursive_analyzer.trace_builder", tb), \
         patch("app.services.run_manager.run_manager", rm):
        analyzer = RecursiveAnalyzer(
            inference_client=mock_client,
            case_loader=loader,
            trace=tb,
        )
        result = await analyzer.analyze(case_id, "Root cause?", "phi3:mini", run_id)

    assert result.status == "complete"
    assert result.trajectory.steps == 2
    assert call_count == 2
    assert result.confidence >= 0.9


@pytest.mark.asyncio
async def test_budget_timeout(evidence_case, run_env):
    """Set max_runtime_seconds=1, mock slow LLM — verify needs_deeper_run=True."""
    case_id, loader, tmp_path = evidence_case
    rm, tb = run_env
    run_id = await rm.create_run(case_id, "Timeout test", "phi3:mini")

    # Mock LLM that always wants deeper but is not slow itself
    # The trick: we set max_runtime to a very small value so budget runs out
    mock_client = AsyncMock(spec=InferenceClient)
    mock_client.chat.return_value = _make_chat_result(
        _complete_response(needs_deeper=True, confidence=0.4)
    )

    with patch("app.services.recursive_analyzer.trace_builder", tb), \
         patch("app.services.run_manager.run_manager", rm), \
         patch("app.services.recursive_analyzer.settings") as mock_settings:
        mock_settings.max_runtime_seconds = 0.001  # Extremely short — budget exhausted immediately
        mock_settings.max_recursion_depth = 10
        mock_settings.max_tokens_per_call = 1200
        mock_settings.temperature = 0.1
        mock_settings.model_name = "phi3:mini"
        mock_settings.inference_provider = "ollama"

        analyzer = RecursiveAnalyzer(
            inference_client=mock_client,
            case_loader=loader,
            trace=tb,
        )
        result = await analyzer.analyze(case_id, "Timeout test", "phi3:mini", run_id)

    # Should be complete (not error) but with needs_deeper_run=True
    assert result.status == "complete"
    assert result.needs_deeper_run is True


@pytest.mark.asyncio
async def test_budget_depth_limit(evidence_case, run_env):
    """Set max_recursion_depth=2, mock always-needs-more — verify stops at 2."""
    case_id, loader, tmp_path = evidence_case
    rm, tb = run_env
    run_id = await rm.create_run(case_id, "Depth test", "phi3:mini")

    mock_client = AsyncMock(spec=InferenceClient)
    mock_client.chat.return_value = _make_chat_result(
        _complete_response(needs_deeper=True, confidence=0.4)
    )

    with patch("app.services.recursive_analyzer.trace_builder", tb), \
         patch("app.services.run_manager.run_manager", rm), \
         patch("app.services.recursive_analyzer.settings") as mock_settings:
        mock_settings.max_runtime_seconds = 120
        mock_settings.max_recursion_depth = 2
        mock_settings.max_tokens_per_call = 1200
        mock_settings.temperature = 0.1
        mock_settings.model_name = "phi3:mini"
        mock_settings.inference_provider = "ollama"

        analyzer = RecursiveAnalyzer(
            inference_client=mock_client,
            case_loader=loader,
            trace=tb,
        )
        result = await analyzer.analyze(case_id, "Depth test", "phi3:mini", run_id)

    assert result.trajectory.steps == 2
    assert result.needs_deeper_run is True


@pytest.mark.asyncio
async def test_llm_error_handling(evidence_case, run_env):
    """Mock InferenceClient.chat() raises exception — verify status='error'."""
    case_id, loader, tmp_path = evidence_case
    rm, tb = run_env
    run_id = await rm.create_run(case_id, "Error test", "phi3:mini")

    mock_client = AsyncMock(spec=InferenceClient)
    mock_client.chat.side_effect = RuntimeError("Ollama connection refused")

    with patch("app.services.recursive_analyzer.trace_builder", tb), \
         patch("app.services.run_manager.run_manager", rm):
        analyzer = RecursiveAnalyzer(
            inference_client=mock_client,
            case_loader=loader,
            trace=tb,
        )
        result = await analyzer.analyze(case_id, "Error test", "phi3:mini", run_id)

    assert result.status == "error"
    assert "Ollama connection refused" in result.summary


@pytest.mark.asyncio
async def test_redaction_applied(evidence_case, run_env):
    """Mock LLM returns SA ID number in findings — verify redacted in output."""
    case_id, loader, tmp_path = evidence_case
    rm, tb = run_env
    run_id = await rm.create_run(case_id, "PII test", "phi3:mini")

    # Response contains a valid SA ID number (8501015009088, Luhn-valid)
    pii_response = json.dumps({
        "findings": ["Access by person with ID 8501015009088 at 14:00"],
        "anomalies": [],
        "timeline": [],
        "recommended_actions": [],
        "confidence": 0.8,
        "needs_deeper": False,
    })

    mock_client = AsyncMock(spec=InferenceClient)
    mock_client.chat.return_value = _make_chat_result(pii_response)

    with patch("app.services.recursive_analyzer.trace_builder", tb), \
         patch("app.services.run_manager.run_manager", rm):
        analyzer = RecursiveAnalyzer(
            inference_client=mock_client,
            case_loader=loader,
            trace=tb,
        )
        result = await analyzer.analyze(case_id, "PII test", "phi3:mini", run_id)

    # SA ID should be redacted
    for finding in result.findings:
        assert "8501015009088" not in finding
    assert "[REDACTED-ID-001]" in result.findings[0]


@pytest.mark.asyncio
async def test_trace_entries_created(evidence_case, run_env):
    """Verify trace.jsonl has file_access and model_call entries after analysis."""
    case_id, loader, tmp_path = evidence_case
    rm, tb = run_env
    run_id = await rm.create_run(case_id, "Trace test", "phi3:mini")

    mock_client = AsyncMock(spec=InferenceClient)
    mock_client.chat.return_value = _make_chat_result(_complete_response())

    with patch("app.services.recursive_analyzer.trace_builder", tb), \
         patch("app.services.run_manager.run_manager", rm):
        analyzer = RecursiveAnalyzer(
            inference_client=mock_client,
            case_loader=loader,
            trace=tb,
        )
        await analyzer.analyze(case_id, "Trace test", "phi3:mini", run_id)

    # Read trace
    trace_entries = rm.get_trace(run_id)
    assert trace_entries is not None

    event_types = [e["event_type"] for e in trace_entries]
    assert "file_access" in event_types
    assert "model_call" in event_types

    # Verify model_call has hashes, not raw text
    model_calls = [e for e in trace_entries if e["event_type"] == "model_call"]
    assert len(model_calls) >= 1
    mc = model_calls[0]
    assert "prompt_hash" in mc["details"]
    assert "response_hash" in mc["details"]
    assert len(mc["details"]["prompt_hash"]) == 64  # SHA256 hex length
    assert len(mc["details"]["response_hash"]) == 64
