from datetime import datetime, timedelta

import pytest

from app.models.health_rating import HealthComponentBreakdown, HealthDataQualityResult, HealthRating
from app.services.sentinel_data_sync import SentinelDataSync


class _FakeSnapshotService:
    def __init__(self):
        self.store_calls = []
        self.rollup_calls = []

    async def store_snapshot(self, rating, site_id=None):
        self.store_calls.append((rating, site_id))
        return "snapshot-1"

    async def update_daily_rollup(self, equipment_id, date):
        self.rollup_calls.append((equipment_id, date))


class _FakeCalculator:
    async def compute_rating(self, equipment_id, equipment, mode):
        return HealthRating(
            equipment_id=equipment_id,
            health_score=91.0,
            health_status="healthy",
            confidence="high",
            assessment_state="normal",
            components=HealthComponentBreakdown(),
            data_quality=HealthDataQualityResult(
                freshness_minutes=0.0,
                snapshot_count_24h=1,
                valid_point_ratio=1.0,
                baseline_age_days=0,
                gates_passed=4,
                gates_total=4,
                confidence="high",
                assessment_state="normal",
            ),
            snapshot_at="2026-03-25T10:00:00Z",
        )


@pytest.mark.asyncio
async def test_capture_health_snapshots_uses_equipment_uuid():
    sync = SentinelDataSync(site_id="site-002")
    snapshot_service = _FakeSnapshotService()
    sync._get_snapshot_service = lambda: snapshot_service
    sync._get_health_calculator = lambda: _FakeCalculator()
    sync._fetch_equipment_snapshot_metadata = lambda codes: {
        "S002-CHILLER-B1-001": {
            "id": "11111111-1111-1111-1111-111111111111",
            "site_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "type": "CHILLER",
            "install_date": None,
            "commissioning_date": None,
            "operating_data": {},
        }
    }

    stored = await sync._capture_health_snapshots(
        {
            "S002-CHILLER-B1-001": {
                "health_score": 91.0,
                "sensor_readings": {"supply_temp": 6.5},
            }
        },
        datetime(2026, 3, 25, 10, 0, 0),
    )

    assert stored == 1
    assert snapshot_service.store_calls[0][0].equipment_id == "11111111-1111-1111-1111-111111111111"
    assert snapshot_service.store_calls[0][1] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert snapshot_service.rollup_calls == [("11111111-1111-1111-1111-111111111111", "2026-03-25")]


def test_should_store_health_snapshot_throttles_unchanged_health():
    sync = SentinelDataSync(site_id="site-002")
    simulated_time = datetime(2026, 3, 25, 10, 0, 0)
    sync._last_snapshot_state["S002-CHILLER-B1-001"] = (simulated_time, 91.0)

    should_store = sync._should_store_health_snapshot(
        "S002-CHILLER-B1-001",
        {"health_score": 91.4, "sensor_readings": {"supply_temp": 6.5}},
        simulated_time + timedelta(minutes=5),
    )

    assert should_store is False
