"""Tests for SentinelAlertEngine — equipment-type-aware safety boundary evaluator.

Verifies the two key false-alarm fixes:
1. Pump DP alerts get pump-specific action text (not AHU "check filter and fan speed")
2. Chiller ramp-up suppression: supply_temp alerts suppressed when chiller cold-starting
"""

import pytest

from app.services.sentinel_alert_engine import AlertContext, SentinelAlertEngine


@pytest.fixture
def engine():
    return SentinelAlertEngine()


@pytest.fixture
def default_context():
    return AlertContext(
        simulated_hour=10,
        is_peak=True,
        site_state="peak_occupied",
        occupancy_pct=80.0,
        hvac_mode="cooling",
    )


def _make_equipment(code: str, equip_type: str, readings: dict, is_running: bool = True) -> dict:
    """Helper to build equipment_states dict for a single piece of equipment."""
    return {
        code: {
            "type": equip_type,
            "is_running": is_running,
            "sensor_readings": readings,
        }
    }


# --- Pump vs AHU action text (the main false-alarm fix) ---


class TestPumpActionText:
    def test_pump_dp_gets_pump_action_text(self, engine, default_context):
        """Pump DP violation → 'strainer'/'impeller', NOT 'filter'/'fan'."""
        states = _make_equipment(
            "S002-PUMP-B1-CHW1",
            "pump",
            {"differential_pressure_kpa": 195.0},  # Within 10% of 200 max
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 1
        v = violations[0]
        assert v.severity == "warning"
        assert "impeller" in v.recommended_action.lower() or "strainer" in v.recommended_action.lower()
        assert "filter" not in v.recommended_action.lower()
        assert "fan" not in v.recommended_action.lower()

    def test_ahu_dp_gets_filter_action_text(self, engine, default_context):
        """AHU DP violation → 'filter'/'fan speed'."""
        states = _make_equipment(
            "S002-AHU-B1-001",
            "ahu",
            {"differential_pressure_kpa": 195.0},
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 1
        v = violations[0]
        assert "filter" in v.recommended_action.lower()


# --- Chiller ramp-up suppression ---


class TestChillerRampUp:
    def test_chiller_ramping_suppressed(self, engine, default_context):
        """Chiller running, supply_temp=24.9, load<50 → chiller is ramping up, no violation."""
        states = _make_equipment(
            "S002-CHILLER-B1-001",
            "chiller",
            {"supply_temp": 24.9, "load_pct": 30.0},
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 0

    def test_chiller_steady_state_alerts(self, engine, default_context):
        """Chiller running, supply_temp=24.9, load>50 → steady state, should alert."""
        states = _make_equipment(
            "S002-CHILLER-B1-001",
            "chiller",
            {"supply_temp": 24.9, "load_pct": 75.0},
        )
        violations = engine.evaluate(states, default_context)
        # supply_temp 24.9 is within 10% of 25 max → warning
        assert len(violations) == 1
        v = violations[0]
        assert v.severity == "warning"
        assert v.point_name == "supply_temp"

    def test_chiller_freeze_risk_alerts(self, engine, default_context):
        """Chiller supply_temp=3.5 → below 4°C min → critical (freeze risk)."""
        states = _make_equipment(
            "S002-CHILLER-B1-001",
            "chiller",
            {"supply_temp": 3.5, "load_pct": 80.0},
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 1
        v = violations[0]
        assert v.severity == "critical"
        assert "freeze" in v.recommended_action.lower() or "refrigerant" in v.recommended_action.lower()


# --- Basic boundary logic ---


class TestBoundaryLogic:
    def test_not_running_skipped(self, engine, default_context):
        """Equipment that is off → no violations."""
        states = _make_equipment(
            "S002-CHILLER-B1-001",
            "chiller",
            {"supply_temp": 3.0},  # Would be critical if running
            is_running=False,
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 0

    def test_safe_value_no_violation(self, engine, default_context):
        """Reading well within bounds → empty list."""
        states = _make_equipment(
            "S002-AHU-B1-001",
            "ahu",
            {"supply_air_temp": 16.0},  # Well within 12-22 range
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 0

    def test_value_exceeds_max_critical(self, engine, default_context):
        """Reading above safety max → critical."""
        states = _make_equipment(
            "S002-AHU-B1-001",
            "ahu",
            {"supply_air_temp": 23.0},  # Above 22°C max
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 1
        assert violations[0].severity == "critical"

    def test_value_within_10pct_warning(self, engine, default_context):
        """Reading near boundary (within 10%) → warning."""
        # supply_air_temp range: 12-22, 10% = 1°C
        # 21.5 is within 10% of upper limit (22 - 1 = 21)
        states = _make_equipment(
            "S002-AHU-B1-001",
            "ahu",
            {"supply_air_temp": 21.5},
        )
        violations = engine.evaluate(states, default_context)
        # 21.5 > 21.0 (max - 10% of range) → approach_pct=90 → but check normal band
        # Normal band for supply_air_temp _default: (13.0, 20.0) → 21.5 is ABOVE normal band
        assert len(violations) == 1
        assert violations[0].severity == "warning"

    def test_normal_band_suppresses(self, engine, default_context):
        """Reading in normal band → no alert even if near safety limit."""
        # zone_temp range: 16-28, peak normal band: 20-24
        # 26.8 is within 10% of 28 max (28 - 1.2 = 26.8) → would trigger
        # BUT 26.8 is OUTSIDE normal band (20-24) → should still alert
        #
        # Let's use a value IN the normal band that's still near the safety limit:
        # off_peak normal band for zone_temp is (18.0, 26.0)
        # 26.0 is at the upper edge of normal — let's set off_peak context
        off_peak_context = AlertContext(
            simulated_hour=22,
            is_peak=False,
            site_state="night_mode",
            occupancy_pct=5.0,
            hvac_mode="night_setback",
        )
        # zone_temp safe range 16-28, 10% = 1.2
        # 26.5 > 26.8 (max - 10%) → would trigger, but check normal band
        # off_peak band is (18.0, 26.0), 26.5 is OUTSIDE → should alert
        # Let's pick 25.8 — safe_max - 10% = 26.8, so 25.8 < 26.8 → no trigger
        # We need a value that triggers the 10% check but is in normal band
        # 26.9 → approach_pct = 90 (within 10% of 28)
        # off_peak normal band (18.0, 26.0) → 26.9 is outside → would alert
        #
        # Use battery_pct instead: safe range 30-100, normal band (50, 100)
        # 35 → within 10% of 30 min (30 + 7 = 37) → approach_pct=90
        # Normal band (50, 100) → 35 is outside → would still alert
        #
        # Best: use load_pct with chiller during peak
        # safe range: 0-95, 10% = 9.5, so >85.5 triggers warning
        # peak normal band for chiller: (0.0, 92.0)
        # 90.0 → approach_pct=90, but 90 is within (0, 92) → SUPPRESSED
        states = _make_equipment(
            "S002-CHILLER-B1-001",
            "chiller",
            {"load_pct": 90.0},
        )
        violations = engine.evaluate(states, default_context)  # default_context.is_peak=True
        assert len(violations) == 0

    def test_max_3_violations(self, engine, default_context):
        """Many violations → capped at 3."""
        # Create 5 pieces of equipment, each with a violation
        states = {}
        for i in range(5):
            code = f"S002-AHU-B1-{i:03d}"
            states[code] = {
                "type": "ahu",
                "is_running": True,
                "sensor_readings": {"supply_air_temp": 23.0},  # Above 22 max
            }
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 3

    def test_non_numeric_skipped(self, engine, default_context):
        """String readings → ignored (no crash)."""
        states = _make_equipment(
            "S002-AHU-B1-001",
            "ahu",
            {"supply_air_temp": "offline", "zone_temp": None},
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 0


class TestViolationFields:
    """Verify SafetyViolation dataclass is populated correctly."""

    def test_violation_fields_populated(self, engine, default_context):
        states = _make_equipment(
            "S002-AHU-B1-001",
            "ahu",
            {"supply_air_temp": 23.0},
        )
        violations = engine.evaluate(states, default_context)
        assert len(violations) == 1
        v = violations[0]
        assert v.equipment_code == "S002-AHU-B1-001"
        assert v.equipment_type == "ahu"
        assert v.point_name == "supply_air_temp"
        assert v.value == 23.0
        assert v.unit == "°C"
        assert v.severity == "critical"
        assert v.limit_min == 12.0
        assert v.limit_max == 22.0
        assert v.approach_pct == 100
        assert v.operational_context["is_peak_hours"] is True
        assert v.operational_context["hour"] == 10
        assert "limit:" in v.limit_desc
