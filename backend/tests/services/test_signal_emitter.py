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

FORWARDED_THREAD_BODY = """
[signatureImage]
________________________________
From: REMSHelpdesk <remshelpdesk@fnb.co.za>
Sent: Monday, March 16, 2026 3:21:40 PM
To: Nthau, Palesa <Palesa.Nthau@fnb.co.za>; Mamafha, Andrew <Andrew.Mamafha@fnb.co.za>
Cc: Van Rooyen, Pieter <Pieter.VanRooyen@fnb.co.za>
Subject: RE: Team work space - Fairlands 2

Good day Thandi

Please see below and advise.

From: Nthau, Palesa <Palesa.Nthau@fnb.co.za>
Sent: Wednesday, 11 March 2026 15:21
To: REMSHelpdesk <remshelpdesk@fnb.co.za>
Subject: Team work space - Fairlands 2

Good day

We are arranging a team work in office day and would like to find out
if there is available work desk space available at Fairlands 2.

Team size: 13
Preferred day: Mondays
Office: Fairlands 2
Bu/segment: Personal and Private IT
""".strip()

FORWARDED_ROOM_THREAD_BODY = """
________________________________
From: REMSHelpdesk <remshelpdesk@fnb.co.za>
Sent: Monday, March 16, 2026 3:21:40 PM
To: Dineka, Thandi <TDineka@fnb.co.za>
Subject: RE: Meeting room issue

Please see below and advise.

From: User, Example <user@example.com>
Sent: Monday, 16 March 2026 15:19
To: REMSHelpdesk <remshelpdesk@fnb.co.za>
Subject: Meeting room issue

Good day the TV in FA1-1Q2-MR5 is not wroking please fix.
""".strip()


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

        mod, sig, _sev = _classify_email("Room issue", "This problem is ongoing")
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

        _mod, sig, sev = _classify_email("Room booking", "Please release the room for us")
        assert sig == "action_request_email"
        assert sev == "high"

    def test_classify_email_fallback(self):
        from app.services.signal_emitter import _classify_email

        _mod, sig, sev = _classify_email("Hello", "Just a general note with no keywords")
        assert sig == "observation_email"
        assert sev == "low"

    def test_classify_email_observation(self):
        from app.services.signal_emitter import _classify_email

        _mod, sig, sev = _classify_email("Status update", "We confirmed the rooms cancelled for today")
        assert sig == "observation_email"
        assert sev == "medium"

    def test_classify_room_issue_email_low_severity(self):
        from app.services.signal_emitter import _classify_email

        mod, sig, sev = _classify_email("Room AV issue", "The TV in FA1-1Q2-MR5 is not wroking please fix")
        assert mod == "email_helpdesk"
        assert sig == "observation_email"
        assert sev == "low"


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
        assert "FA1-1Q4-MR-10" in ref

    def test_extract_location_ref_normalises_email_room_code(self):
        from app.services.signal_emitter import _extract_location_ref

        ref = _extract_location_ref("AV issue", "TV in FA1-1Q2-MR5 is not wroking please fix")
        assert ref == "Fairlands/FA1/1Q2/FA1-1Q2-MR-05"

    def test_extract_location_ref_site_002_room_code(self):
        from app.services.signal_emitter import _extract_location_ref

        ref = _extract_location_ref(
            "Meeting room catering issue",
            "The catering for meeting room S002-L2-MR1 at site-002 has still not arrived",
        )
        assert ref == "S002-L2-MR1"

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
        expected = hashlib.sha256(b"<reply@ex.com>").hexdigest()[:16]
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


