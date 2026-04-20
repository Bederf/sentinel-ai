"""
Tests for the Desk Complaint LangGraph Agent
==============================================
Unit tests for NLP extraction, graph traversal, history summary,
and channel formatters.
"""

import os
import sys

import pytest

# Ensure backend is on path and DEMO_MODE is active
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.setdefault("DEMO_MODE", "true")

from app.agents.complaint_nlp import (
    detect_comfort_complaint,
    extract_complaint_types,
    extract_desk_id,
    extract_duration,
)
from app.agents.formatters import (
    format_for_chat,
    format_for_telegram,
    format_for_whatsapp,
)
from app.models.complaint import ComplaintDiagnosis, Desk, HVACZone

# ===================================================================
# NLP: detect_comfort_complaint
# ===================================================================


class TestDetectComfortComplaint:
    """Tests for comfort complaint detection."""

    @pytest.mark.parametrize(
        "text",
        [
            "it's freezing at my desk",
            "too hot here",
            "I'm sweating",
            "the FCU is making noise",
            "really stuffy in here",
            "too dark can't see",
            "it's so cold",
            "there is a draft coming from somewhere",
            "the room is boiling",
            "uncomfortable temperature",
        ],
    )
    def test_detects_complaints(self, text: str):
        assert detect_comfort_complaint(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "WO-2026-0042",
            "status",
            "help",
            "?",
            "alerts",
            "/start",
            "What's the weather like?",
        ],
    )
    def test_rejects_non_complaints(self, text: str):
        assert detect_comfort_complaint(text) is False


# ===================================================================
# NLP: extract_desk_id
# ===================================================================


class TestExtractDeskId:
    """Tests for desk ID extraction."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("desk 203 is too hot", "203"),
            ("desk 25", "25"),
            ("at L12-25", "L12-25"),
            ("at desk 42", "42"),
            ("too hot at 25", "25"),
            ("desk L2-D025", "L2-D025"),
            ("I'm at L2-D025 and it's cold", "L2-D025"),
        ],
    )
    def test_extracts_desk_id(self, text: str, expected: str):
        assert extract_desk_id(text) == expected

    def test_returns_none_when_no_desk(self):
        assert extract_desk_id("it's too hot") is None
        assert extract_desk_id("hello world") is None

    def test_bare_number_rejected_by_default(self):
        """Bare numbers without context words are not desk IDs by default."""
        assert extract_desk_id("25") is None

    def test_bare_number_accepted_when_flag_set(self):
        """In multi-turn context, bare numbers are accepted."""
        assert extract_desk_id("25", bare_number_ok=True) == "25"
        assert extract_desk_id("203", bare_number_ok=True) == "203"


# ===================================================================
# NLP: extract_complaint_types
# ===================================================================


class TestExtractComplaintTypes:
    """Tests for complaint type extraction."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("too cold", ["too_cold"]),
            ("too hot", ["too_hot"]),
            ("I'm freezing", ["too_cold"]),
            ("stuffy in here", ["stuffy"]),
            ("drafty", ["drafty"]),
            ("FCU is noisy", ["noise"]),
            ("too dark", ["too_dark"]),
            ("too bright", ["too_bright"]),
        ],
    )
    def test_single_type(self, text: str, expected: list):
        assert extract_complaint_types(text) == expected

    def test_compound_types(self):
        result = extract_complaint_types("cold and noisy")
        assert "too_cold" in result
        assert "noise" in result

    def test_compound_types_stuffy_dark(self):
        result = extract_complaint_types("stuffy and dark")
        assert "stuffy" in result
        assert "too_dark" in result

    def test_empty_for_no_complaint(self):
        assert extract_complaint_types("hello world") == []
        assert extract_complaint_types("status") == []


# ===================================================================
# NLP: extract_duration
# ===================================================================


class TestExtractDuration:
    """Tests for duration extraction."""

    def test_since_this_morning(self):
        assert extract_duration("since this morning") is not None

    def test_for_past_hours(self):
        result = extract_duration("it's been hot for the past 2 hours")
        assert result is not None
        assert "2 hour" in result

    def test_all_day(self):
        result = extract_duration("it's been cold all day")
        assert result is not None
        assert "all day" in result

    def test_none_when_no_duration(self):
        assert extract_duration("too hot") is None
        assert extract_duration("hello") is None


# ===================================================================
# Formatters
# ===================================================================


