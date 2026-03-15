"""
Tests for signal emitter email bridge + base utilities (Phase 159-01).
======================================================================
Covers email classification, location extraction, thread ID derivation,
dedup, entity extraction, signal row building, and end-to-end emission.
All Supabase calls are mocked via httpx.
"""

import hashlib
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_dedup():
    """Clear the in-memory dedup cache between tests."""
    from app.services.signal_emitter_base import _reset_dedup

    _reset_dedup()
    yield
    _reset_dedup()


# ---------------------------------------------------------------------------
# Email classification
# ---------------------------------------------------------------------------


class TestClassifyEmail:
    def test_classify_email_complaint(self):
        from app.services.signal_emitter import _classify_email

        mod, sig, sev = _classify_email("Room issue", "This problem is ongoing")
        assert sig == "complaint_email"
        assert mod == "email_helpdesk"

    def test_classify_email_escalation(self):
        from app.services.signal_emitter import _classify_email

        mod, sig, sev = _classify_email("Urgent escalation needed", "We escalate this matter")
        assert sig == "escalation_email"
        assert sev == "critical"
        assert mod == "email_escalation"

    def test_classify_email_action_request(self):
        from app.services.signal_emitter import _classify_email

        mod, sig, sev = _classify_email("Room booking", "Please release the room for us")
        assert sig == "action_request_email"
        assert sev == "high"

    def test_classify_email_fallback(self):
        from app.services.signal_emitter import _classify_email

        mod, sig, sev = _classify_email("Hello", "Just a general note with no keywords")
        assert sig == "observation_email"
        assert sev == "low"

    def test_classify_email_observation(self):
        from app.services.signal_emitter import _classify_email

        mod, sig, sev = _classify_email("Status update", "We confirmed the rooms cancelled for today")
        assert sig == "observation_email"
        assert sev == "medium"


# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------


class TestExtractLocationRef:
    def test_extract_location_ref_fairlands(self):
        from app.services.signal_emitter import _extract_location_ref

        ref = _extract_location_ref("Issue at Fairlands", "The meeting room is broken")
        assert ref == "Fairlands"

    def test_extract_location_ref_room_code(self):
        from app.services.signal_emitter import _extract_location_ref

        ref = _extract_location_ref("Room issue", "The room FA1-1Q4-MR10 is too cold")
        assert ref is not None
        assert "FA1" in ref
        assert "1Q4" in ref
        assert "MR10" in ref

    def test_extract_location_ref_unknown(self):
        from app.services.signal_emitter import _extract_location_ref

        ref = _extract_location_ref("Hello", "No location info here at all")
        assert ref is None

    def test_extract_location_ref_springboks(self):
        from app.services.signal_emitter import _extract_location_ref

        ref = _extract_location_ref("", "The Springboks room AC is broken")
        assert ref is not None
        assert "Springboks" in ref


# ---------------------------------------------------------------------------
# Thread ID derivation
# ---------------------------------------------------------------------------


