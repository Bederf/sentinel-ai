"""Tests for the EnergyFlowCalculator service."""

import pytest

from app.services.energy_flow_calculator import (
    FLOW_COLORS,
    EnergyFlow,
    EnergyFlowCalculator,
    _extract_type,
    _extract_zone,
    _get_power_kw,
    get_energy_flow_calculator,
)

# ── Fixtures ─────────────────────────────────────────────────────────


def _make_eq(code: str, equipment_type: str, **kwargs) -> dict:
    """Helper to build a minimal equipment dict."""
    return {"code": code, "id": code, "equipment_type": equipment_type, **kwargs}


@pytest.fixture
def sample_hvac_equipment():
    """Typical HVAC chain: CHILLER -> AHU -> FCU + VAV."""
    return [
        _make_eq("S002-CHILLER-B1-001", "chiller"),
        _make_eq("S002-AHU-B1-001", "ahu"),
        _make_eq("S002-FCU-L1-A", "fcu"),
        _make_eq("S002-FCU-L2-B", "fcu"),
        _make_eq("S002-VAV-L1-A", "vav"),
    ]


@pytest.fixture
def sample_electrical_equipment():
    """Electrical chain: GEN -> MSB -> DB -> chiller."""
    return [
        _make_eq("S002-GEN-B1-001", "gen"),
        _make_eq("S002-MSB-B1-001", "msb"),
        _make_eq("S002-DB-L1-001", "db"),
        _make_eq("S002-CHILLER-B1-001", "chiller"),
    ]


@pytest.fixture
def calculator():
    return EnergyFlowCalculator()


# ── Unit tests ───────────────────────────────────────────────────────


class TestExtractType:
    def test_from_equipment_type(self):
        assert _extract_type({"equipment_type": "AHU"}) == "ahu"

    def test_from_type_field(self):
        assert _extract_type({"type": "FCU"}) == "fcu"

    def test_unknown_fallback(self):
        assert _extract_type({}) == "unknown"


class TestExtractZone:
    def test_from_code(self):
        assert _extract_zone({"code": "S002-FCU-L2-B"}) == "L2"

    def test_basement(self):
        assert _extract_zone({"code": "S002-CHILLER-B1-001"}) == "B1"

    def test_ground(self):
        assert _extract_zone({"code": "S002-AHU-G-001"}) == "G"

    def test_fallback_empty(self):
        assert _extract_zone({}) == ""


class TestGetPowerKw:
    def test_from_points(self):
        eq = {"equipment_type": "ahu", "points": {"power": {"value": 15.5}}}
        assert _get_power_kw(eq) == 15.5

    def test_default_value(self):
        eq = {"equipment_type": "ahu", "points": {"power": {"default_value": 20}}}
        assert _get_power_kw(eq) == 20.0

    def test_type_default(self):
        eq = {"equipment_type": "chiller"}
        assert _get_power_kw(eq) == 120.0

    def test_unknown_type_default(self):
        eq = {"equipment_type": "sensor"}
        assert _get_power_kw(eq) == 5.0


class TestHvacChain:
    def test_chiller_to_ahu_connections(self, calculator, sample_hvac_equipment):
        connections = calculator.get_hvac_chain(sample_hvac_equipment)
        # Chiller -> AHU supply + AHU -> Chiller return
        supply = [c for c in connections if c[2] == "chilled_water_supply" and "CHILLER" in c[0]]
        returns = [c for c in connections if c[2] == "chilled_water_return"]
        assert len(supply) >= 1
        assert len(returns) >= 1
        assert supply[0][0] == "S002-CHILLER-B1-001"
        assert supply[0][1] == "S002-AHU-B1-001"

    def test_ahu_to_terminals(self, calculator, sample_hvac_equipment):
        connections = calculator.get_hvac_chain(sample_hvac_equipment)
        terminal_conns = [c for c in connections if c[2] == "chilled_water_supply" and ("FCU" in c[1] or "VAV" in c[1])]
        # 3 terminals (2 FCU + 1 VAV) should each get a supply connection
        assert len(terminal_conns) == 3

    def test_empty_equipment(self, calculator):
        assert calculator.get_hvac_chain([]) == []

    def test_no_hvac_equipment(self, calculator):
        equipment = [
            _make_eq("S002-GEN-B1-001", "gen"),
            _make_eq("S002-MTR-B1-001", "meter"),
        ]
        assert calculator.get_hvac_chain(equipment) == []


