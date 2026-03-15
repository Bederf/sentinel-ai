"""
Tests for occupancy signal emitter (Phase 159-03).
===================================================
Covers occupancy mismatch (ghost/shadow), underutilisation, sensor fault
emission, dedup windows, and source_module consistency.

All Supabase calls are mocked via httpx.
"""

import uuid
from unittest.mock import AsyncMock, patch

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


def _mock_write_signal(signal_row: dict) -> dict:
    """Return the signal_row with an id, simulating Supabase insert."""
    row = dict(signal_row)
    if "id" not in row:
        row["id"] = str(uuid.uuid4())
    return row


def _mock_write_entities(entities: list[dict]) -> list[dict]:
    return entities


# ---------------------------------------------------------------------------
# Mismatch signals — ghost bookings / shadow usage
# ---------------------------------------------------------------------------


class TestEmitMismatchGhostBooking:
    @pytest.mark.asyncio
    async def test_emit_mismatch_ghost_booking(self):
        """Room booked, 0 occupancy -> ghost_booking mismatch signal emitted."""
        from app.services.occupancy_signal_emitter import (
            emit_occupancy_mismatch_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            result = await emit_occupancy_mismatch_signal(
                {
                    "room_code": "FA1-1Q4-MR10",
                    "booking_active": True,
                    "sensor_occupancy": 0,
                    "expected_occupancy": 8,
                    "timestamp": "2026-03-15T10:00:00Z",
                    "site_id": "site-002",
                }
            )

        assert result is not None
        assert result["signal_type"] == "occupancy_mismatch"
        assert result["mismatch_type"] == "ghost_booking"
        assert result["status"] == "created"
        assert result["location_ref"] == "Fairlands/FA1/1Q4/MR10"


class TestEmitMismatchShadowUsage:
    @pytest.mark.asyncio
    async def test_emit_mismatch_shadow_usage(self):
        """Room not booked, 5 people detected -> shadow_usage mismatch signal."""
        from app.services.occupancy_signal_emitter import (
            emit_occupancy_mismatch_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            result = await emit_occupancy_mismatch_signal(
                {
                    "room_code": "FA2-2Q1-BR03",
                    "booking_active": False,
                    "sensor_occupancy": 5,
                    "expected_occupancy": 0,
                    "timestamp": "2026-03-15T11:00:00Z",
                    "site_id": "site-002",
                }
            )

        assert result is not None
        assert result["signal_type"] == "occupancy_mismatch"
        assert result["mismatch_type"] == "shadow_usage"
        assert result["status"] == "created"


class TestEmitMismatchSeverity:
    @pytest.mark.asyncio
    async def test_emit_mismatch_minor_deviation_low_severity(self):
        """<30% deviation -> severity=low."""
        from app.services.occupancy_signal_emitter import (
            emit_occupancy_mismatch_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            # 10 expected, 8 actual = 20% off
            result = await emit_occupancy_mismatch_signal(
                {
                    "room_code": "FA1-1Q4-MR10",
                    "booking_active": True,
                    "sensor_occupancy": 8,
                    "expected_occupancy": 10,
                    "timestamp": "2026-03-15T12:00:00Z",
                    "site_id": "site-002",
                }
            )

        assert result is not None
        assert result["severity"] == "low"

    @pytest.mark.asyncio
    async def test_emit_mismatch_major_deviation_medium_severity(self):
        """>30% deviation -> severity=medium."""
        from app.services.occupancy_signal_emitter import (
            emit_occupancy_mismatch_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            # 10 expected, 5 actual = 50% off
            result = await emit_occupancy_mismatch_signal(
                {
                    "room_code": "FA2-2Q1-BR03",
                    "booking_active": True,
                    "sensor_occupancy": 5,
                    "expected_occupancy": 10,
                    "timestamp": "2026-03-15T12:30:00Z",
                    "site_id": "site-002",
                }
            )

        assert result is not None
        assert result["severity"] == "medium"


class TestEmitMismatchDedup:
    @pytest.mark.asyncio
    async def test_emit_mismatch_dedup_30min(self):
        """Same room within 30 min -> None (deduplicated)."""
        from app.services.occupancy_signal_emitter import (
            emit_occupancy_mismatch_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            # First call — emitted
            result1 = await emit_occupancy_mismatch_signal(
                {
                    "room_code": "FA1-1Q4-MR10",
                    "booking_active": True,
                    "sensor_occupancy": 0,
                    "expected_occupancy": 8,
                    "timestamp": "2026-03-15T10:00:00Z",
                    "site_id": "site-002",
                }
            )
            assert result1 is not None

            # Second call — should be deduped
            result2 = await emit_occupancy_mismatch_signal(
                {
                    "room_code": "FA1-1Q4-MR10",
                    "booking_active": True,
                    "sensor_occupancy": 0,
                    "expected_occupancy": 8,
                    "timestamp": "2026-03-15T10:05:00Z",
                    "site_id": "site-002",
                }
            )
            assert result2 is None


# ---------------------------------------------------------------------------
# Underutilisation signals
# ---------------------------------------------------------------------------


class TestEmitUnderutilisationLowSeverity:
    @pytest.mark.asyncio
    async def test_emit_underutilisation_low_severity(self):
        """25% utilisation -> severity=low."""
        from app.services.occupancy_signal_emitter import (
            emit_underutilisation_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            result = await emit_underutilisation_signal(
                {
                    "room_code": "FA1-1Q4-MR10",
                    "capacity": 20,
                    "avg_occupancy": 5.0,
                    "utilisation_pct": 25.0,
                    "period": "7d",
                    "site_id": "site-002",
                }
            )

        assert result is not None
        assert result["signal_type"] == "underutilisation"
        assert result["severity"] == "low"
        assert result["status"] == "created"


class TestEmitUnderutilisationMediumSeverity:
    @pytest.mark.asyncio
    async def test_emit_underutilisation_medium_severity(self):
        """15% utilisation -> severity=medium."""
        from app.services.occupancy_signal_emitter import (
            emit_underutilisation_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            result = await emit_underutilisation_signal(
                {
                    "room_code": "FA2-2Q1-BR03",
                    "capacity": 30,
                    "avg_occupancy": 4.5,
                    "utilisation_pct": 15.0,
                    "period": "7d",
                    "site_id": "site-002",
                }
            )

        assert result is not None
        assert result["severity"] == "medium"


class TestEmitUnderutilisationDedup:
    @pytest.mark.asyncio
    async def test_emit_underutilisation_dedup_24h(self):
        """Same room within 24h -> None (deduplicated)."""
        from app.services.occupancy_signal_emitter import (
            emit_underutilisation_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            result1 = await emit_underutilisation_signal(
                {
                    "room_code": "FA1-1Q4-MR10",
                    "capacity": 20,
                    "avg_occupancy": 5.0,
                    "utilisation_pct": 25.0,
                    "period": "7d",
                    "site_id": "site-002",
                }
            )
            assert result1 is not None

            result2 = await emit_underutilisation_signal(
                {
                    "room_code": "FA1-1Q4-MR10",
                    "capacity": 20,
                    "avg_occupancy": 4.8,
                    "utilisation_pct": 24.0,
                    "period": "7d",
                    "site_id": "site-002",
                }
            )
            assert result2 is None


# ---------------------------------------------------------------------------
# Sensor fault signals
# ---------------------------------------------------------------------------


class TestEmitSensorFaultNoData:
    @pytest.mark.asyncio
    async def test_emit_sensor_fault_no_data(self):
        """fault_type=no_data -> signal emitted with severity=medium."""
        from app.services.occupancy_signal_emitter import emit_sensor_fault_signal

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            result = await emit_sensor_fault_signal(
                {
                    "sensor_id": "OCC-FA1-1Q4-01",
                    "room_code": "FA1-1Q4-MR10",
                    "fault_type": "no_data",
                    "last_reading_at": "2026-03-14T08:00:00Z",
                    "site_id": "site-002",
                }
            )

        assert result is not None
        assert result["signal_type"] == "sensor_fault"
        assert result["severity"] == "medium"
        assert result["status"] == "created"


class TestEmitSensorFaultStuckValue:
    @pytest.mark.asyncio
    async def test_emit_sensor_fault_stuck_value(self):
        """fault_type=stuck_value -> signal emitted."""
        from app.services.occupancy_signal_emitter import emit_sensor_fault_signal

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            result = await emit_sensor_fault_signal(
                {
                    "sensor_id": "OCC-FA2-2Q1-03",
                    "room_code": "FA2-2Q1-BR03",
                    "fault_type": "stuck_value",
                    "last_reading_at": "2026-03-15T06:00:00Z",
                    "site_id": "site-002",
                }
            )

        assert result is not None
        assert result["signal_type"] == "sensor_fault"
        assert result["severity"] == "medium"


class TestEmitSensorFaultDedup:
    @pytest.mark.asyncio
    async def test_emit_sensor_fault_dedup_4h(self):
        """Same sensor within 4h -> None (deduplicated)."""
        from app.services.occupancy_signal_emitter import emit_sensor_fault_signal

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            result1 = await emit_sensor_fault_signal(
                {
                    "sensor_id": "OCC-FA1-1Q4-01",
                    "room_code": "FA1-1Q4-MR10",
                    "fault_type": "no_data",
                    "last_reading_at": "2026-03-14T08:00:00Z",
                    "site_id": "site-002",
                }
            )
            assert result1 is not None

            result2 = await emit_sensor_fault_signal(
                {
                    "sensor_id": "OCC-FA1-1Q4-01",
                    "room_code": "FA1-1Q4-MR10",
                    "fault_type": "no_data",
                    "last_reading_at": "2026-03-14T08:00:00Z",
                    "site_id": "site-002",
                }
            )
            assert result2 is None


# ---------------------------------------------------------------------------
# Cross-cutting: source module consistency
# ---------------------------------------------------------------------------


class TestSourceModuleConsistency:
    @pytest.mark.asyncio
    async def test_all_signals_use_occupancy_sensor_source(self):
        """All 3 signal types use source_module='occupancy_sensor'."""
        from app.services.occupancy_signal_emitter import (
            emit_occupancy_mismatch_signal,
            emit_sensor_fault_signal,
            emit_underutilisation_signal,
        )

        with (
            patch(
                "app.services.occupancy_signal_emitter.write_signal",
                new_callable=AsyncMock,
                side_effect=_mock_write_signal,
            ),
            patch(
                "app.services.occupancy_signal_emitter.write_entities",
                new_callable=AsyncMock,
                side_effect=_mock_write_entities,
            ),
        ):
            r1 = await emit_occupancy_mismatch_signal(
                {
                    "room_code": "FA1-1Q4-MR10",
                    "booking_active": True,
                    "sensor_occupancy": 0,
                    "expected_occupancy": 8,
                    "site_id": "site-002",
                }
            )
            assert r1 is not None
            assert r1["source_module"] == "occupancy_sensor"

            r2 = await emit_underutilisation_signal(
                {
                    "room_code": "FA2-2Q1-BR03",
                    "capacity": 20,
                    "avg_occupancy": 3.0,
                    "utilisation_pct": 15.0,
                    "period": "7d",
                    "site_id": "site-002",
                }
            )
            assert r2 is not None
            assert r2["source_module"] == "occupancy_sensor"

            r3 = await emit_sensor_fault_signal(
                {
                    "sensor_id": "OCC-FA2-2Q1-03",
                    "room_code": "FA2-2Q1-BR03",
                    "fault_type": "impossible_count",
                    "last_reading_at": "2026-03-15T09:00:00Z",
                    "site_id": "site-002",
                }
            )
            assert r3 is not None
            assert r3["source_module"] == "occupancy_sensor"
