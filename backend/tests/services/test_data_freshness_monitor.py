from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.services.data_freshness_monitor import DataFreshnessMonitor


class _FakeTable:
    def __init__(self):
        self.upserts = []
        self.inserts = []

    def upsert(self, payload, on_conflict=None):
        self.upserts.append((payload, on_conflict))
        return self

    def insert(self, payload):
        self.inserts.append(payload)
        return self

    def execute(self):
        return type("Resp", (), {"data": []})()


class _FakeSupabase:
    def __init__(self):
        self.tables = {"data_freshness": _FakeTable()}

    def table(self, name):
        return self.tables.setdefault(name, _FakeTable())


@pytest.mark.asyncio
async def test_telemetry_stream_freshness_fails_when_any_stream_or_equipment_is_stale(monkeypatch):
    monitor = DataFreshnessMonitor()
    now = datetime(2026, 6, 28, 13, 0, tzinfo=UTC)
    stale_latest = now - timedelta(hours=2)

    monkeypatch.setattr(
        monitor,
        "_load_telemetry_stream_snapshot",
        lambda site_id, now_: {
            "stream_count": 20,
            "equipment_count": 10,
            "max_age_seconds": 7200,
            "oldest_latest": stale_latest,
            "stale_streams": [
                {
                    "equipment_id": "S002-FCU-305",
                    "sensor_type": "co2_ppm",
                    "latest": stale_latest.isoformat(),
                    "age_seconds": 7200,
                }
            ],
            "missing_equipment": [{"code": "S002-VAV-L1-A", "type": "vav"}],
        },
    )
    handle = AsyncMock(return_value={"breach_started": True, "breach_resolved": False})
    monkeypatch.setattr(monitor, "_handle_breach_logic", handle)

    supabase = _FakeSupabase()
    result = await monitor._check_telemetry_stream_freshness(supabase, "site-002", now)

    assert result is not None
    assert result.data_source == "telemetry_streams"
    assert result.sli_pass is False
    assert result.age_seconds == 7200
    payload, on_conflict = supabase.table("data_freshness").upserts[0]
    assert on_conflict == "site_id,data_source"
    assert payload["data_source"] == "telemetry_streams"
    assert payload["sli_pass"] is False
    handle.assert_awaited_once()
    details = handle.await_args.kwargs["details"]
    assert details["stale_stream_count"] == 1
    assert details["missing_equipment_count"] == 1


@pytest.mark.asyncio
async def test_telemetry_stream_freshness_uses_full_counts_not_samples(monkeypatch):
    monitor = DataFreshnessMonitor()
    now = datetime(2026, 6, 28, 13, 0, tzinfo=UTC)

    monkeypatch.setattr(
        monitor,
        "_load_telemetry_stream_snapshot",
        lambda site_id, now_: {
            "stream_count": 200,
            "equipment_count": 25,
            "max_age_seconds": 1800,
            "oldest_latest": now - timedelta(minutes=30),
            "stale_stream_count": 7,
            "missing_equipment_count": 3,
            "stale_streams": [],
            "missing_equipment": [],
        },
    )
    handle = AsyncMock(return_value={"breach_started": True, "breach_resolved": False})
    monkeypatch.setattr(monitor, "_handle_breach_logic", handle)

    result = await monitor._check_telemetry_stream_freshness(_FakeSupabase(), "site-005", now)

    assert result is not None
    assert result.site_id == "site-005"
    assert result.sli_pass is False
    details = handle.await_args.kwargs["details"]
    assert details["stale_stream_count"] == 7
    assert details["missing_equipment_count"] == 3


def test_freshness_alert_message_groups_stale_stream_samples():
    monitor = DataFreshnessMonitor()

    text = monitor._format_unrecoverable_alert(
        "site-002",
        "telemetry_streams",
        7200,
        900,
        1200,
        {
            "stream_count": 200,
            "stale_stream_count": 2,
            "missing_equipment_count": 1,
            "stale_stream_samples": [{"equipment_id": "S002-FCU-305", "sensor_type": "co2_ppm", "age_seconds": 7200}],
            "missing_equipment_samples": [{"code": "S002-VAV-L1-A", "type": "vav"}],
        },
    )

    assert "SENTINEL Data Freshness Alert" in text
    assert "Telemetry streams checked: 200" in text
    assert "S002-FCU-305.co2_ppm" in text
    assert "S002-VAV-L1-A (vav)" in text


def test_telemetry_stream_database_url_falls_back_to_local_postgres(monkeypatch):
    monitor = DataFreshnessMonitor()

    monkeypatch.setattr("app.services.data_freshness_monitor.settings.database_url", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)

    assert monitor._database_url() == "postgresql://postgres:postgres@127.0.0.1:55322/postgres"


@pytest.mark.asyncio
async def test_freshness_alert_does_not_fall_back_to_global_chat(monkeypatch):
    monitor = DataFreshnessMonitor()
    supabase = _FakeSupabase()

    monkeypatch.setattr(monitor, "_resolve_site_manager_chat_id", lambda site_id: "")
    monkeypatch.setattr(monitor, "_fallback_log", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.database.supabase_client.get_supabase_client", lambda: supabase)

    sent = await monitor._send_freshness_telegram("site-005", "freshness failed", "high")

    assert sent is False
    payload = supabase.table("notification_delivery_log").inserts[0]
    assert payload["site_id"] == "site-005"
    assert payload["recipient_identifier"] == ""
    assert payload["status"] == "failed"
    assert "active site manager" in payload["error_message"]
