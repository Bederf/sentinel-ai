"""Tests for AEGIS contributing factors audit payload."""

from types import SimpleNamespace

from app.config.settings import settings
from app.services.aegis_bridge import _build_contributing_factors
from app.services.bess_dispatch_engine import BESSState
from app.services.solar_arbitrage_engine import DispatchAction


class _FakeConstraint:
    """Test helper for serialized constraint payloads."""

    def __init__(self, severity: str):
        self._severity = severity

    def to_dict(self):
        return {
            "constraint_type": "test_constraint",
            "severity": self._severity,
            "current_value": 1.0,
            "limit_value": 2.0,
            "message": "test",
            "mitigation": "none",
        }


def _build_inputs():
    dispatch_action = DispatchAction(
        action="discharge",
        power_kw=120.0,
        reason="Peak shaving",
        tariff_band="peak",
        rate_per_kwh=3.01,
        current_soc_pct=65.0,
        target_soc_pct=40.0,
    )
    dispatch_command = SimpleNamespace(
        duration_minutes=15,
        actual_power_kw=100.0,
        requested_power_kw=120.0,
        constraints_applied=[],
    )
    bess_state = BESSState(
        soc_pct=65.0,
        temperature_c=25.0,
        power_kw=0.0,
        grid_frequency_hz=50.0,
    )
    recommendation = SimpleNamespace(correlation_id="proposal-123")
    context = {"ls_stage": 0, "forecast_available": True}
    return dispatch_action, dispatch_command, bess_state, recommendation, context


def test_constraint_counts_derived_from_serialized_payload(monkeypatch):
    monkeypatch.setattr(settings, "aegis_bess_writer_enabled", False)

    dispatch_action, dispatch_command, bess_state, recommendation, context = _build_inputs()
    dispatch_command.constraints_applied = [
        _FakeConstraint("warning"),
        _FakeConstraint("warn"),
        _FakeConstraint("block"),
        _FakeConstraint("blocked"),
        _FakeConstraint("alarm"),
    ]

    factors = _build_contributing_factors(
        dispatch_action=dispatch_action,
        dispatch_command=dispatch_command,
        bess_state=bess_state,
        recommendation=recommendation,
        context=context,
    )

    assert len(factors["constraints_evaluated"]) == 5
    assert factors["constraint_warnings"] == 2
    assert factors["constraint_blocks"] == 2


def test_quality_gate_and_metadata_fields_present(monkeypatch):
    monkeypatch.setattr(settings, "aegis_bess_writer_enabled", False)

    dispatch_action, dispatch_command, bess_state, recommendation, context = _build_inputs()

    factors = _build_contributing_factors(
        dispatch_action=dispatch_action,
        dispatch_command=dispatch_command,
        bess_state=bess_state,
        recommendation=recommendation,
        context=context,
    )

    assert factors["created_by"] == "aegis"
    assert factors["approval_outcome"] == "pending"
    assert factors["dispatch_action_type"] == "discharge"
    assert factors["quality_gate_status"] == "unknown"
    assert factors["quality_gate_status_at_routing"] == "unknown"
    assert factors["quality_gate_status_final"] == "pending"


def test_command_hash_stable_for_same_dispatch_payload(monkeypatch):
    monkeypatch.setattr(settings, "aegis_bess_writer_enabled", False)

    dispatch_action, dispatch_command, bess_state, recommendation, context = _build_inputs()

    factors_1 = _build_contributing_factors(
        dispatch_action=dispatch_action,
        dispatch_command=dispatch_command,
        bess_state=bess_state,
        recommendation=recommendation,
        context=context,
    )
    factors_2 = _build_contributing_factors(
        dispatch_action=dispatch_action,
        dispatch_command=dispatch_command,
        bess_state=bess_state,
        recommendation=recommendation,
        context=context,
    )

    assert factors_1["command_hash"] == factors_2["command_hash"]