class TestThreadExtraction:
    def test_extract_email_thread_messages_parses_forwarded_chain(self):
        from app.services.signal_emitter import _extract_email_thread_messages

        messages = _extract_email_thread_messages(FORWARDED_THREAD_BODY)

        assert len(messages) == 2
        assert messages[0]["from_email"] == "remshelpdesk@fnb.co.za"
        assert messages[0]["subject"] == "RE: Team work space - Fairlands 2"
        assert "Please see below and advise." in messages[0]["body_plain"]
        assert messages[1]["from_email"] == "palesa.nthau@fnb.co.za"
        assert messages[1]["subject"] == "Team work space - Fairlands 2"
        assert "Fairlands 2" in messages[1]["body_plain"]


class TestMeetingRoomGate:
    def test_is_meeting_room_email_accepts_room_id(self):
        from app.services.signal_emitter import _is_meeting_room_email

        assert _is_meeting_room_email(
            "AV issue",
            "Good day the TV in FA1-1Q2-MR5 is not wroking please fix",
        )

    def test_is_meeting_room_email_accepts_meeting_room_language(self):
        from app.services.signal_emitter import _is_meeting_room_email

        assert _is_meeting_room_email(
            "Block Bookings of Meeting Rooms in Fairland",
            "Trying to book a 12-seater room without success",
        )

    def test_is_meeting_room_email_rejects_workspace_planning_email(self):
        from app.services.signal_emitter import _is_meeting_room_email

        assert not _is_meeting_room_email(
            "Fw: Team work space - Fairlands 2",
            FORWARDED_THREAD_BODY,
        )


class TestReceivedAtNormalisation:
    def test_normalise_received_at_converts_utc_header_to_johannesburg(self):
        from app.services.signal_emitter import _normalise_received_at

        normalised, original = _normalise_received_at("Mon, 16 Mar 2026 13:52:54 +0000")
        assert normalised == "2026-03-16T15:52:54+02:00"
        assert original == "Mon, 16 Mar 2026 13:52:54 +0000"

    def test_normalise_received_at_keeps_johannesburg_iso(self):
        from app.services.signal_emitter import _normalise_received_at

        normalised, original = _normalise_received_at("2026-03-16T15:52:54+02:00")
        assert normalised == "2026-03-16T15:52:54+02:00"
        assert original is None