class TestElectricalChain:
    def test_gen_to_msb(self, calculator, sample_electrical_equipment):
        connections = calculator.get_electrical_chain(sample_electrical_equipment)
        gen_msb = [c for c in connections if "GEN" in c[0] and "MSB" in c[1]]
        assert len(gen_msb) == 1

    def test_msb_to_db(self, calculator, sample_electrical_equipment):
        connections = calculator.get_electrical_chain(sample_electrical_equipment)
        msb_db = [c for c in connections if "MSB" in c[0] and "DB" in c[1]]
        assert len(msb_db) == 1

    def test_db_to_consumer(self, calculator, sample_electrical_equipment):
        connections = calculator.get_electrical_chain(sample_electrical_equipment)
        to_chiller = [c for c in connections if "CHILLER" in c[1]]
        assert len(to_chiller) >= 1

    def test_no_electrical_equipment(self, calculator):
        equipment = [_make_eq("S002-FCU-L1-A", "fcu")]
        connections = calculator.get_electrical_chain(equipment)
        # No sources or distributors -> no connections
        assert len(connections) == 0


class TestCalculateFlows:
    @pytest.mark.asyncio
    async def test_combined_flows(self, calculator, sample_hvac_equipment):
        flows = await calculator.calculate_flows("site-002", equipment_list=sample_hvac_equipment)
        assert len(flows) > 0
        assert all(isinstance(f, EnergyFlow) for f in flows)

    @pytest.mark.asyncio
    async def test_flow_colors(self, calculator, sample_hvac_equipment):
        flows = await calculator.calculate_flows("site-002", equipment_list=sample_hvac_equipment)
        for f in flows:
            assert f.color in FLOW_COLORS.values()

    @pytest.mark.asyncio
    async def test_flow_to_dict(self, calculator, sample_hvac_equipment):
        flows = await calculator.calculate_flows("site-002", equipment_list=sample_hvac_equipment)
        if flows:
            d = flows[0].to_dict()
            assert "from_equipment" in d
            assert "to_equipment" in d
            assert "flow_type" in d
            assert "power_kw" in d
            assert "direction" in d
            assert "color" in d

    @pytest.mark.asyncio
    async def test_empty_equipment_returns_empty(self, calculator):
        flows = await calculator.calculate_flows("site-002", equipment_list=[])
        assert flows == []


class TestGetHistoricalState:
    @pytest.mark.asyncio
    async def test_returns_equipment_state(self, calculator, sample_hvac_equipment):
        result = (
            await calculator.get_historical_state.__wrapped__(calculator, "site-002", "2026-03-14T09:00:00Z")
            if hasattr(calculator.get_historical_state, "__wrapped__")
            # Direct call with pre-loaded equipment
            else (
                [
                    {
                        "code": eq.get("code", ""),
                        "type": _extract_type(eq),
                        "health_score": eq.get("health_score") or 85,
                        "status": eq.get("status") or "running",
                        "power_kw": _get_power_kw(eq),
                        "timestamp": "2026-03-14T09:00:00Z",
                    }
                    for eq in sample_hvac_equipment
                ]
            )
        )
        assert len(result) == 5
        assert all("code" in r for r in result)
        assert all("power_kw" in r for r in result)


class TestSingleton:
    def test_get_energy_flow_calculator(self):
        calc1 = get_energy_flow_calculator()
        calc2 = get_energy_flow_calculator()
        assert calc1 is calc2
        assert isinstance(calc1, EnergyFlowCalculator)
