"""Tests for InspectionTelemetryService."""

import pytest

from app.services.inspection_telemetry_service import InspectionTelemetryService, _rms_ms2_to_velocity


class TestRmsConversion:
    def test_converts_ms2_to_velocity(self):
        v = _rms_ms2_to_velocity(2.0, 50.0)
        assert v == pytest.approx(6.37, rel=0.01)

    def test_uses_default_rpm_when_no_freq(self):
        v = _rms_ms2_to_velocity(1.0, None, default_shaft_rpm=1500.0)
        assert v > 0


class TestScoreFromPhyphox:
    def test_no_defect_low_rms_high_score(self):
        parsed = {"rms_total_ms2": 0.5, "peak_frequencies_hz": [50.0]}
        analyzer = {"defect_detected": False, "mechanical_fault": None, "confidence": 0.0}
        score = InspectionTelemetryService.score_from_phyphox(parsed, analyzer)
        assert score >= 85

    def test_bearing_defect_outer_race_high_conf_low_score(self):
        parsed = {"rms_total_ms2": 3.0, "peak_frequencies_hz": [50.0]}
        analyzer = {"defect_detected": True, "defect_type": "outer_race", "confidence": 0.7, "mechanical_fault": None}
        score = InspectionTelemetryService.score_from_phyphox(parsed, analyzer)
        assert score <= 35

    def test_mechanical_fault_high_conf(self):
        parsed = {"rms_total_ms2": 0.8, "peak_frequencies_hz": [50.0]}
        analyzer = {"defect_detected": False, "mechanical_fault": "imbalance", "confidence": 0.9}
        score = InspectionTelemetryService.score_from_phyphox(parsed, analyzer)
        assert score == 40.0

    def test_high_velocity_hard_cap(self):
        parsed = {"rms_total_ms2": 20.0, "peak_frequencies_hz": [50.0]}
        analyzer = {"defect_detected": False, "mechanical_fault": None, "confidence": 0.0}
        score = InspectionTelemetryService.score_from_phyphox(parsed, analyzer)
        assert score == 25.0

    def test_bearing_defect_plus_high_velocity_caps_at_25(self):
        parsed = {"rms_total_ms2": 20.0, "peak_frequencies_hz": [50.0]}
        analyzer = {"defect_detected": True, "defect_type": "outer_race", "confidence": 0.9, "mechanical_fault": None}
        score = InspectionTelemetryService.score_from_phyphox(parsed, analyzer)
        assert score == 25.0  # Hard cap takes precedence


class TestScoreFromManual:
    def test_condition_5_no_noise(self):
        score = InspectionTelemetryService.score_from_manual(None, 5)
        assert score == 95.0

    def test_condition_1_loud_noise(self):
        score = InspectionTelemetryService.score_from_manual(98.0, 1)
        assert score <= 15.0

    def test_invalid_rating_raises(self):
        with pytest.raises(ValueError):
            InspectionTelemetryService.score_from_manual(None, 6)

    def test_quiet_environment_boost(self):
        score = InspectionTelemetryService.score_from_manual(65.0, 4)
        assert score == 87.0  # 82 + 5


class TestCalculateInspectionModifier:
    def test_no_data_returns_zero(self):
        assert InspectionTelemetryService.calculate_inspection_modifier(None, None) == 0.0

    def test_stale_returns_zero(self):
        assert InspectionTelemetryService.calculate_inspection_modifier(90.0, 95) == 0.0

    def test_fresh_excellent(self):
        assert InspectionTelemetryService.calculate_inspection_modifier(90.0, 10) == 5.0

    def test_fresh_critical(self):
        assert InspectionTelemetryService.calculate_inspection_modifier(20.0, 10) == -15.0

    def test_decayed_modifier(self):
        assert InspectionTelemetryService.calculate_inspection_modifier(20.0, 70) == -7.5

    def test_neutral_band(self):
        assert InspectionTelemetryService.calculate_inspection_modifier(55.0, 10) == 0.0