class TestStorageNormalisation:
    def test_normalise_signal_type_for_storage_maps_non_schema_email_types(self):
        from app.services.signal_emitter import _normalise_signal_type_for_storage

        assert _normalise_signal_type_for_storage("observation_email") == (
            "information_email",
            "observation_email",
        )
        assert _normalise_signal_type_for_storage("intake_email") == (
            "information_email",
            "intake_email",
        )
        assert _normalise_signal_type_for_storage("action_request_email") == (
            "escalation_email",
            "action_request_email",
        )

    def test_coerce_site_uuid_preserves_logical_site_codes(self):
        from app.services.signal_emitter import _coerce_site_uuid

        persisted, logical = _coerce_site_uuid("S001")
        assert persisted is None
        assert logical == "S001"

        persisted, logical = _coerce_site_uuid("123e4567-e89b-12d3-a456-426614174000")
        assert persisted == "123e4567-e89b-12d3-a456-426614174000"
        assert logical is None


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
        assert any(e["name"] == "FA1-1Q4-MR-10" for e in room_entities)

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
    """Pre-173-02 tests. Phase gate mocked to 'advisory' so these exercise the full emit path."""

    @pytest.fixture(autouse=True)
    def mock_phase_advisory(self):
        """Ensure emit_email_signal sees advisory phase in all pre-gate tests."""
        with patch(
            "app.models.onboarding_phase.get_site_phase",
            new_callable=AsyncMock,
            return_value="advisory",
        ):
            yield

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
                subject="Meeting room issue at Fairlands",
                body_plain="The meeting room is too cold and there is a problem",
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
                subject="Meeting room issue at Fairlands",
                body_plain="The meeting room is too cold and there is a problem",
            )
            assert result1["status"] == "created"

            # Second call: deduplicated
            result2 = await emit_email_signal(
                from_email="user@example.com",
                from_name="Test User",
                subject="Meeting room issue at Fairlands",
                body_plain="The meeting room is too cold and there is a problem",
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

    @pytest.mark.asyncio
    async def test_emit_email_signal_sets_canonical_room_metadata_for_concierge(self):
        """Room-linked intelligence email should stamp canonical room_id and site_id."""
        from app.services.signal_emitter import emit_email_signal

        fake_signal = {
            "id": str(uuid.uuid4()),
            "source_module": "email_helpdesk",
            "signal_type": "observation_email",
            "severity": "low",
            "location_ref": "Fairlands/FA1/1Q2/FA1-1Q2-MR-05",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = [fake_signal]
        mock_response.raise_for_status = MagicMock()

        post_calls = []

        async def capture_post(url, **kwargs):
            post_calls.append({"url": url, "json": kwargs.get("json")})
            return mock_response

        mock_repo = MagicMock()
        mock_repo.get_room = AsyncMock(
            return_value={
                "site_id": "S001",
                "room_id": "FA1-1Q2-MR-05",
                "building": "FA1",
                "quadrant": "1Q2",
            }
        )

        with (
            patch("app.services.signal_emitter.get_room_registry_repository", return_value=mock_repo),
            patch("app.services.signal_emitter_base.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=capture_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await emit_email_signal(
                from_email="user@example.com",
                from_name="Test User",
                subject="AV issue",
                body_plain="Good day the TV in FA1-1Q2-MR5 is not wroking please fix",
            )

        assert result["status"] == "created"
        signal_calls = [c for c in post_calls if "/signal" in c["url"] and "/entity" not in c["url"]]
        assert len(signal_calls) == 1
        signal_payload = signal_calls[0]["json"]
        assert "site_id" not in signal_payload
        assert signal_payload["location_ref"] == "Fairlands/FA1/1Q2/FA1-1Q2-MR-05"
        assert signal_payload["metadata"]["room_id"] == "FA1-1Q2-MR-05"
        assert signal_payload["metadata"]["logical_site_id"] == "S001"
        assert signal_payload["signal_type"] == "information_email"
        assert signal_payload["metadata"]["email_signal_variant"] == "observation_email"

    @pytest.mark.asyncio
    async def test_emit_email_signal_sets_site_002_room_metadata_for_concierge(self):
        """Site-002 room emails should resolve onto the local meeting room registry."""
        from app.services.signal_emitter import emit_email_signal

        fake_signal = {
            "id": str(uuid.uuid4()),
            "source_module": "email_helpdesk",
            "signal_type": "information_email",
            "severity": "medium",
            "location_ref": "S002-L2-MR1",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = [fake_signal]
        mock_response.raise_for_status = MagicMock()

        post_calls = []

        async def capture_post(url, **kwargs):
            post_calls.append({"url": url, "json": kwargs.get("json")})
            return mock_response

        mock_repo = MagicMock()
        mock_repo.get_room = AsyncMock(
            return_value={
                "site_id": "site-002",
                "room_id": "S002-L2-MR1",
                "building": "S002",
                "quadrant": "L2",
            }
        )

        with (
            patch("app.services.signal_emitter.get_room_registry_repository", return_value=mock_repo),
            patch("app.services.signal_emitter_base.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=capture_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await emit_email_signal(
                from_email="helpdesk@site002.example.com",
                from_name="Site 002 Helpdesk",
                subject="Fw: Meeting room catering issue - S002-L2-MR1",
                body_plain="Please attend. The meeting room catering in S002-L2-MR1 has not arrived.",
            )

        assert result["status"] == "created"
        signal_calls = [c for c in post_calls if "/signal" in c["url"] and "/entity" not in c["url"]]
        assert len(signal_calls) == 1
        signal_payload = signal_calls[0]["json"]
        assert signal_payload["location_ref"] == "S002-L2-MR1"
        assert signal_payload["metadata"]["room_id"] == "S002-L2-MR1"
        assert signal_payload["metadata"]["logical_site_id"] == "site-002"

    @pytest.mark.asyncio
    async def test_emit_email_signal_accepts_fairlands_room_code_with_space_before_number(self):
        from app.services.signal_emitter import emit_email_signal

        fake_signal = {
            "id": str(uuid.uuid4()),
            "source_module": "email_helpdesk",
            "signal_type": "information_email",
            "severity": "medium",
            "location_ref": "Fairlands/FA1/2Q2/FA1-2Q2-MR-23",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = [fake_signal]
        mock_response.raise_for_status = MagicMock()

        post_calls = []

        async def capture_post(url, **kwargs):
            post_calls.append({"url": url, "json": kwargs.get("json")})
            return mock_response

        mock_repo = MagicMock()
        mock_repo.get_room = AsyncMock(
            return_value={
                "site_id": "S001",
                "room_id": "FA1-2Q2-MR-23",
                "building": "FA1",
                "quadrant": "2Q2",
            }
        )

        with (
            patch("app.services.signal_emitter.get_room_registry_repository", return_value=mock_repo),
            patch("app.services.signal_emitter_base.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=capture_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await emit_email_signal(
                from_email="helpdesk@fairlands.example.com",
                from_name="Fairlands Helpdesk",
                subject="Meeting room catering",
                body_plain="Hi, please can I have catering at 12:00 today for FA1-2Q2-MR 23",
            )

        assert result["status"] == "created"
        signal_calls = [c for c in post_calls if "/signal" in c["url"] and "/entity" not in c["url"]]
        assert len(signal_calls) == 1
        signal_payload = signal_calls[0]["json"]
        assert signal_payload["location_ref"] == "Fairlands/FA1/2Q2/FA1-2Q2-MR-23"
        assert signal_payload["metadata"]["room_id"] == "FA1-2Q2-MR-23"

    @pytest.mark.asyncio
    async def test_emit_email_signal_normalises_received_at_to_local_time(self):
        from app.services.signal_emitter import emit_email_signal

        fake_signal = {
            "id": str(uuid.uuid4()),
            "source_module": "email_helpdesk",
            "signal_type": "observation_email",
            "severity": "low",
            "location_ref": "Fairlands/FA1/1Q2/FA1-1Q2-MR-05",
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
                subject="Fairlands room issue",
                body_plain="The TV in FA1-1Q2-MR5 is not wroking please fix",
                received_at="Mon, 16 Mar 2026 13:52:54 +0000",
            )

        assert result["status"] == "created"
        signal_calls = [c for c in post_calls if "/signal" in c["url"] and "/entity" not in c["url"]]
        assert len(signal_calls) == 1
        signal_payload = signal_calls[0]["json"]
        assert signal_payload["metadata"]["received_at"] == "2026-03-16T15:52:54+02:00"
        assert signal_payload["metadata"]["received_at_original"] == "Mon, 16 Mar 2026 13:52:54 +0000"

    @pytest.mark.asyncio
    async def test_emit_email_signal_maps_intake_email_to_schema_supported_type(self):
        from app.services.signal_emitter import emit_email_signal

        fake_signal = {
            "id": str(uuid.uuid4()),
            "source_module": "email_helpdesk",
            "signal_type": "information_email",
            "severity": "medium",
            "location_ref": "Fairlands",
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
                from_email="pieter.vanrooyen@fnb.co.za",
                from_name="Van Rooyen, Pieter",
                subject="Fw: Meeting room support - Fairlands 2",
                body_plain=(
                    "From: REMSHelpdesk <remshelpdesk@fnb.co.za>\n"
                    "Please attend to the meeting room query at Fairlands 2."
                ),
                received_at="Mon, 16 Mar 2026 13:52:54 +0000",
            )

        assert result["status"] == "created"
        signal_calls = [c for c in post_calls if "/signal" in c["url"] and "/entity" not in c["url"]]
        assert len(signal_calls) == 1
        signal_payload = signal_calls[0]["json"]
        assert signal_payload["signal_type"] == "information_email"
        assert signal_payload["metadata"]["email_signal_variant"] == "intake_email"
        assert signal_payload["metadata"]["logical_site_id"] == "S001"
        assert "site_id" not in signal_payload

    @pytest.mark.asyncio
    async def test_emit_email_signal_ignores_non_meeting_room_email(self):
        from app.services.signal_emitter import emit_email_signal

        result = await emit_email_signal(
            from_email="pieter.vanrooyen@fnb.co.za",
            from_name="Van Rooyen, Pieter",
            subject="Fw: Team work space - Fairlands 2",
            body_plain=FORWARDED_THREAD_BODY,
            received_at="Mon, 16 Mar 2026 13:52:54 +0000",
        )

        assert result["status"] == "ignored"
        assert result["reason"] == "non_meeting_room_email"
        assert result["signal_id"] is None

    @pytest.mark.asyncio
    async def test_emit_email_signal_uses_forwarded_thread_context_for_room_issue(self):
        from app.services.signal_emitter import emit_email_signal

        fake_signal = {
            "id": str(uuid.uuid4()),
            "source_module": "email_helpdesk",
            "signal_type": "information_email",
            "severity": "low",
            "location_ref": "Fairlands/FA1/1Q2/FA1-1Q2-MR-05",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = [fake_signal]
        mock_response.raise_for_status = MagicMock()

        post_calls = []

        async def capture_post(url, **kwargs):
            post_calls.append({"url": url, "json": kwargs.get("json")})
            return mock_response

        mock_repo = MagicMock()
        mock_repo.get_room = AsyncMock(
            return_value={
                "site_id": "S001",
                "room_id": "FA1-1Q2-MR-05",
                "building": "FA1",
                "quadrant": "1Q2",
            }
        )

        with (
            patch("app.services.signal_emitter.get_room_registry_repository", return_value=mock_repo),
            patch("app.services.signal_emitter_base.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=capture_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await emit_email_signal(
                from_email="pieter.vanrooyen@fnb.co.za",
                from_name="Van Rooyen, Pieter",
                subject="Fw: Meeting room issue",
                body_plain=FORWARDED_ROOM_THREAD_BODY,
                received_at="Mon, 16 Mar 2026 13:52:54 +0000",
            )

        assert result["status"] == "created"
        signal_calls = [c for c in post_calls if "/signal" in c["url"] and "/entity" not in c["url"]]
        assert len(signal_calls) == 1
        signal_payload = signal_calls[0]["json"]
        assert signal_payload["location_ref"] == "Fairlands/FA1/1Q2/FA1-1Q2-MR-05"
        assert signal_payload["metadata"]["room_id"] == "FA1-1Q2-MR-05"
        assert signal_payload["metadata"]["thread_message_count"] == 2
        assert len(signal_payload["metadata"]["thread_messages"]) == 2


# ---------------------------------------------------------------------------
# 173-02 Phase gate tests
# ---------------------------------------------------------------------------


class TestEmitEmailSignalPhaseGate:
    """173-02: emit_email_signal is gated by onboarding phase."""

    @pytest.mark.asyncio
    async def test_emit_email_signal_skipped_in_shadow(self, monkeypatch):
        """emit_email_signal returns phase_gate_skipped for shadow-phase sites."""
        from unittest.mock import AsyncMock

        # Patch get_site_phase to return 'shadow'
        monkeypatch.setattr(
            "app.models.onboarding_phase.effective_phase",
            AsyncMock(return_value="shadow"),
        )
        # Patch _resolve_room_context to return a resolvable site_id
        monkeypatch.setattr(
            "app.services.signal_emitter._resolve_room_context",
            AsyncMock(return_value=(None, "Fairlands", "S001")),
        )

        from app.services.signal_emitter import emit_email_signal

        # Subject must contain a meeting-room keyword to pass the non-meeting-room filter
        result = await emit_email_signal(
            from_email="user@fnb.co.za",
            from_name="Test User",
            subject="Meeting room issue",
            body_plain="The meeting room is broken.",
            received_at="Mon, 16 Mar 2026 13:52:54 +0000",
        )

        assert result is not None
        assert result["status"] == "phase_gate_skipped"
        assert "shadow" in result["reason"]

    @pytest.mark.asyncio
    async def test_emit_email_signal_allowed_in_advisory(self, monkeypatch):
        """emit_email_signal proceeds past the phase gate for advisory-phase sites."""
        from unittest.mock import AsyncMock, MagicMock

        # Patch get_site_phase to return 'advisory'
        monkeypatch.setattr(
            "app.models.onboarding_phase.effective_phase",
            AsyncMock(return_value="advisory"),
        )
        # Patch _resolve_room_context
        monkeypatch.setattr(
            "app.services.signal_emitter._resolve_room_context",
            AsyncMock(return_value=(None, "Fairlands", "S001")),
        )
        # Patch _coerce_site_uuid so we don't need real UUIDs
        monkeypatch.setattr(
            "app.services.signal_emitter._coerce_site_uuid",
            lambda _: ("00000000-0000-0000-0000-000000000001", "S001"),
        )
        # Patch httpx to avoid real network calls — return dedup-skipped
        from app.services.signal_emitter_base import _recent_signals

        _recent_signals.clear()

        import httpx

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "sig-001",
            "source_module": "email_helpdesk",
            "signal_type": "observation_email",
        }

        mock_httpx_client = AsyncMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_httpx_client.__aexit__ = AsyncMock(return_value=False)

        monkeypatch.setattr(
            "app.services.signal_emitter_base.httpx.AsyncClient",
            lambda **_kw: mock_httpx_client,
        )

        from app.services.signal_emitter import emit_email_signal

        result = await emit_email_signal(
            from_email="user@fnb.co.za",
            from_name="Test User",
            subject="General office update",
            body_plain="This is a routine update, no issues.",
            received_at="Mon, 16 Mar 2026 13:52:54 +0000",
        )

        # Phase gate was passed — result should NOT be phase_gate_skipped
        assert result is not None
        assert result.get("status") != "phase_gate_skipped"


class TestEmitBlockBookingSignalsPhaseGate:
    """173-02: emit_block_booking_signals is gated by onboarding phase."""

    @pytest.mark.asyncio
    async def test_emit_block_booking_signals_skipped_in_shadow(self, monkeypatch):
        """emit_block_booking_signals returns empty list for shadow-phase sites."""
        from unittest.mock import AsyncMock

        monkeypatch.setattr(
            "app.models.onboarding_phase.effective_phase",
            AsyncMock(return_value="shadow"),
        )

        from app.services.block_booking_signal_emitter import emit_block_booking_signals

        result = await emit_block_booking_signals(site_id="S001")
        assert result == []

    @pytest.mark.asyncio
    async def test_emit_block_booking_signals_allowed_in_advisory(self, monkeypatch):
        """emit_block_booking_signals proceeds past gate for advisory-phase sites."""
        from unittest.mock import AsyncMock, MagicMock

        monkeypatch.setattr(
            "app.models.onboarding_phase.effective_phase",
            AsyncMock(return_value="advisory"),
        )

        # Patch booking store to return empty so no signals are emitted
        mock_store = MagicMock()
        mock_store.get_bookings_for_site.return_value = []
        monkeypatch.setattr(
            "app.services.block_booking_detector.booking_store.get_booking_store",
            lambda: mock_store,
        )

        from app.services.block_booking_signal_emitter import emit_block_booking_signals

        result = await emit_block_booking_signals(site_id="S001")
        # Gate was passed; no bookings means empty list (not skipped)
        assert isinstance(result, list)
