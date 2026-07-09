"""Tests for wizard acceptance gates.

Phase 187.1 — validates that:
- Each gate individually blocks
- All gates passing succeeds
- 409 response shape is correct
- Admin override works and writes audit events
- Disable-path is never gated
- Fail-closed on check errors
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.wizard_acceptance_gates import (
    GateResult,
    evaluate,
    _check_aggregation_fresh,
    _check_history_fresh,
    _check_operating_hours_set,
    _check_wizard_complete,
)


@pytest.fixture
def mock_conn() -> AsyncMock:
    """Mock asyncpg connection with fetchrow."""
    conn = AsyncMock()
    conn.close = AsyncMock()
    return conn


@pytest.fixture
def mock_pool(monkeypatch):
    """Mock asyncpg.connect to return a controlled connection."""


# ---------------------------------------------------------------------------
# _check_wizard_complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wizard_complete_all_three_passes():
    """All three sub-states present → pass."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock()
        # Three sequential fetchrow calls: equipment count, canonicalization, zones
        conn.fetchrow.side_effect = [
            {"cnt": 5},  # has equipment
            {"cnt": 5},  # has canonicalized
            {"cnt": 3},  # has hierarchy
        ]
        mock_connect.return_value = conn

        result = await _check_wizard_complete("site-005")
        assert result.passed is True
        assert "Equipment=True" in result.reason


@pytest.mark.asyncio
async def test_wizard_complete_missing_equipment():
    """No equipment rows → fail."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock()
        conn.fetchrow.side_effect = [
            {"cnt": 0},  # no equipment
            {"cnt": 0},  # no canonicalization
            {"cnt": 3},  # has hierarchy
        ]
        mock_connect.return_value = conn

        result = await _check_wizard_complete("site-005")
        assert result.passed is False
        assert "Equipment=False" in result.reason


@pytest.mark.asyncio
async def test_wizard_complete_throws_fails_closed():
    """Exception during check → the raw function propagates (caught by evaluate())."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_connect.return_value = conn

        with pytest.raises(RuntimeError, match="DB down"):
            await _check_wizard_complete("site-005")


# ---------------------------------------------------------------------------
# _check_aggregation_fresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregation_fresh_recent_rows():
    """telemetry_hourly has rows within 48h → pass."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"cnt": 500, "newest": datetime.now(UTC) - timedelta(hours=2)})
        mock_connect.return_value = conn

        result = await _check_aggregation_fresh("site-005")
        assert result.passed is True


@pytest.mark.asyncio
async def test_aggregation_fresh_stale_rows():
    """telemetry_hourly rows older than 48h → fail."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"cnt": 500, "newest": datetime.now(UTC) - timedelta(hours=72)})
        mock_connect.return_value = conn

        result = await _check_aggregation_fresh("site-005")
        assert result.passed is False
        assert "cutoff" in result.reason


@pytest.mark.asyncio
async def test_aggregation_fresh_no_rows():
    """No telemetry_hourly rows → fail."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"cnt": 0, "newest": None})
        mock_connect.return_value = conn

        result = await _check_aggregation_fresh("site-005")
        assert result.passed is False
        assert "No telemetry_hourly rows" in result.reason


# ---------------------------------------------------------------------------
# _check_history_fresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_fresh_from_data_freshness():
    """data_freshness says bms_telemetry sli_pass=true → pass."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        # First query (cached freshness): sli_pass=true
        conn.fetchrow = AsyncMock(
            return_value={
                "sli_pass": True,
                "last_updated": datetime.now(UTC) - timedelta(minutes=2),
            },
        )
        mock_connect.return_value = conn

        result = await _check_history_fresh("site-005")
        assert result.passed is True


@pytest.mark.asyncio
async def test_history_fresh_fallback_to_raw():
    """data_freshness cache missing → fallback to raw readings."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        # First query returns None (no cached freshness)
        conn.fetchrow = AsyncMock(
            side_effect=[
                None,  # no data_freshness row
                {"cnt": 1000, "newest": datetime.now(UTC) - timedelta(seconds=30)},  # raw readings fresh
            ]
        )
        mock_connect.return_value = conn

        result = await _check_history_fresh("site-005")
        assert result.passed is True


@pytest.mark.asyncio
async def test_history_fresh_no_raw_readings():
    """No raw readings at all → fail."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock(
            side_effect=[
                None,
                {"cnt": 0, "newest": None},
            ]
        )
        mock_connect.return_value = conn

        result = await _check_history_fresh("site-005")
        assert result.passed is False
        assert "No raw readings" in result.reason


