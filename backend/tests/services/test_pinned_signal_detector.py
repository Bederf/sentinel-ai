"""Phase 236-02: pinned-signal detector verdict logic + exclusions + finding semantics."""

import json

import pytest

from app.services.pinned_signal_detector import (
    LONG_WINDOW_HOURS,
    MIN_LONG_HOURS,
    PinnedSignalDetector,
    PinnedSignalExclusions,
    PinnedVerdict,
    evaluate_point,
)


class TestEvaluatePoint:
    """Pure verdict logic against the 2026-07-05 S002 audit shapes."""

    def test_valve_pinned_exactly_48_structural(self):
        """valve_position exactly 48 for 7 days → structural_7d pinned."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=1,
            long_vmin=48.0,
            long_vmax=48.0,
            long_vmean=48.0,
            short_distinct=1,
            short_bucket_count=24,
            short_value=48.0,
        )
        assert v is not None and v.pinned and v.window_kind == "structural_7d"
        assert v.pinned_value == 48.0

    def test_supply_air_pressure_420(self):
        """supply_air_pressure pinned 420 (AHU-201/B1-001 live case)."""
        v = evaluate_point(
            long_hours=242,
            long_distinct=1,
            long_vmin=420.0,
            long_vmax=420.0,
            long_vmean=420.0,
            short_distinct=1,
            short_bucket_count=24,
            short_value=420.0,
        )
        assert v is not None and v.pinned and v.window_kind == "structural_7d"

    def test_tight_relative_range_pinned(self):
        """CO2-class: many distinct values but <1% relative range over the week."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=8,
            long_vmin=1097.0,
            long_vmax=1103.0,
            long_vmean=1100.0,
            short_distinct=6,
            short_bucket_count=24,
            short_value=1100.0,
        )
        assert v is not None and v.pinned and v.window_kind == "structural_7d"
        assert v.relative_range == pytest.approx(6.0 / 1100.0, rel=1e-3)

    def test_room_temp_real_variance_not_pinned(self):
        """room_temp (767 distinct, sd 1.6) must NOT trigger."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=120,
            long_vmin=19.0,
            long_vmax=27.0,
            long_vmean=23.0,
            short_distinct=18,
            short_bucket_count=24,
            short_value=23.4,
        )
        assert v is not None and not v.pinned

    def test_frozen_24h_requires_normal_history(self):
        """A normally-varying signal whose last day collapsed to one value → frozen_24h."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=60,
            long_vmin=30.0,
            long_vmax=80.0,
            long_vmean=55.0,
            short_distinct=1,
            short_bucket_count=24,
            short_value=75.0,
        )
        assert v is not None and v.pinned and v.window_kind == "frozen_24h"

    def test_low_cadence_but_changing_not_frozen(self):
        """SHOULD FIX #2: one-sample-per-hour but the value changes hourly
        (short_distinct > 1) must NOT be read as frozen."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=60,
            long_vmin=30.0,
            long_vmax=80.0,
            long_vmean=55.0,
            short_distinct=12,  # 12 distinct values across the last day → live
            short_bucket_count=24,
            short_value=75.0,
        )
        assert v is not None and not v.pinned

    def test_frozen_at_zero_is_off_not_stuck(self):
        """Value collapsed to 0 (equipment off) must NOT fire frozen_24h."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=60,
            long_vmin=0.0,
            long_vmax=80.0,
            long_vmean=30.0,
            short_distinct=1,
            short_bucket_count=24,
            short_value=0.0,
        )
        assert v is not None and not v.pinned

    def test_binary_toggle_not_pinned(self):
        """Codex #4: a genuine 2-state signal (status 0↔1) over the week has
        distinct=2 and ~100% relative range — must NOT be flagged pinned."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=2,
            long_vmin=0.0,
            long_vmax=1.0,
            long_vmean=0.4,
            short_distinct=2,
            short_bucket_count=24,
            short_value=1.0,
        )
        assert v is not None and not v.pinned

    def test_truly_frozen_single_value_pinned(self):
        """distinct == 1 (one value all week) still fires structural_7d."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=1,
            long_vmin=5.0,
            long_vmax=5.0,
            long_vmean=5.0,
            short_distinct=1,
            short_bucket_count=24,
            short_value=5.0,
        )
        assert v is not None and v.pinned and v.window_kind == "structural_7d"

    def test_structural_constant_zero_excluded(self):
        """SHOULD FIX #4: a signal constant at 0 all week reads as 'off', not a
        stuck feed — structural_7d must NOT pin it (keeps fcu_running=False knowable)."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=1,
            long_vmin=0.0,
            long_vmax=0.0,
            long_vmean=0.0,
            short_distinct=1,
            short_bucket_count=24,
            short_value=0.0,
        )
        assert v is not None and not v.pinned

    def test_insufficient_coverage_returns_none(self):
        """Under MIN_LONG_HOURS of buckets → no verdict at all."""
        v = evaluate_point(
            long_hours=MIN_LONG_HOURS - 1,
            long_distinct=1,
            long_vmin=48.0,
            long_vmax=48.0,
            long_vmean=48.0,
            short_distinct=1,
            short_bucket_count=24,
            short_value=48.0,
        )
        assert v is None

    def test_pinned_history_blocks_frozen_24h_tier(self):
        """A signal with too little 7d variety can't fire frozen_24h (structural owns it)."""
        v = evaluate_point(
            long_hours=168,
            long_distinct=5,  # < VARIES_NORMALLY_DISTINCT but > MIN_DISTINCT_LONG
            long_vmin=10.0,
            long_vmax=30.0,
            long_vmean=20.0,
            short_distinct=1,
            short_bucket_count=24,
            short_value=25.0,
        )
        assert v is not None and not v.pinned


