"""
Tests for signal replay tool (Phase 159-04).
=============================================
Unit tests mock Supabase writes. Acceptance test (integration) requires
a live Supabase connection and is marked with ``@pytest.mark.integration``.
"""

import logging
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


class PostRecorder:
    """Records httpx.post calls and returns mock responses."""

    def __init__(self):
        self.calls = []

    async def __call__(self, url, *, headers=None, json=None, **kwargs):
        self.calls.append({"url": url, "json": json})
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        # Return the posted JSON as if Supabase created it
        if isinstance(json, list):
            resp.json.return_value = json
        elif isinstance(json, dict):
            resp.json.return_value = [json]
        else:
            resp.json.return_value = [{}]
        return resp


# ---------------------------------------------------------------------------
# Test: load case data
# ---------------------------------------------------------------------------


class TestLoadCaseData:
    @pytest.mark.asyncio
    async def test_load_case_fairlands(self):
        from app.services.signal_replay_tool import _load_case_data

        data = await _load_case_data("fairlands")
        assert "emails" in data
        assert "ghost_bookings" in data
        assert "block_bookings" in data
        assert "occupancy_events" in data
        assert len(data["emails"]) >= 3
        assert len(data["ghost_bookings"]) >= 2
        assert len(data["block_bookings"]) >= 1
        assert len(data["occupancy_events"]) >= 2

    @pytest.mark.asyncio
    async def test_load_case_unknown(self):
        from app.services.signal_replay_tool import _load_case_data

        with pytest.raises(ValueError, match="Unknown replay case"):
            await _load_case_data("nonexistent_case")


# ---------------------------------------------------------------------------
# Test: replay emails
# ---------------------------------------------------------------------------