@pytest.fixture
def sample_diagnosis():
    """Create a sample diagnosis for formatter tests."""
    desk = Desk(
        desk_id="L12-25",
        floor="Level 2",
        building="Sandton",
        zone_id="Zone-L2-C",
        near_window=True,
        orientation="N",
    )
    zone = HVACZone(
        zone_id="Zone-L2-C",
        zone_name="Level 2 North",
        floor="Level 2",
        fcu_id="S002-FCU-L2-C",
        vav_id="S002-VAV-L2-C",
        current_temp=24.5,
        setpoint=22.0,
        status="running",
    )
    return ComplaintDiagnosis(
        complaint_id="test-001",
        desk=desk,
        zone=zone,
        diagnosis="FCU running, 2.5C above setpoint",
        root_cause="Solar heat gain - north-facing window",
        confidence="high",
        suggestions=[
            "Lower FCU setpoint to 20C",
            "Dim luminaires to 40%",
            "Verify VAV damper position",
        ],
        needs_dispatch=False,
    )


@pytest.fixture
def sample_history():
    return {
        "count": 2,
        "same_type_count": 2,
        "last_complaint": "2026-02-19T10:30:00",
        "escalation_recommended": False,
    }


class TestFormatForChat:
    """Tests for chat (markdown) formatter."""

    def test_includes_desk_id(self, sample_diagnosis):
        result = format_for_chat(sample_diagnosis)
        assert "L12-25" in result

    def test_includes_temperature(self, sample_diagnosis):
        result = format_for_chat(sample_diagnosis)
        assert "24.5" in result
        assert "22.0" in result

    def test_includes_root_cause(self, sample_diagnosis):
        result = format_for_chat(sample_diagnosis)
        assert "Solar heat gain" in result

    def test_includes_suggestions(self, sample_diagnosis):
        result = format_for_chat(sample_diagnosis)
        assert "Lower FCU" in result
        assert "Dim luminaires" in result

    def test_includes_history(self, sample_diagnosis, sample_history):
        result = format_for_chat(sample_diagnosis, sample_history)
        assert "2 in last 7 days" in result

    def test_markdown_headers(self, sample_diagnosis):
        result = format_for_chat(sample_diagnosis)
        assert "##" in result
        assert "###" in result

    def test_dispatch_note(self, sample_diagnosis):
        sample_diagnosis.needs_dispatch = True
        result = format_for_chat(sample_diagnosis)
        assert "technician dispatch" in result.lower()


class TestFormatForWhatsApp:
    """Tests for WhatsApp formatter."""

    def test_uses_bold_formatting(self, sample_diagnosis):
        result = format_for_whatsapp(sample_diagnosis)
        assert "*Desk L12-25*" in result

    def test_includes_temperature_with_degree(self, sample_diagnosis):
        result = format_for_whatsapp(sample_diagnosis)
        assert "\u00b0C" in result

    def test_includes_history_warning(self, sample_diagnosis, sample_history):
        result = format_for_whatsapp(sample_diagnosis, sample_history)
        assert "2 similar complaint" in result

    def test_escalation_shows_wo_prompt(self, sample_diagnosis):
        history = {"count": 3, "escalation_recommended": True}
        result = format_for_whatsapp(sample_diagnosis, history)
        assert "WO" in result


class TestFormatForTelegram:
    """Tests for Telegram formatter."""

    def test_includes_desk_report_header(self, sample_diagnosis):
        result = format_for_telegram(sample_diagnosis)
        assert "*Desk Comfort Report" in result

    def test_includes_fcu_code_block(self, sample_diagnosis):
        result = format_for_telegram(sample_diagnosis)
        assert "`S002-FCU-L2-C`" in result

    def test_includes_confidence(self, sample_diagnosis):
        result = format_for_telegram(sample_diagnosis)
        assert "high" in result


# ===================================================================
# Graph traversal
# ===================================================================