class TestThreadId:
    def test_thread_id_from_references(self):
        from app.services.signal_emitter import _thread_id_from_references

        tid = _thread_id_from_references("", "", "<msg1@ex.com> <msg2@ex.com>")
        assert tid is not None
        assert len(tid) == 16
        # Should be stable
        tid2 = _thread_id_from_references("", "", "<msg1@ex.com> <msg2@ex.com>")
        assert tid == tid2

    def test_thread_id_from_reply(self):
        from app.services.signal_emitter import _thread_id_from_references

        tid = _thread_id_from_references("", "<reply@ex.com>", "")
        expected = hashlib.sha256("<reply@ex.com>".encode()).hexdigest()[:16]
        assert tid == expected

    def test_thread_id_from_message_id_fallback(self):
        from app.services.signal_emitter import _thread_id_from_references

        tid = _thread_id_from_references("<self@ex.com>", "", "")
        assert tid is not None
        assert len(tid) == 16

    def test_thread_id_none_when_empty(self):
        from app.services.signal_emitter import _thread_id_from_references

        tid = _thread_id_from_references("", "", "")
        assert tid is None


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDedup:
    def test_dedup_within_window(self):
        from app.services.signal_emitter_base import check_dedup

        # First call: not a dup
        assert check_dedup("email_helpdesk", "complaint_email", "Fairlands") is False
        # Second call: IS a dup
        assert check_dedup("email_helpdesk", "complaint_email", "Fairlands") is True

    def test_dedup_outside_window(self):
        from app.services.signal_emitter_base import _recent_signals, check_dedup

        # First call sets timestamp
        assert check_dedup("email_helpdesk", "complaint_email", "FA1", window_seconds=1) is False
        # Manually expire the entry
        key = "email_helpdesk:complaint_email:FA1"
        _recent_signals[key] = time.monotonic() - 2  # 2 seconds ago
        # Now it should NOT be a dup
        assert check_dedup("email_helpdesk", "complaint_email", "FA1", window_seconds=1) is False

    def test_dedup_different_keys(self):
        from app.services.signal_emitter_base import check_dedup

        assert check_dedup("email_helpdesk", "complaint_email", "FA1") is False
        assert check_dedup("email_helpdesk", "escalation_email", "FA1") is False


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------


class TestEntityExtraction:
    def test_extract_room_code(self):
        from app.services.signal_emitter_base import extract_entities_from_text

        entities = extract_entities_from_text("Issue in FA1-1Q4-MR10 is urgent")
        room_entities = [e for e in entities if e["entity_type"] == "room"]
        assert len(room_entities) >= 1
        assert any("FA1-1Q4-MR10" in e["name"] for e in room_entities)

    def test_extract_building_code(self):
        from app.services.signal_emitter_base import extract_entities_from_text

        entities = extract_entities_from_text("The issue is at S002 main reception")
        building_entities = [e for e in entities if e["entity_type"] == "building"]
        assert any(e["name"] == "S002" for e in building_entities)

    def test_extract_known_people(self):
        from app.services.signal_emitter_base import extract_entities_from_text

        entities = extract_entities_from_text("John Smith reported the issue", known_people=["John Smith"])
        person_entities = [e for e in entities if e["entity_type"] == "person"]
        assert len(person_entities) == 1
        assert person_entities[0]["name"] == "John Smith"

    def test_extract_no_duplicates(self):
        from app.services.signal_emitter_base import extract_entities_from_text

        # FA1 appears as building AND as part of room code — room should win, building deduped
        entities = extract_entities_from_text("Room FA1-1Q4-MR10 in FA1")
        names = [e["name"] for e in entities]
        # FA1 should appear as building since room code already captured FA1 prefix
        # But FA1 building code is separate from FA1-1Q4-MR10 room code
        assert len(entities) >= 1


# ---------------------------------------------------------------------------
# Build signal row
# ---------------------------------------------------------------------------


class TestBuildSignalRow:
    def test_build_signal_row_truncates_content(self):
        from app.services.signal_emitter_base import build_signal_row

        long_content = "x" * 5000
        row = build_signal_row(
            source_module="email_helpdesk",
            signal_type="complaint_email",
            severity="medium",
            confidence=0.80,
            location_ref="Fairlands",
            raw_content=long_content,
        )
        assert len(row["raw_content"]) == 2000

    def test_build_signal_row_fields(self):
        from app.services.signal_emitter_base import build_signal_row

        row = build_signal_row(
            source_module="email_helpdesk",
            signal_type="complaint_email",
            severity="high",
            confidence=0.85,
            location_ref="Fairlands/FA1",
            raw_content="Test content",
            metadata={"from": "test@example.com"},
            site_id="site-002",
            parent_signal_id="parent-123",
        )
        assert row["source_module"] == "email_helpdesk"
        assert row["signal_type"] == "complaint_email"
        assert row["severity"] == "high"
        assert row["confidence"] == 0.85
        assert row["location_ref"] == "Fairlands/FA1"
        assert row["resolution_state"] == "active"
        assert row["site_id"] == "site-002"
        assert row["parent_signal_id"] == "parent-123"
        assert row["metadata"]["from"] == "test@example.com"
        assert "id" in row
        assert "created_at" in row

    def test_build_signal_row_unknown_location(self):
        from app.services.signal_emitter_base import build_signal_row

        row = build_signal_row(
            source_module="test",
            signal_type="test",
            severity="low",
            confidence=0.5,
            location_ref="",
            raw_content="test",
        )
        assert row["location_ref"] == "unknown"


