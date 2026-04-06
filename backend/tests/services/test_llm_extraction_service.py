"""Tests for LLMExtractionService (Phase 181-02).

Tests field extraction from OCR text, graceful degradation,
_esc helper, and C1 JSON injection prevention.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, Mock

from app.services.llm_extraction_service import (
    LLMExtractionResult,
    LLMExtractionService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Mock database with equipment rows."""
    rows = [
        {"code": "S002-CHILLER-B1-001", "type": "CHILLER", "location": "Basement B1"},
        {"code": "S002-AHU-L1-001", "type": "AHU", "location": "Level 1"},
    ]
    mock = Mock()
    mock.query.return_value.fetchall.return_value = rows
    return mock


@pytest.fixture
def service(mock_db):
    """Service instance with mock db."""
    return LLMExtractionService(mock_db, "S002")


# ---------------------------------------------------------------------------
# _esc helper
# ---------------------------------------------------------------------------


class TestEsc:
    def test_esc_double_curly_braces(self):
        assert LLMExtractionService._esc("{hello}") == "{{hello}}"

    def test_esc_open_brace_only(self):
        assert LLMExtractionService._esc("before { after") == "before {{ after"

    def test_esc_close_brace_only(self):
        assert LLMExtractionService._esc("before } after") == "before }} after"

    def test_esc_no_braces_unchanged(self):
        assert LLMExtractionService._esc("plain text 123") == "plain text 123"

    def test_esc_nested_braces(self):
        assert LLMExtractionService._esc("{{nested}}") == "{{{{nested}}}}"

    def test_esc_empty_string(self):
        assert LLMExtractionService._esc("") == ""


# ---------------------------------------------------------------------------
# extract_fields — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_fields_parses_valid_json(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.return_value = json.dumps(
        {
            "equipment_description": "Chiller in Basement B1",
            "equipment_code": "S002-CHILLER-B1-001",
            "document_date": "2026-03-15",
            "technician_name": "Johan Smith",
            "fault_description": "High temperature alarm",
            "action_taken": "Replaced compressor",
            "overall_confidence": 0.95,
        }
    )

    result = await service.extract_fields("raw ocr text here", gateway=mock_gateway)

    assert result.equipment_description == "Chiller in Basement B1"
    assert result.equipment_code == "S002-CHILLER-B1-001"
    assert result.document_date == "2026-03-15"
    assert result.technician_name == "Johan Smith"
    assert result.fault_description == "High temperature alarm"
    assert result.action_taken == "Replaced compressor"
    assert result.confidence == 0.95
    assert result.extraction_method == "llm"
    assert result.raw_response


# ---------------------------------------------------------------------------
# extract_fields — graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_fields_json_parse_error_returns_failed(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.return_value = "not valid json {{{"

    result = await service.extract_fields("raw text", gateway=mock_gateway)

    assert result.extraction_method == "failed"
    assert result.confidence == 0.0
    assert result.raw_response == "not valid json {{{"


@pytest.mark.asyncio
async def test_extract_fields_gateway_error_returns_failed(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.side_effect = RuntimeError("Gateway unavailable")

    result = await service.extract_fields("raw text", gateway=mock_gateway)

    assert result.extraction_method == "failed"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_extract_fields_empty_response_returns_failed(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.return_value = ""

    result = await service.extract_fields("raw text", gateway=mock_gateway)

    assert result.extraction_method == "failed"
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# extract_fields — _esc is applied to user-supplied fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_fields_escapes_raw_text(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.return_value = json.dumps(
        {
            "equipment_description": "Test",
            "equipment_code": None,
            "document_date": None,
            "technician_name": None,
            "fault_description": None,
            "action_taken": None,
            "overall_confidence": 0.5,
        }
    )

    await service.extract_fields("hello {world} test", gateway=mock_gateway)

    call_args = mock_gateway.call.call_args
    messages = call_args.kwargs["messages"]
    prompt = messages[0]["content"]
    # Check raw text braces are escaped
    assert "{{" in prompt
    assert "}}" in prompt
    # The actual braces in prompt should not be bare
    assert (
        "{{world}}" in prompt or "world" not in prompt.split("--- Document Text ---")[1].split("{{")[1].split("}}")[0]
    )


@pytest.mark.asyncio
async def test_extract_fields_escapes_document_type(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.return_value = json.dumps(
        {
            "equipment_description": "Test",
            "equipment_code": None,
            "document_date": None,
            "technician_name": None,
            "fault_description": None,
            "action_taken": None,
            "overall_confidence": 0.5,
        }
    )

    await service.extract_fields("text", document_type="job {card}", gateway=mock_gateway)

    call_args = mock_gateway.call.call_args
    messages = call_args.kwargs["messages"]
    prompt = messages[0]["content"]
    # The doc type braces should be escaped
    assert "{{job" in prompt or "card}}" in prompt


# ---------------------------------------------------------------------------
# extract_equipment_description
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_equipment_description_returns_string(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.return_value = json.dumps({"equipment_description": "Chiller Unit B1"})

    result = await service.extract_equipment_description("raw ocr text", gateway=mock_gateway)

    assert result == "Chiller Unit B1"


@pytest.mark.asyncio
async def test_extract_equipment_description_returns_empty_on_error(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.side_effect = RuntimeError("fail")

    result = await service.extract_equipment_description("raw ocr text", gateway=mock_gateway)

    assert result == ""


@pytest.mark.asyncio
async def test_extract_equipment_description_returns_empty_on_json_error(service):
    mock_gateway = AsyncMock()
    mock_gateway.call.return_value = "not json"

    result = await service.extract_equipment_description("raw ocr text", gateway=mock_gateway)

    assert result == ""


# ---------------------------------------------------------------------------
# LLMExtractionResult.failed()
# ---------------------------------------------------------------------------


def test_failed_result_dataclass():
    result = LLMExtractionResult.failed(raw_response="broken json")

    assert result.confidence == 0.0
    assert result.extraction_method == "failed"
    assert result.raw_response == "broken json"


# ---------------------------------------------------------------------------
# C1: email_intake_agent._esc_jinja prevents JSON injection
# ---------------------------------------------------------------------------


def test_email_intake_agent_esc_jinja_pattern():
    """Verify _esc_jinja pattern matches LLMExtractionService._esc."""
    from app.services.email_intake_agent import _esc_jinja

    assert _esc_jinja("{hello}") == "{{hello}}"
    assert _esc_jinja("test {data} end") == "test {{data}} end"
    assert _esc_jinja("no braces") == "no braces"


@pytest.mark.asyncio
async def test_email_intake_agent_c1_injection_prevented():
    """
    C1 Fix: body with {/} chars must be escaped before embedding in prompt.

    A body containing Jinja2-style braces like '{ "key": "value" }'
    should be escaped to prevent JSON context injection in the LLM prompt.
    """
    from app.services.email_intake_agent import _esc_jinja

    # Simulate an attacker sending an email with braces that could
    # break the JSON context in the prompt template
    malicious_body = '{"action": "injection_attempt"}'
    escaped = _esc_jinja(malicious_body)

    # Each brace is doubled: { -> {{, } -> }}
    assert escaped == '{{"action": "injection_attempt"}}'
    # The escaped version has no single braces (all doubled)
    assert escaped.count("{{") == malicious_body.count("{")
    assert escaped.count("}}") == malicious_body.count("}")
