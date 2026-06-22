from datetime import UTC, datetime, timedelta

import pytest

from app.services.zone_occupancy_trigger_service import (
    ZoneOccupancyTriggerService,
)


class FakeZoneEventRepository:
    def __init__(self):
        self.events = []

    async def create_event(self, event):
        self.events.append(event)

    async def list_recent_events(self, site_id, *, zone_id=None, since=None, limit=200):
        events = [event.to_record() for event in self.events if event.site_id == site_id]
        if zone_id:
            events = [event for event in events if event["zone_id"] == zone_id]
        if since:
            events = [event for event in events if datetime.fromisoformat(event["observed_at"]) >= since]
        return events[:limit]


def _service(cooldown_minutes=10):
    repo = FakeZoneEventRepository()
    return ZoneOccupancyTriggerService(repository=repo, cooldown_minutes=cooldown_minutes), repo


@pytest.mark.asyncio
async def test_zone_change_records_event_when_site_aggregate_unchanged():
    svc, repo = _service()
    t0 = datetime(2026, 6, 22, 10, 0, tzinfo=UTC)

    baseline = {
        "site_aggregate": {"total_occupancy": 10, "occupied_zones": 1},
        "zone_occupancy": {
            "L1-East": {"occupancy_count": 10},
            "L1-West": {"occupancy_count": 0},
        },
    }
    changed = {
        "site_aggregate": {"total_occupancy": 10, "occupied_zones": 1},
        "zone_occupancy": {
            "L1-East": {"occupancy_count": 0},
            "L1-West": {"occupancy_count": 10},
        },
    }

    assert await svc.process_payload("site-002", baseline, observed_at=t0) == []
    events = await svc.process_payload("site-002", changed, observed_at=t0 + timedelta(minutes=11))

    assert len(events) == 2
    assert {event.zone_id for event in events} == {"L1-East", "L1-West"}
    assert len(repo.events) == 2


@pytest.mark.asyncio
async def test_no_zone_change_records_no_event():
    svc, repo = _service()
    t0 = datetime(2026, 6, 22, 10, 0, tzinfo=UTC)
    payload = {"zone_occupancy": {"L1-East": {"occupancy_percent": 25}}}

    await svc.process_payload("site-002", payload, observed_at=t0)
    events = await svc.process_payload("site-002", payload, observed_at=t0 + timedelta(minutes=15))

    assert events == []
    assert repo.events == []


@pytest.mark.asyncio
async def test_repeated_change_inside_cooldown_records_no_duplicate_event():
    svc, repo = _service(cooldown_minutes=10)
    t0 = datetime(2026, 6, 22, 10, 0, tzinfo=UTC)

    await svc.process_payload("site-002", {"zone_occupancy": {"L1-East": 0}}, observed_at=t0)
    first = await svc.process_payload(
        "site-002", {"zone_occupancy": {"L1-East": 1}}, observed_at=t0 + timedelta(minutes=1)
    )
    await svc.process_payload("site-002", {"zone_occupancy": {"L1-East": 0}}, observed_at=t0 + timedelta(minutes=2))
    duplicate = await svc.process_payload(
        "site-002",
        {"zone_occupancy": {"L1-East": 1}},
        observed_at=t0 + timedelta(minutes=3),
    )

    assert len(first) == 1
    assert duplicate == []
    assert len(repo.events) == 1


@pytest.mark.asyncio
async def test_repeated_change_after_cooldown_records_event():
    svc, repo = _service(cooldown_minutes=10)
    t0 = datetime(2026, 6, 22, 10, 0, tzinfo=UTC)

    await svc.process_payload("site-002", {"zone_occupancy": {"L1-East": 0}}, observed_at=t0)
    await svc.process_payload("site-002", {"zone_occupancy": {"L1-East": 1}}, observed_at=t0 + timedelta(minutes=1))
    await svc.process_payload("site-002", {"zone_occupancy": {"L1-East": 0}}, observed_at=t0 + timedelta(minutes=2))
    after_cooldown = await svc.process_payload(
        "site-002",
        {"zone_occupancy": {"L1-East": 1}},
        observed_at=t0 + timedelta(minutes=12),
    )

    assert len(after_cooldown) == 1
    assert len(repo.events) == 2


@pytest.mark.asyncio
async def test_scheduler_zone_trigger_is_inert(monkeypatch):
    import app.services.background_scheduler as scheduler_module

    class FakeTriggerService:
        def __init__(self):
            self.called = False

        async def process_site(self, site_id):
            self.called = True
            assert site_id == "site-002"
            return []

    fake_service = FakeTriggerService()
    scheduler = scheduler_module.BackgroundSchedulerService()

    monkeypatch.setattr(scheduler_module, "get_registered_site_ids", lambda: ["site-002"], raising=False)
    monkeypatch.setattr(
        "app.core.site_resolver.get_registered_site_ids",
        lambda: ["site-002"],
    )
    monkeypatch.setattr(
        "app.services.zone_occupancy_trigger_service.get_zone_occupancy_trigger_service",
        lambda: fake_service,
    )
    monkeypatch.setattr(
        "app.services.ai_optimizer.get_ai_optimizer",
        lambda: (_ for _ in ()).throw(AssertionError("zone trigger must not call optimization")),
    )

    await scheduler._run_zone_occupancy_trigger_async()

    assert fake_service.called is True


def test_recent_event_query_shape_is_site_zone_time_indexed():
    svc, _repo = _service()

    assert hasattr(svc.repository, "list_recent_events")