class TestExclusions:
    def _cfg(self, tmp_path, cfg: dict) -> PinnedSignalExclusions:
        p = tmp_path / "exclusions.json"
        p.write_text(json.dumps(cfg))
        return PinnedSignalExclusions(path=str(p))

    def test_global_point_excluded(self, tmp_path):
        ex = self._cfg(tmp_path, {"global_excluded_points": ["fault_state"]})
        assert ex.is_excluded("site-002", "fault_state")
        assert not ex.is_excluded("site-002", "valve_position")

    def test_suffix_excluded(self, tmp_path):
        ex = self._cfg(tmp_path, {"global_excluded_suffixes": ["anomaly_score"]})
        assert ex.is_excluded("site-002", "lstm_anomaly_score")
        assert ex.is_excluded("site-002", "autoencoder_anomaly_score")
        assert not ex.is_excluded("site-002", "fan_speed")

    def test_site_override(self, tmp_path):
        ex = self._cfg(
            tmp_path,
            {"site_overrides": {"site-005": {"excluded_points": ["setpoint"]}}},
        )
        assert ex.is_excluded("site-005", "setpoint")
        assert not ex.is_excluded("site-002", "setpoint")

    def test_missing_config_fails_open(self, tmp_path):
        ex = PinnedSignalExclusions(path=str(tmp_path / "nope.json"))
        assert not ex.is_excluded("site-002", "anything")

    def test_shipped_default_config_loads(self):
        """The real shipped config parses and excludes status flags + ML scores."""
        ex = PinnedSignalExclusions()
        assert ex.is_excluded("site-002", "fault_state")
        assert ex.is_excluded("site-002", "equipment_online")
        assert ex.is_excluded("site-002", "lstm_anomaly_score")
        # Setpoints deliberately NOT excluded by default (operator decision).
        assert not ex.is_excluded("site-002", "setpoint")


def _pinned(equipment_id: str, point_name: str, value: float = 48.0) -> PinnedVerdict:
    return PinnedVerdict(
        equipment_id=equipment_id,
        point_name=point_name,
        pinned=True,
        window_kind="structural_7d",
        pinned_value=value,
        distinct_values=1,
        relative_range=0.0,
        hours_evaluated=168,
    )


def _clear(equipment_id: str, point_name: str) -> PinnedVerdict:
    return PinnedVerdict(equipment_id=equipment_id, point_name=point_name, pinned=False)


class TestFindingUnits:
    def setup_method(self):
        self.det = PinnedSignalDetector(database_url="postgresql://unused/unused")

    def test_equipment_grouping_below_systemic_threshold(self):
        """A handful of pinned points on two units → one finding per equipment."""
        verdicts = [_pinned("S002-AHU-201", "supply_air_pressure", 420.0), _pinned("S002-AHU-201", "filter_dp", 98.0)]
        verdicts += [_pinned("S002-FCU-101", "valve_position", 48.0)]
        verdicts += [_clear(f"S002-FCU-{i}", "room_temp") for i in range(100, 140)]
        units = self.det.build_finding_units("site-002", verdicts)
        assert len(units) == 2
        keys = {u["key"] for u in units}
        assert keys == {("S002-AHU-201", "equipment"), ("S002-FCU-101", "equipment")}
        ahu = next(u for u in units if u["target_equipment"] == "S002-AHU-201")
        point_names = {p["point_name"] for p in ahu["metadata_patch"]["pinned_points"]}
        assert point_names == {"supply_air_pressure", "filter_dp"}

    def test_systemic_rollup_single_site_finding(self):
        """Majority-pinned site (the live 529/619 case) → exactly one site finding."""
        verdicts = [_pinned(f"S002-EQ-{i:03d}", "point_a") for i in range(30)]
        verdicts += [_clear(f"S002-EQ-{i:03d}", "point_b") for i in range(10)]
        units = self.det.build_finding_units("site-002", verdicts)
        assert len(units) == 1
        unit = units[0]
        assert unit["scope"] == "site"
        assert unit["key"][1] == "site"
        assert unit["metadata_patch"]["pinned_count"] == 30
        assert unit["metadata_patch"]["evaluated_count"] == 40
        assert "bridge/BMS export feed fault" in unit["reason"]

    def test_small_site_never_systemic(self):
        """Below SYSTEMIC_MIN_POINTS pinned, even 100% ratio stays per-equipment."""
        verdicts = [_pinned(f"S005-EQ-{i}", "point_a") for i in range(5)]
        units = self.det.build_finding_units("site-005", verdicts)
        assert all(u["scope"] == "equipment" for u in units)

    def test_no_pinned_no_units(self):
        verdicts = [_clear("S002-FCU-101", "room_temp")]
        assert self.det.build_finding_units("site-002", verdicts) == []

    def test_finding_key_uses_scope(self):
        row = {"target_equipment": "S002-AHU-201", "metadata": {"scope": "equipment"}}
        assert PinnedSignalDetector._finding_key(row) == ("S002-AHU-201", "equipment")

    def test_build_finding_shape(self):
        from datetime import UTC, datetime

        units = self.det.build_finding_units("site-002", [_pinned("S002-AHU-201", "supply_air_pressure", 420.0)])
        rec = self.det._build_finding("site-002", units[0], datetime.now(UTC))
        assert rec.action_type == "data_integrity"
        assert rec.source == "pinned_signal_detector"
        assert rec.target_equipment == "S002-AHU-201"
        assert rec.metadata["scope"] == "equipment"
        assert rec.metadata["observation_count"] == 1
        assert rec.requires_approval is False
        assert "supply_air_pressure" in rec.reason

    def test_window_constants_sane(self):
        assert LONG_WINDOW_HOURS == 168
        assert MIN_LONG_HOURS < LONG_WINDOW_HOURS