class TestGraphTraversal:
    """Tests for the LangGraph desk complaint graph."""

    @pytest.fixture(autouse=True)
    def reset_graph(self):
        """Reset the graph singleton for each test."""
        import app.agents.desk_complaint_graph as mod

        mod._compiled_graph = None
        mod._checkpointer = __import__("langgraph.checkpoint.memory", fromlist=["MemorySaver"]).MemorySaver()

    def _get_agent(self):
        from app.agents import get_desk_complaint_graph

        return get_desk_complaint_graph()

    def test_complete_info_goes_to_diagnose(self):
        """When desk_id and complaint_type are both present, no asking."""
        from langchain_core.messages import HumanMessage

        agent = self._get_agent()
        config = {"configurable": {"thread_id": "test_complete"}}

        result = agent.invoke(
            {
                "messages": [HumanMessage(content="Too hot at desk 25")],
                "user_id": "test",
                "channel": "chat",
            },
            config,
        )

        assert result["needs_input"] is False
        assert result["response"]  # Non-empty response

    def test_missing_desk_asks(self):
        """When desk_id is missing, graph asks for it."""
        from langchain_core.messages import HumanMessage

        agent = self._get_agent()
        config = {"configurable": {"thread_id": "test_no_desk"}}

        result = agent.invoke(
            {
                "messages": [HumanMessage(content="it's really hot here")],
                "user_id": "test",
                "channel": "chat",
            },
            config,
        )

        assert result["needs_input"] is True
        assert "desk" in result["response"].lower()

    def test_missing_type_asks(self):
        """When complaint type is missing, graph asks for it."""
        from langchain_core.messages import HumanMessage

        agent = self._get_agent()
        config = {"configurable": {"thread_id": "test_no_type"}}

        result = agent.invoke(
            {
                "messages": [HumanMessage(content="there's an issue at desk 25")],
                "user_id": "test",
                "channel": "chat",
            },
            config,
        )

        assert result["needs_input"] is True
        assert "issue" in result["response"].lower() or "hot" in result["response"].lower()

    def test_multi_turn_desk_then_diagnose(self):
        """Multi-turn: ask for desk, then provide it, get diagnosis."""
        from langchain_core.messages import HumanMessage

        agent = self._get_agent()
        config = {"configurable": {"thread_id": "test_multi_turn"}}

        # Turn 1: Missing desk
        r1 = agent.invoke(
            {
                "messages": [HumanMessage(content="it's really hot")],
                "user_id": "test",
                "channel": "whatsapp",
            },
            config,
        )
        assert r1["needs_input"] is True

        # Turn 2: Provide desk
        r2 = agent.invoke(
            {"messages": [HumanMessage(content="25")]},
            config,
        )
        assert r2["needs_input"] is False
        assert r2["response"]  # Got a diagnosis

    def test_compound_complaint_types(self):
        """Compound complaints should capture multiple types."""
        from langchain_core.messages import HumanMessage

        agent = self._get_agent()
        config = {"configurable": {"thread_id": "test_compound"}}

        result = agent.invoke(
            {
                "messages": [HumanMessage(content="cold and noisy at desk 25")],
                "user_id": "test",
                "channel": "chat",
            },
            config,
        )

        # Should complete (has desk + types)
        assert result["needs_input"] is False

        # Check state has both types
        state = agent.get_state(config)
        types = state.values.get("complaint_types", [])
        assert "too_cold" in types
        assert "noise" in types

    def test_whatsapp_channel_formatting(self):
        """WhatsApp channel should use WhatsApp formatter."""
        from langchain_core.messages import HumanMessage

        agent = self._get_agent()
        config = {"configurable": {"thread_id": "test_wa_format"}}

        result = agent.invoke(
            {
                "messages": [HumanMessage(content="Too hot at desk 25")],
                "user_id": "test",
                "channel": "whatsapp",
            },
            config,
        )

        # WhatsApp uses *bold* and degree symbols
        assert "*" in result["response"]

    def test_telegram_channel_formatting(self):
        """Telegram channel should use Telegram formatter."""
        from langchain_core.messages import HumanMessage

        agent = self._get_agent()
        config = {"configurable": {"thread_id": "test_tg_format"}}

        result = agent.invoke(
            {
                "messages": [HumanMessage(content="Too hot at desk 25")],
                "user_id": "test",
                "channel": "telegram",
            },
            config,
        )

        assert "Desk Comfort Report" in result["response"]


# ===================================================================
# History summary
# ===================================================================


class TestComplaintHistorySummary:
    """Tests for get_complaint_history_summary."""

    def test_empty_history(self):
        from app.services.complaint_handler import ComfortComplaintHandler

        handler = ComfortComplaintHandler.__new__(ComfortComplaintHandler)
        handler._desks = {}
        handler._zones = {}
        handler._complaints = {}
        handler._desk_id_map = {}

        summary = handler.get_complaint_history_summary("25")
        assert summary["count"] == 0
        assert summary["escalation_recommended"] is False
        assert summary["last_complaint"] is None

    def test_escalation_at_three(self):
        from app.models.complaint import ComfortComplaint
        from app.services.complaint_handler import ComfortComplaintHandler

        handler = ComfortComplaintHandler.__new__(ComfortComplaintHandler)
        handler._desks = {}
        handler._zones = {}
        handler._desk_id_map = {"25": "25"}
        handler._complaints = {}

        # Add 3 recent complaints
        for i in range(3):
            c = ComfortComplaint(
                desk_id="25",
                complaint_type="too_hot",
                status="diagnosed",
            )
            handler._complaints[c.complaint_id] = c

        summary = handler.get_complaint_history_summary("25", complaint_types=["too_hot"])
        assert summary["count"] == 3
        assert summary["same_type_count"] == 3
        assert summary["escalation_recommended"] is True
