"""Comprehensive tests for the static validation engine.

Phase 162: Semantic Control Foundation — Plan 03.
Tests bounds checking, rate-of-change limits, completeness scoring, conflict
detection, data quality gating, and full ValidationReport structure.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models.point_classification import PointClassification
from app.models.semantic_tag import SafetyClass
from app.models.validation_errors import ValidationErrorCategory
from app.services.simbiot.validators.bounds_validator import BoundsValidator
from app.services.simbiot.validators.template_completeness import (
    TemplateCompletenessCalculator,
)
from app.services.simbiot.validators.validation_engine import StaticValidationEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_classification(
    point_id: str = "S001-AHU-B1-001.SAT",
    semantic_tags: list[str] | None = None,
    confidence_score: float = 0.85,
    data_quality_score: float = 0.9,
    current_value: float | None = None,
    highest_safety_class: SafetyClass | None = SafetyClass.MEDIUM,
    historic_values: dict | None = None,
) -> PointClassification:
    return PointClassification(
        point_id=point_id,
        site_id="S001",
        equipment_type="ahu",
        semantic_tags=semantic_tags or ["supply_air_temperature_sensor"],
        confidence_score=confidence_score,
        data_quality_score=data_quality_score,
        classification_date=datetime.utcnow(),
        highest_safety_class=highest_safety_class,
        current_value=current_value,
        historic_values=historic_values,
    )


AHU_TEMPLATE = {
    "critical_points": [
        "supply_air_temperature_sensor",
        "supply_air_pressure_sensor",
        "fan_status",
    ],
    "important_points": [
        "supply_air_temperature_setpoint",
        "supply_air_static_pressure_setpoint",
        "economizer_position",
    ],
}


# ---------------------------------------------------------------------------
# BoundsValidator tests
# ---------------------------------------------------------------------------


class TestBoundsValidator:
    def setup_method(self) -> None:
        self.validator = BoundsValidator()
        self.bounds = {"min": 5.0, "max": 35.0}

    def test_bounds_violation_detected_low(self) -> None:
        """Value below minimum triggers BOUNDS_VIOLATION error."""
        errors = self.validator.validate_point_value("point-1", "supply_air_temperature_sensor", -2.0, self.bounds)
        assert len(errors) == 1
        assert errors[0].category == ValidationErrorCategory.BOUNDS_VIOLATION
        assert errors[0].severity == "error"
        assert errors[0].actual_value == -2.0

    def test_bounds_violation_detected_high(self) -> None:
        """Value above maximum triggers BOUNDS_VIOLATION error."""
        errors = self.validator.validate_point_value("point-1", "supply_air_temperature_sensor", 85.0, self.bounds)
        assert len(errors) == 1
        assert errors[0].category == ValidationErrorCategory.BOUNDS_VIOLATION
        assert errors[0].severity == "error"
        assert "above maximum" in errors[0].message

    def test_bounds_valid_value_passes(self) -> None:
        """Value within bounds returns no errors."""
        errors = self.validator.validate_point_value("point-1", "supply_air_temperature_sensor", 18.5, self.bounds)
        assert errors == []

    def test_bounds_none_skipped(self) -> None:
        """None bounds dict returns no errors (not yet configured)."""
        errors = self.validator.validate_point_value(
            "point-1",
            "supply_air_temperature_sensor",
            999.0,
            None,  # type: ignore[arg-type]
        )
        assert errors == []

    def test_rate_limit_exceeded_triggers_warning(self) -> None:
        """Rate-of-change exceeding limit produces a warning."""
        values = [20.0, 35.0]  # +15°C
        timestamps = [0.0, 30.0]  # 30 seconds = 0.5 min → 30/min rate
        rate_limit = {"max_per_minute": 5.0, "alarm_if_exceeded": False}

        errors = self.validator.validate_rate_of_change(
            "point-1", "supply_air_temperature_sensor", values, timestamps, rate_limit
        )
        assert len(errors) == 1
        assert errors[0].category == ValidationErrorCategory.RATE_LIMIT_EXCEEDED
        assert errors[0].severity == "warning"

    def test_rate_limit_exceeded_triggers_error_when_alarm_set(self) -> None:
        """alarm_if_exceeded=True upgrades severity to error."""
        values = [20.0, 35.0]
        timestamps = [0.0, 30.0]
        rate_limit = {"max_per_minute": 5.0, "alarm_if_exceeded": True}

        errors = self.validator.validate_rate_of_change(
            "point-1", "supply_air_temperature_sensor", values, timestamps, rate_limit
        )
        assert len(errors) == 1
        assert errors[0].severity == "error"

    def test_rate_within_limit_passes(self) -> None:
        """Gradual change within rate limit produces no errors."""
        values = [20.0, 20.5]  # +0.5°C
        timestamps = [0.0, 60.0]  # 1 minute → 0.5/min rate
        rate_limit = {"max_per_minute": 5.0}

        errors = self.validator.validate_rate_of_change(
            "point-1", "supply_air_temperature_sensor", values, timestamps, rate_limit
        )
        assert errors == []

    def test_rate_single_value_skipped(self) -> None:
        """Single data point cannot compute rate; returns no errors."""
        errors = self.validator.validate_rate_of_change("point-1", "tag", [20.0], [0.0], {"max_per_minute": 1.0})
        assert errors == []


# ---------------------------------------------------------------------------
# TemplateCompletenessCalculator tests
# ---------------------------------------------------------------------------


class TestTemplateCompletenessCalculator:
    def setup_method(self) -> None:
        self.calculator = TemplateCompletenessCalculator()

    def test_template_completeness_all_critical_only(self) -> None:
        """All critical present, no important → 0.7 score."""
        classified_points = [
            {"semantic_tag": "supply_air_temperature_sensor"},
            {"semantic_tag": "supply_air_pressure_sensor"},
            {"semantic_tag": "fan_status"},
        ]
        score = self.calculator.calculate_completeness("ahu", classified_points, AHU_TEMPLATE)
        assert score == pytest.approx(0.7, abs=1e-6)

    def test_template_completeness_all_points(self) -> None:
        """All critical + all important → 1.0 score."""
        classified_points = [
            {"semantic_tag": t}
            for t in [
                "supply_air_temperature_sensor",
                "supply_air_pressure_sensor",
                "fan_status",
                "supply_air_temperature_setpoint",
                "supply_air_static_pressure_setpoint",
                "economizer_position",
            ]
        ]
        score = self.calculator.calculate_completeness("ahu", classified_points, AHU_TEMPLATE)
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_template_completeness_none_present(self) -> None:
        """No matching points → 0.0 score."""
        score = self.calculator.calculate_completeness("ahu", [], AHU_TEMPLATE)
        assert score == 0.0

    def test_template_completeness_calculated_correctly(self) -> None:
        """Partial coverage: 2/3 critical (no important) → 0.7 * 2/3 ≈ 0.467."""
        classified_points = [
            {"semantic_tag": "supply_air_temperature_sensor"},
            {"semantic_tag": "supply_air_pressure_sensor"},
        ]
        score = self.calculator.calculate_completeness("ahu", classified_points, AHU_TEMPLATE)
        expected = (2 / 3) * 0.7
        assert score == pytest.approx(expected, abs=1e-6)

    def test_completeness_grade_assignment(self) -> None:
        """Verify A/B/C/D/F grade thresholds."""
        cases = [
            (0.95, "A"),
            (0.85, "B"),
            (0.75, "C"),
            (0.65, "D"),
            (0.45, "F"),
        ]
        for score, expected_grade in cases:
            assert self.calculator._get_grade(score) == expected_grade

    def test_completeness_report_contains_missing_list(self) -> None:
        """Report lists missing critical points."""
        present_tags = ["supply_air_temperature_sensor"]
        report = self.calculator.generate_completeness_report("ahu", 0.23, present_tags, AHU_TEMPLATE)
        assert "supply_air_pressure_sensor" in report["critical_points_missing"]
        assert "fan_status" in report["critical_points_missing"]
        assert "supply_air_temperature_sensor" in report["critical_points_present"]

    def test_completeness_report_recommendation_incomplete(self) -> None:
        """Score < 0.5 triggers incomplete template recommendation."""
        report = self.calculator.generate_completeness_report("ahu", 0.3, [], AHU_TEMPLATE)
        assert any("incomplete" in r.lower() for r in report["recommendations"])


# ---------------------------------------------------------------------------
# StaticValidationEngine tests
# ---------------------------------------------------------------------------


class TestStaticValidationEngine:
    def setup_method(self) -> None:
        self.engine = StaticValidationEngine()

    def test_data_quality_too_low_triggers_error(self) -> None:
        """Data quality < 0.3 produces DATA_QUALITY_TOO_LOW error."""
        pc = _make_classification(data_quality_score=0.1)
        report = self.engine.validate_classification(pc)
        assert not report.validation_passed
        assert any(e.category == ValidationErrorCategory.DATA_QUALITY_TOO_LOW for e in report.errors)

    def test_data_quality_acceptable_passes(self) -> None:
        """Data quality ≥ 0.3 does not trigger data quality error."""
        pc = _make_classification(data_quality_score=0.5)
        report = self.engine.validate_classification(pc)
        assert not any(e.category == ValidationErrorCategory.DATA_QUALITY_TOO_LOW for e in report.errors)

    def test_conflicting_tags_detected(self) -> None:
        """supply_air_temperature_sensor + return_air_temperature_sensor on same point is flagged."""
        pc = _make_classification(
            semantic_tags=[
                "supply_air_temperature_sensor",
                "return_air_temperature_sensor",
            ]
        )
        report = self.engine.validate_classification(pc)
        assert not report.validation_passed
        assert any(e.category == ValidationErrorCategory.CONFLICTING_TAGS for e in report.errors)

    def test_non_conflicting_tags_pass(self) -> None:
        """Single tag raises no conflict error."""
        pc = _make_classification(semantic_tags=["supply_air_temperature_sensor"])
        report = self.engine.validate_classification(pc)
        assert not any(e.category == ValidationErrorCategory.CONFLICTING_TAGS for e in report.errors)

    def test_validation_passed_true_when_no_errors(self) -> None:
        """Clean classification with good quality and single tag passes."""
        pc = _make_classification(data_quality_score=0.9)
        report = self.engine.validate_classification(pc)
        assert report.validation_passed is True

    def test_validation_report_structure(self) -> None:
        """ValidationReport has all required fields."""
        pc = _make_classification()
        report = self.engine.validate_classification(pc)
        assert hasattr(report, "classification_id")
        assert hasattr(report, "validation_passed")
        assert hasattr(report, "errors")
        assert hasattr(report, "warnings")
        assert hasattr(report, "completeness_score")
        assert hasattr(report, "validation_timestamp")
        assert isinstance(report.errors, list)
        assert isinstance(report.warnings, list)
        assert 0.0 <= report.completeness_score <= 1.0

    def test_equipment_batch_validation_aggregates(self) -> None:
        """Batch validation aggregates errors across all points and scores completeness."""
        # All three critical points for AHU
        pc1 = _make_classification(point_id="p1", semantic_tags=["supply_air_temperature_sensor"])
        pc2 = _make_classification(point_id="p2", semantic_tags=["supply_air_pressure_sensor"])
        pc3 = _make_classification(point_id="p3", semantic_tags=["fan_status"])

        report = self.engine.validate_equipment_batch("ahu", [pc1, pc2, pc3])
        # 3/3 critical covered → completeness = 0.7
        assert report.completeness_score == pytest.approx(0.7, abs=1e-6)
        assert report.validation_passed is True

    def test_equipment_batch_low_completeness_fails(self) -> None:
        """Batch with < 50% completeness marks validation_passed False."""
        pc1 = _make_classification(point_id="p1", semantic_tags=["fan_status"])
        report = self.engine.validate_equipment_batch("ahu", [pc1])
        # 1/3 critical → 0.7 * 1/3 ≈ 0.233 → fails completeness gate
        assert report.validation_passed is False

    def test_high_safety_class_point_structure(self) -> None:
        """HIGH safety class points are classified correctly and appear in report."""
        pc = _make_classification(highest_safety_class=SafetyClass.HIGH)
        report = self.engine.validate_classification(pc)
        # Safety class itself doesn't auto-fail; validation_passed reflects other checks
        assert report.classification_id == pc.point_id

    def test_validation_timestamp_is_iso_format(self) -> None:
        """Validation timestamp is a valid ISO datetime string."""
        pc = _make_classification()
        report = self.engine.validate_classification(pc)
        # Should not raise
        dt = datetime.fromisoformat(report.validation_timestamp)
        assert dt is not None

    def test_conflicting_heating_and_cooling_commands(self) -> None:
        """heating_command + cooling_command conflict is detected."""
        pc = _make_classification(semantic_tags=["heating_command", "cooling_command"])
        report = self.engine.validate_classification(pc)
        conflict_errors = [e for e in report.errors if e.category == ValidationErrorCategory.CONFLICTING_TAGS]
        assert len(conflict_errors) >= 1

    def test_no_historic_values_skips_rate_check(self) -> None:
        """Missing historic values does not raise and produces no rate errors."""
        pc = _make_classification(historic_values=None)
        report = self.engine.validate_classification(pc)
        assert not any(
            e.category == ValidationErrorCategory.RATE_LIMIT_EXCEEDED for e in report.errors + report.warnings
        )