class TestReplayEmails:
    @pytest.mark.asyncio
    async def test_replay_emails_calls_emitter(self):
        from app.services.signal_replay_tool import _replay_emails

        emails = [
            {
                "from_email": "test@test.com",
                "from_name": "Test",
                "subject": "Test complaint issue",
                "body_plain": "Problem with FA1-1Q4-MR10",
                "message_id": "<msg-1>",
                "in_reply_to": "",
                "references": "",
                "to": ["help@test.com"],
                "cc": [],
                "received_at": "2026-03-01T09:00:00Z",
            },
            {
                "from_email": "test2@test.com",
                "from_name": "Test2",
                "subject": "Another issue at Fairlands",
                "body_plain": "Rooms not available",
                "message_id": "<msg-2>",
                "received_at": "2026-03-02T10:00:00Z",
            },
        ]

        recorder = PostRecorder()
        with patch("httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.post = recorder
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = instance

            results = await _replay_emails(emails, None, verbose=False)

        assert len(results) == 2
        # Each email produces at least 1 httpx call (signal write)
        assert len(recorder.calls) >= 2


# ---------------------------------------------------------------------------
# Test: replay bookings
# ---------------------------------------------------------------------------


class TestReplayBookings:
    @pytest.fixture(autouse=True)
    def mock_phase_advisory(self):
        """Phase gate mocked advisory so replay tests exercise full emit path."""
        with patch(
            "app.models.onboarding_phase.get_site_phase",
            new_callable=AsyncMock,
            return_value="advisory",
        ):
            yield

    @pytest.mark.asyncio
    async def test_replay_bookings_calls_both_emitters(self):
        from app.services.signal_replay_tool import _replay_bookings

        ghost = [
            {
                "room_code": "FA1-1Q4-MR10",
                "booking_title": "Test Meeting",
                "booked_by": "Alice",
                "start_time": "2026-03-01T08:00:00Z",
                "end_time": "2026-03-01T17:00:00Z",
                "occupancy_detected": False,
                "site_id": "site-fairlands",
            }
        ]
        block = [
            {
                "room_code": "FA1-1Q4-MR10",
                "booked_by": "Bob",
                "pattern": "daily",
                "booking_count": 10,
                "date_range": "2026-03-01 to 2026-03-10",
                "site_id": "site-fairlands",
            }
        ]

        recorder = PostRecorder()
        with patch("httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.post = recorder
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = instance

            results = await _replay_bookings(ghost, block, None, verbose=False)

        # Should have 2 results (1 ghost + 1 block)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Test: replay occupancy
# ---------------------------------------------------------------------------


class TestReplayOccupancy:
    @pytest.mark.asyncio
    async def test_replay_occupancy_calls_emitter(self):
        from app.services.signal_replay_tool import _replay_occupancy

        events = [
            {
                "room_code": "FA1-1Q4-MR10",
                "booking_active": True,
                "sensor_occupancy": 0,
                "expected_occupancy": 8,
                "timestamp": "2026-03-01T10:00:00Z",
                "site_id": "site-fairlands",
            },
            {
                "room_code": "FA1-1Q4-MR08",
                "booking_active": True,
                "sensor_occupancy": 0,
                "expected_occupancy": 6,
                "timestamp": "2026-03-02T14:00:00Z",
                "site_id": "site-fairlands",
            },
        ]

        recorder = PostRecorder()
        with patch("httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.post = recorder
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = instance

            results = await _replay_occupancy(events, None, verbose=False)

        assert len(results) == 2


# ---------------------------------------------------------------------------
# Test: replay_case returns summary
# ---------------------------------------------------------------------------


class TestReplayCase:
    @pytest.mark.asyncio
    async def test_replay_case_returns_summary(self):
        from app.services.signal_replay_tool import replay_case

        recorder = PostRecorder()
        with patch("httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.post = recorder
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = instance

            # Mock _run_correlation to avoid needing a real DB
            with patch(
                "app.services.signal_replay_tool._run_correlation",
                new_callable=AsyncMock,
                return_value={
                    "clusters_formed": 1,
                    "cluster_states": ["escalated"],
                    "cards_generated": 2,
                    "errors": [],
                },
            ):
                result = await replay_case("fairlands")

        assert result["case"] == "fairlands"
        assert "signals_emitted" in result
        assert result["signals_emitted"] >= 1
        assert "signals_deduped" in result
        assert result["clusters_formed"] == 1
        assert result["cluster_states"] == ["escalated"]
        assert result["cards_generated"] == 2
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_replay_case_unknown_raises(self):
        from app.services.signal_replay_tool import replay_case

        with pytest.raises(ValueError, match="Unknown replay case"):
            await replay_case("nonexistent")


# ---------------------------------------------------------------------------
# Test: time window filtering
# ---------------------------------------------------------------------------


class TestTimeWindow:
    @pytest.mark.asyncio
    async def test_replay_with_time_window(self):
        """Only events within the time window should be processed."""
        from app.services.signal_replay_tool import _replay_emails

        emails = [
            {
                "from_email": "a@test.com",
                "from_name": "A",
                "subject": "Early complaint issue",
                "body_plain": "Problem at FA1",
                "message_id": "<early>",
                "received_at": "2026-03-01T09:00:00Z",
            },
            {
                "from_email": "b@test.com",
                "from_name": "B",
                "subject": "Late complaint issue",
                "body_plain": "Problem at FA1",
                "message_id": "<late>",
                "received_at": "2026-03-07T09:00:00Z",
            },
        ]

        # Window only includes the first email
        window = {
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-03T00:00:00Z",
        }

        recorder = PostRecorder()
        with patch("httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.post = recorder
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = instance

            results = await _replay_emails(emails, window, verbose=False)

        # Only 1 email is within the window
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Test: verbose logging
# ---------------------------------------------------------------------------


class TestVerboseLogging:
    @pytest.mark.asyncio
    async def test_replay_verbose_logging(self, caplog):
        """verbose=True should produce INFO log entries."""
        from app.services.signal_replay_tool import _replay_emails

        emails = [
            {
                "from_email": "a@test.com",
                "from_name": "A",
                "subject": "Test issue complaint",
                "body_plain": "FA1 room problem",
                "message_id": "<v1>",
                "received_at": "2026-03-01T09:00:00Z",
            },
        ]

        recorder = PostRecorder()
        with patch("httpx.AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.post = recorder
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = instance

            with caplog.at_level(logging.INFO, logger="app.services.signal_replay_tool"):
                await _replay_emails(emails, None, verbose=True)

        assert any("emitting email" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Test: in_time_window helper
# ---------------------------------------------------------------------------


class TestInTimeWindow:
    def test_no_window_always_true(self):
        from app.services.signal_replay_tool import _in_time_window

        assert _in_time_window("2026-03-01T09:00:00Z", None) is True

    def test_within_window(self):
        from app.services.signal_replay_tool import _in_time_window

        window = {"start": "2026-03-01T00:00:00Z", "end": "2026-03-05T00:00:00Z"}
        assert _in_time_window("2026-03-02T12:00:00Z", window) is True

    def test_outside_window(self):
        from app.services.signal_replay_tool import _in_time_window

        window = {"start": "2026-03-01T00:00:00Z", "end": "2026-03-03T00:00:00Z"}
        assert _in_time_window("2026-03-07T12:00:00Z", window) is False


# ---------------------------------------------------------------------------
# Acceptance test (integration — requires live Supabase)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFairlandsEndToEnd:
    """THE acceptance test: replay Fairlands case → signals → clusters → escalated → routed card.

    Requires Supabase running. Run with: ``pytest -m integration``
    """

    @pytest.mark.asyncio
    async def test_fairlands_end_to_end(self):
        """Full replay of Fairlands scenario validates the complete pipeline."""
        import psycopg2

        from app.config.settings import settings
        from app.services.signal_replay_tool import replay_case

        db_url = settings.supabase_db_url
        if not db_url:
            pytest.skip("No Supabase DB URL — skipping integration test")

        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
        except Exception:
            pytest.skip("Cannot connect to Supabase — skipping integration test")

        # 1. Clear test signals (those from replay fixture)
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM signal WHERE metadata->>'source' = 'intelligence_intake' "
                "OR source_module IN ('booking_system', 'occupancy_sensor')"
            )
            cur.close()
        except Exception:
            pass
        finally:
            conn.close()

        # 2. Run replay
        result = await replay_case("fairlands")

        # 3. Verify signals emitted (4 emails + 3 ghost + 1 block + 3 occupancy = 11,
        #    minus any deduplication from same-room signals within windows)
        assert result["signals_emitted"] >= 8, f"Expected >= 8 signals emitted, got {result['signals_emitted']}"

        # 4. Verify clusters formed
        assert result["clusters_formed"] >= 1, f"Expected >= 1 cluster, got {result['clusters_formed']}"

        # 5. Check cluster state in DB
        try:
            conn2 = psycopg2.connect(db_url)
            conn2.autocommit = True
            cur = conn2.cursor()

            # At least one escalated cluster
            cur.execute(
                "SELECT id, state, escalation_level FROM issue_cluster "
                "WHERE state = 'escalated' ORDER BY created_at DESC LIMIT 5"
            )
            escalated = cur.fetchall()

            # 6. Check for dashboard cards
            cur.execute("SELECT id, cluster_id, routed_to FROM dashboard_card ORDER BY created_at DESC LIMIT 10")
            cards = cur.fetchall()

            cur.close()
            conn2.close()
        except Exception as exc:
            pytest.skip(f"DB query failed: {exc}")

        assert len(escalated) >= 1, "Expected at least one escalated cluster"
        assert len(cards) >= 1, "Expected at least one dashboard card"
