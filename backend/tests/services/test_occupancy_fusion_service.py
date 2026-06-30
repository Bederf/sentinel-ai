import pytest

from app.services.occupancy_fusion_service import OccupancyFusionService


class _Result:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._eq = {}
        self._in = {}
        self._gte = {}
        self._lt = {}
        self._limit = None
        self._desc = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self._eq[key] = value
        return self

    def in_(self, key, values):
        self._in[key] = set(values)
        return self

    def gte(self, key, value):
        self._gte[key] = value
        return self

    def lt(self, key, value):
        self._lt[key] = value
        return self

    def order(self, key, desc=False, **_kwargs):
        if key == "recorded_at":
            self._desc = bool(desc)
        return self

    def limit(self, value):
        self._limit = value
        return self

    def execute(self):
        rows = []
        for row in self._rows:
            if any(row.get(key) != value for key, value in self._eq.items()):
                continue
            if any(row.get(key) not in values for key, values in self._in.items()):
                continue
            if any(str(row.get(key) or "") < value for key, value in self._gte.items()):
                continue
            if any(str(row.get(key) or "") >= value for key, value in self._lt.items()):
                continue
            rows.append(row)
        rows.sort(key=lambda row: str(row.get("recorded_at") or ""), reverse=self._desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class _FakeSupabase:
    def __init__(self, rows=None, tables=None):
        self.tables = tables or {"equipment_sensor_readings": rows or []}

    def table(self, name):
        return _FakeQuery(self.tables.get(name, []))


def _co2_row(equipment_id, value, recorded_at):
    return {
        "site_id": "site-002",
        "equipment_id": equipment_id,
        "sensor_type": "co2_ppm",
        "value": value,
        "recorded_at": recorded_at,
    }


@pytest.mark.asyncio
async def test_zone_fusion_uses_authoritative_direct_zone_co2_before_site_aggregate():
    svc = OccupancyFusionService(
        supabase_client=_FakeSupabase(
            tables={
                "bridge_discovered_equipment": [
                    {
                        "site_id": "site-002",
                        "canonical_code": "S002-ZONE-L1-002",
                        "bridge_code": "S002-ZONE-L1-002",
                        "status": "pending",
                    }
                ],
                "equipment_sensor_readings": [
                    _co2_row("S002-ZONE-L1-002", 450, "2026-06-30T12:46:25+00:00"),
                    _co2_row("S002-ZONE-L1-002", 448, "2026-06-30T12:31:25+00:00"),
                    _co2_row("S002-FCU-102", 1099, "2026-06-30T12:46:25+00:00"),
                    _co2_row("S002-FCU-103", 1101, "2026-06-30T12:46:25+00:00"),
                ],
            }
        )
    )

    signal = await svc._get_co2_elevation("site-002", "Zone-102")

    assert signal is not None
    assert signal.normalized_pct == 0.0
    assert signal.raw_value["avg_co2"] == 450
    assert signal.raw_value["source_scope"] == "direct_zone_sensor"


@pytest.mark.asyncio
async def test_zone_fusion_ignores_unregistered_numeric_zone_co2_alias():
    svc = OccupancyFusionService(
        supabase_client=_FakeSupabase(
            tables={
                "bridge_discovered_equipment": [],
                "sites": [],
                "equipment": [],
                "equipment_sensor_readings": [
                    _co2_row("S002-ZONE-102", 450, "2026-06-30T12:46:25+00:00"),
                    _co2_row("S002-ZONE-102", 448, "2026-06-30T12:31:25+00:00"),
                    _co2_row("S002-FCU-102", 1099, "2026-06-30T12:46:25+00:00"),
                    _co2_row("S002-FCU-103", 1101, "2026-06-30T12:46:25+00:00"),
                ],
            }
        )
    )

    signal = await svc._get_co2_elevation("site-002", "Zone-102")

    assert signal is not None
    assert signal.normalized_pct == 100.0
    assert signal.raw_value["avg_co2"] == 1100
    assert signal.raw_value["source_scope"] == "site_fcu_aggregate"


@pytest.mark.asyncio
async def test_zone_fusion_falls_back_to_site_aggregate_when_direct_zone_co2_missing():
    svc = OccupancyFusionService(
        supabase_client=_FakeSupabase(
            [
                _co2_row("S002-FCU-102", 1099, "2026-06-30T12:46:25+00:00"),
                _co2_row("S002-FCU-103", 1101, "2026-06-30T12:46:25+00:00"),
            ]
        )
    )

    signal = await svc._get_co2_elevation("site-002", "Zone-999")

    assert signal is not None
    assert signal.normalized_pct == 100.0
    assert signal.raw_value["avg_co2"] == 1100
    assert signal.raw_value["source_scope"] == "site_fcu_aggregate"


@pytest.mark.asyncio
async def test_site_level_fusion_uses_site_aggregate_co2():
    svc = OccupancyFusionService(
        supabase_client=_FakeSupabase(
            [
                _co2_row("S002-ZONE-102", 450, "2026-06-30T12:46:25+00:00"),
                _co2_row("S002-FCU-102", 1099, "2026-06-30T12:46:25+00:00"),
                _co2_row("S002-FCU-103", 1101, "2026-06-30T12:46:25+00:00"),
            ]
        )
    )

    signal = await svc._get_co2_elevation("site-002")

    assert signal is not None
    assert signal.normalized_pct == 100.0
    assert signal.raw_value["avg_co2"] == 1100
    assert signal.raw_value["source_scope"] == "site_fcu_aggregate"
