"""Tests for Email Intake AI Agent (Phase 134).

Tests classification, reply generation, validation, and fallback behavior
with mocked LLM responses.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.email_intake_agent import (
    AgentResult,
    EmailIntakeAgent,
    _build_taxonomy_reference,
    get_email_intake_agent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agent():
    """Create a fresh agent instance for each test."""
    return EmailIntakeAgent()


@pytest.fixture
def good_llm_response():
    """A valid JSON response from the LLM."""
    return json.dumps(
        {
            "discipline": "Electrical",
            "sub_category": "Power outlet not working",
            "specialty": "electrical",
            "priority": "high",
            "location_desk": "204",
            "location_floor": "L2",
            "location_area": None,
            "phone": "0798607245",
            "issue_summary": "Broken power outlet at desk 204",
            "completeness": 0.95,
            "action": "auto_submit",
            "reply_text": (
                "Hi Pieter, I've logged your broken plug at desk 204 "
                "(Level 2). Reference: {ref}. Our electrical team has "
                "been notified. Kind regards,\nSENTINEL Building Management"
            ),
        }
    )


@pytest.fixture
def hvac_llm_response():
    """A valid HVAC classification response."""
    return json.dumps(
        {
            "discipline": "HVAC",
            "sub_category": "Too hot",
            "specialty": "hvac",
            "priority": "medium",
            "location_desk": None,
            "location_floor": "L1",
            "location_area": "Boardroom",
            "phone": None,
            "issue_summary": "Boardroom on Level 1 is too hot",
            "completeness": 0.65,
            "action": "request_info",
            "reply_text": (
                "Dear Sarah, thank you for reporting the temperature "
                "issue in the boardroom on Level 1. Reference: {ref}. "
                "Could you please provide your desk number or phone "
                "number so we can follow up? Kind regards,\n"
                "SENTINEL Building Management"
            ),
        }
    )


# ---------------------------------------------------------------------------
# Taxonomy reference
# ---------------------------------------------------------------------------


class TestTaxonomyReference:
    def test_builds_taxonomy_reference(self):
        ref = _build_taxonomy_reference()
        assert "Electrical" in ref
        assert "HVAC" in ref
        assert "Plumbing" in ref
        assert "Power outlet not working" in ref
        assert len(ref) > 500  # Non-trivial content

    def test_taxonomy_reference_cached(self):
        ref1 = _build_taxonomy_reference()
        ref2 = _build_taxonomy_reference()
        assert ref1 is ref2  # Same object (cached)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    def test_parse_plain_json(self, agent):
        raw = '{"discipline": "HVAC", "sub_category": "Too hot"}'
        result = agent._parse_response(raw)
        assert result["discipline"] == "HVAC"

    def test_parse_json_in_markdown_block(self, agent):
        raw = '```json\n{"discipline": "Electrical", "sub_category": "Sparking"}\n```'
        result = agent._parse_response(raw)
        assert result["discipline"] == "Electrical"

    def test_parse_json_with_surrounding_text(self, agent):
        raw = 'Here is the classification:\n{"discipline": "Plumbing", "sub_category": "Leaking tap"}\nDone.'
        result = agent._parse_response(raw)
        assert result["discipline"] == "Plumbing"

    def test_parse_invalid_json_raises(self, agent):
        with pytest.raises(json.JSONDecodeError):
            agent._parse_response("This is not JSON at all")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_result(self, agent, good_llm_response):
        parsed = json.loads(good_llm_response)
        result = agent._validate(parsed)
        assert isinstance(result, AgentResult)
        assert result.discipline == "Electrical"
        assert result.sub_category == "Power outlet not working"
        assert result.specialty == "electrical"
        assert result.priority == "high"
        assert result.location_desk == "204"
        assert result.location_floor == "L2"
        assert result.phone == "0798607245"
        assert result.completeness == 0.95
        assert result.action == "auto_submit"

    def test_invalid_discipline_falls_back(self, agent):
        parsed = {
            "discipline": "NonexistentDiscipline",
            "sub_category": "Something",
            "specialty": "general",
            "priority": "medium",
            "completeness": 0.5,
        }
        result = agent._validate(parsed)
        assert result.discipline == "General"
        assert result.sub_category == "Unclassified"

    def test_invalid_sub_category_corrected(self, agent):
        parsed = {
            "discipline": "Electrical",
            "sub_category": "Nonexistent sub",
            "specialty": "electrical",
            "priority": "medium",
            "completeness": 0.7,
        }
        result = agent._validate(parsed)
        assert result.discipline == "Electrical"
        # Should pick first valid sub_category for Electrical
        assert result.sub_category == "Power outlet not working"

    def test_invalid_priority_defaults_medium(self, agent):
        parsed = {
            "discipline": "HVAC",
            "sub_category": "Too hot",
            "specialty": "hvac",
            "priority": "super_urgent",
            "completeness": 0.5,
        }
        result = agent._validate(parsed)
        assert result.priority == "medium"

    def test_completeness_clamped(self, agent):
        parsed = {
            "discipline": "HVAC",
            "sub_category": "Too hot",
            "specialty": "hvac",
            "priority": "medium",
            "completeness": 1.5,
        }
        result = agent._validate(parsed)
        assert result.completeness == 1.0

    def test_action_derived_from_completeness(self, agent):
        # Even if LLM says "auto_submit", if completeness < 0.85, action is overridden
        parsed = {
            "discipline": "HVAC",
            "sub_category": "Too hot",
            "specialty": "hvac",
            "priority": "medium",
            "completeness": 0.50,
            "action": "auto_submit",
        }
        result = agent._validate(parsed)
        assert result.action == "manual_review"  # 0.50 < 0.60


# ---------------------------------------------------------------------------
# Keyword fallback
# ---------------------------------------------------------------------------


class TestKeywordFallback:
    def test_electrical_classification(self, agent):
        result = agent._keyword_fallback(
            from_name="Pieter",
            from_email="pieter@example.com",
            subject="Broken plug at desk 204",
            body_plain="Hi, I have a broken plug at my desk 204. Regards, Pieter, 0798607245",
            site_id="site-002",
        )
        assert result.discipline == "Electrical"
        assert result.sub_category == "Power outlet not working"
        assert result.location_desk == "204"
        assert result.phone == "0798607245"
        assert result.agent_model == "keyword_fallback"

    def test_hvac_classification(self, agent):
        result = agent._keyword_fallback(
            from_name="Sarah",
            from_email="sarah@example.com",
            subject="Office too hot",
            body_plain="The office on level 2 is very hot today.",
            site_id="site-002",
        )
        assert result.discipline == "HVAC"
        assert result.location_floor == "L2"

    def test_no_match_general(self, agent):
        result = agent._keyword_fallback(
            from_name="John",
            from_email="john@example.com",
            subject="Hello",
            body_plain="Just checking in about the building.",
            site_id="site-002",
        )
        assert result.discipline == "General"
        assert result.sub_category == "Unclassified"

    def test_reply_text_generated(self, agent):
        result = agent._keyword_fallback(
            from_name="Pieter",
            from_email="pieter@example.com",
            subject="Broken plug",
            body_plain="Broken plug at desk 204. 0798607245",
            site_id="site-002",
        )
        assert "Pieter" in result.reply_text
        assert "SENTINEL" in result.reply_text
        assert result.reply_html  # HTML reply generated

    def test_request_info_mentions_missing(self, agent):
        result = agent._keyword_fallback(
            from_name=None,
            from_email="anon@example.com",
            subject="Water leak",
            body_plain="There is a water leak somewhere.",
            site_id="site-002",
        )
        # Should be request_info since no location/phone
        assert result.action in ("request_info", "manual_review")


# ---------------------------------------------------------------------------
# Full classify_and_reply (mocked LLM)
# ---------------------------------------------------------------------------


class TestClassifyAndReply:
    @pytest.mark.asyncio
    async def test_successful_llm_call(self, agent, good_llm_response):
        with patch.object(agent, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = good_llm_response

            result = await agent.classify_and_reply(
                from_name="Pieter van Rooyen",
                from_email="pieter@example.com",
                subject="Broken plug at desk 204",
                body_plain="Hi, I have a broken plug at my desk 204.",
                site_id="site-002",
                bms_context=None,
            )

            assert result.discipline == "Electrical"
            assert result.action == "auto_submit"
            assert result.agent_latency_ms >= 0
            assert result.reply_html  # HTML generated
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self, agent):
        with patch.object(agent, "_call_llm", new_callable=AsyncMock, side_effect=RuntimeError("API down")):
            result = await agent.classify_and_reply(
                from_name="Pieter",
                from_email="pieter@example.com",
                subject="Broken plug at desk 204",
                body_plain="Hi, broken plug at desk 204. 0798607245",
                site_id="site-002",
                bms_context=None,
            )

            assert result.agent_model == "keyword_fallback"
            assert result.discipline == "Electrical"
            assert result.location_desk == "204"

    @pytest.mark.asyncio
    async def test_bms_context_in_prompt(self, agent):
        bms_context = {
            "building_name": "Centre Court",
            "active_alerts": [{"severity": "warning", "message": "FCU-101 high temp"}],
            "recent_work_orders": [{"code": "WO-2026-001", "title": "Fix AC", "status": "scheduled"}],
        }

        with patch.object(agent, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps(
                {
                    "discipline": "HVAC",
                    "sub_category": "Too hot",
                    "specialty": "hvac",
                    "priority": "medium",
                    "completeness": 0.65,
                    "action": "request_info",
                    "reply_text": "Test reply",
                }
            )

            await agent.classify_and_reply(
                from_name="Test",
                from_email="test@example.com",
                subject="Hot office",
                body_plain="Very hot",
                site_id="site-002",
                bms_context=bms_context,
            )

            # Verify BMS context was included in prompt
            prompt = mock_llm.call_args[0][0]
            assert "Centre Court" in prompt
            assert "FCU-101" in prompt
            assert "WO-2026-001" in prompt


# ---------------------------------------------------------------------------
# HTML reply wrapper
# ---------------------------------------------------------------------------


class TestHTMLWrapper:
    def test_html_contains_sentinel_branding(self, agent):
        html = agent._wrap_html(
            "Test reply text",
            ref="WO-2026-001",
            category="electrical",
            from_name="Test",
        )
        assert "SENTINEL" in html
        assert "WO-2026-001" in html
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_html_escapes_special_chars(self, agent):
        html = agent._wrap_html(
            'Issue with <tag> & "quotes"',
            ref="REF-1",
            category="general",
            from_name="User <script>",
        )
        assert "<script>" not in html
        assert "&lt;tag&gt;" in html


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_email_intake_agent_returns_same_instance(self):
        import app.services.email_intake_agent as mod

        mod._agent = None  # Reset
        a1 = get_email_intake_agent()
        a2 = get_email_intake_agent()
        assert a1 is a2
        mod._agent = None  # Clean up