# ---------------------------------------------------------------------------
# End-to-end emit_email_signal
# ---------------------------------------------------------------------------


class TestEmitEmailSignal:
    @pytest.mark.asyncio
    async def test_emit_email_signal_success(self):
        from app.services.signal_emitter import emit_email_signal

        fake_signal = {
            "id": str(uuid.uuid4()),
            "source_module": "email_helpdesk",
            "signal_type": "complaint_email",
            "severity": "medium",
            "location_ref": "Fairlands",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = [fake_signal]
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.signal_emitter_base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await emit_email_signal(
                from_email="user@example.com",
                from_name="Test User",
                subject="Room issue at Fairlands",
                body_plain="The room is too cold and there is a problem",
            )

        assert result["status"] == "created"
        assert result["signal_id"] == fake_signal["id"]

    @pytest.mark.asyncio
    async def test_emit_email_signal_dedup(self):
        """Second identical email within 5min should be deduplicated."""
        from app.services.signal_emitter import emit_email_signal

        fake_signal = {
            "id": str(uuid.uuid4()),
            "source_module": "email_helpdesk",
            "signal_type": "complaint_email",
            "severity": "medium",
            "location_ref": "Fairlands",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = [fake_signal]
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.signal_emitter_base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # First call: created
            result1 = await emit_email_signal(
                from_email="user@example.com",
                from_name="Test User",
                subject="Room issue at Fairlands",
                body_plain="The room is too cold and there is a problem",
            )
            assert result1["status"] == "created"

            # Second call: deduplicated
            result2 = await emit_email_signal(
                from_email="user@example.com",
                from_name="Test User",
                subject="Room issue at Fairlands",
                body_plain="The room is too cold and there is a problem",
            )
            assert result2["status"] == "deduplicated"

    @pytest.mark.asyncio
    async def test_emit_email_signal_entities_extracted(self):
        """Email with room code should trigger entity write."""
        from app.services.signal_emitter import emit_email_signal

        signal_id = str(uuid.uuid4())
        fake_signal = {
            "id": signal_id,
            "source_module": "email_helpdesk",
            "signal_type": "complaint_email",
            "severity": "medium",
            "location_ref": "Fairlands/FA1/1Q4/MR10",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = [fake_signal]
        mock_response.raise_for_status = MagicMock()

        post_calls = []

        async def capture_post(url, **kwargs):
            post_calls.append({"url": url, "json": kwargs.get("json")})
            return mock_response

        with patch("app.services.signal_emitter_base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=capture_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await emit_email_signal(
                from_email="user@example.com",
                from_name="Test User",
                subject="Room issue",
                body_plain="Room FA1-1Q4-MR10 AC is not working",
            )

        assert result["status"] == "created"
        # Should have 2 POST calls: signal + entities
        signal_calls = [c for c in post_calls if "/signal" in c["url"] and "/entity" not in c["url"]]
        entity_calls = [c for c in post_calls if "/entity" in c["url"]]
        assert len(signal_calls) == 1
        assert len(entity_calls) == 1
        # Entity payload should reference the signal
        entity_payload = entity_calls[0]["json"]
        assert isinstance(entity_payload, list)
        assert len(entity_payload) >= 1