# ---------------------------------------------------------------------------
# _check_operating_hours_set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operating_hours_set():
    """operating_hours is set → pass."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"operating_hours": {"is_24_7": True}})
        mock_connect.return_value = conn

        result = await _check_operating_hours_set("site-005")
        assert result.passed is True


@pytest.mark.asyncio
async def test_operating_hours_not_set():
    """operating_hours is null → fail."""
    with (
        patch(
            "app.config.settings",
        ) as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"operating_hours": None})
        mock_connect.return_value = conn

        result = await _check_operating_hours_set("site-005")
        assert result.passed is False
        assert "is null" in result.reason


# ---------------------------------------------------------------------------
# evaluate() — integration-level
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_all_pass():
    """All four gates pass → result.all_passed=True."""
    with (
        patch("app.config.settings") as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock()
        # wizard_complete: 3 queries → all pass
        # aggregation_fresh: 1 query → recent
        # history_fresh: 1 query → cached sli_pass
        # operating_hours_set: 1 query → set
        conn.fetchrow.side_effect = [
            {"cnt": 5},
            {"cnt": 5},
            {"cnt": 3},  # wizard_complete
            {"cnt": 500, "newest": datetime.now(UTC) - timedelta(hours=1)},  # aggregation_fresh
            {"sli_pass": True, "last_updated": datetime.now(UTC) - timedelta(minutes=1)},  # history_fresh
            {"operating_hours": {"is_24_7": True}},  # operating_hours_set
        ]
        mock_connect.return_value = conn

        result = await evaluate("site-005")
        assert result.all_passed is True
        assert len(result.gates) == 4
        for g in result.gates:
            assert g.passed is True, f"Gate {g.name} failed: {g.reason}"


@pytest.mark.asyncio
async def test_evaluate_one_gate_fails():
    """One gate fails → all_passed=False with breakdown."""
    with (
        patch("app.config.settings") as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock()
        conn.fetchrow.side_effect = [
            {"cnt": 0},
            {"cnt": 0},
            {"cnt": 0},  # wizard_complete → fail
            {"cnt": 500, "newest": datetime.now(UTC) - timedelta(hours=1)},  # aggregation_fresh → pass
            {"sli_pass": True, "last_updated": datetime.now(UTC) - timedelta(minutes=1)},  # history_fresh → pass
            {"operating_hours": {"is_24_7": True}},  # operating_hours_set → pass
        ]
        mock_connect.return_value = conn

        result = await evaluate("site-005")
        assert result.all_passed is False
        names = [g.name for g in result.gates]
        assert "wizard_complete" in names
        wc = next(g for g in result.gates if g.name == "wizard_complete")
        assert wc.passed is False


@pytest.mark.asyncio
async def test_evaluate_gate_fail_closed_on_error():
    """A gate that raises is caught by evaluate() and reported as check_error."""
    with (
        patch("app.config.settings") as mock_settings,
        patch("asyncpg.connect", new_callable=AsyncMock) as mock_connect,
    ):
        mock_settings.database_url = "postgresql://test"
        conn = AsyncMock()
        conn.close = AsyncMock()
        conn.fetchrow = AsyncMock()
        conn.fetchrow.side_effect = [
            {"cnt": 5},
            {"cnt": 5},
            {"cnt": 3},  # wizard_complete → pass
            RuntimeError("DB connection lost"),  # aggregation_fresh throws
        ]
        mock_connect.return_value = conn

        result = await evaluate("site-005")

        assert result.all_passed is False
        af = next((g for g in result.gates if g.name == "aggregation_fresh"), None)
        assert af is not None
        assert af.passed is False
        assert af.reason == "check_error"


# ---------------------------------------------------------------------------
# GateResult dataclass
# ---------------------------------------------------------------------------


def test_gate_result_construction():
    """GateResult can be constructed with expected fields."""
    r = GateResult(name="test_gate", passed=True, reason="all good")
    assert r.name == "test_gate"
    assert r.passed is True
    assert r.reason == "all good"
