"""Static validation engine coordinator.

Phase 162: Semantic Control Foundation — Plan 03.
Orchestrates bounds checking, rate-of-change validation, data quality gating,
tag conflict detection, and template completeness scoring.

This is the safety guard that runs at classification time before the review queue.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.models.validation_errors import (
    ValidationError,
    ValidationErrorCategory,
    ValidationReport,
)
from app.services.simbiot.validators.bounds_validator import BoundsValidator
from app.services.simbiot.validators.template_completeness import (
    TemplateCompletenessCalculator,
)

if TYPE_CHECKING:
    from app.models.point_classification import PointClassification


class StaticValidationEngine:
    """Validates point classifications against semantic rules and engineering constraints.

    This is the safety guard that runs at classification time, before review queue.
    """

    # Pairs of tags that are logically mutually exclusive on a single point.
    _CONFLICT_PAIRS: list[tuple[str, str]] = [
        ("supply_air_temperature_sensor", "return_air_temperature_sensor"),
        ("heating_command", "cooling_command"),
        ("compressor_status", "economizer_position"),
    ]

    def __init__(self) -> None:
        self.bounds_validator = BoundsValidator()
        self.completeness_calculator = TemplateCompletenessCalculator()
        self.equipment_templates = self._load_equipment_templates()

    # ------------------------------------------------------------------
    # Template registry
    # ------------------------------------------------------------------

    @staticmethod
    def _load_equipment_templates() -> dict[str, dict[str, list[str]]]:
        """Return expected point templates for each equipment type."""
        return {
            "ahu": {
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
            },
            "fcu": {
                "critical_points": [
                    "space_temperature_sensor",
                    "valve_command",
                    "fan_status",
                ],
                "important_points": [
                    "space_temperature_setpoint",
                    "cooling_command",
                    "heating_command",
                ],
            },
            "chiller": {
                "critical_points": [
                    "leaving_chilled_water_temperature_sensor",
                    "entering_chilled_water_temperature_sensor",
                    "compressor_status",
                ],
                "important_points": [
                    "chilled_water_setpoint",
                    "approach_temperature",
                    "operating_hours",
                ],
            },
        }

    # ------------------------------------------------------------------
    # Tag config helper (wired to dictionary service from Plan 162-01)
    # ------------------------------------------------------------------

    def _get_tag_config(self, tag: str) -> Any:
        """Return SemanticTag config from dictionary service.

        Returns None when dictionary service is not wired in (test/standalone use).
        """
        # Deferred import to avoid circular dependency; dictionary service may not
        # be available in all deployment contexts.
        try:
            from app.services.simbiot.semantic_dictionary import SemanticDictionaryService

            svc = SemanticDictionaryService()
            svc.load()
            return svc.get_tag(tag)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_tag_conflicts(self, tags: list[str]) -> list[dict[str, Any]]:
        """Detect logically conflicting semantic tags on the same point."""
        conflicts = []
        for tag1, tag2 in self._CONFLICT_PAIRS:
            if tag1 in tags and tag2 in tags:
                conflicts.append(
                    {
                        "tags": [tag1, tag2],
                        "description": f"{tag1} and {tag2}",
                    }
                )
        return conflicts

    # ------------------------------------------------------------------
    # Single-point validation
    # ------------------------------------------------------------------

    def validate_classification(
        self,
        classification: PointClassification,
        historic_values: dict | None = None,
    ) -> ValidationReport:
        """Run all static validations on a point classification.

        Args:
            classification: The PointClassification to validate.
            historic_values: Optional dict with 'values' and 'timestamps' lists
                             for rate-of-change checking.

        Returns:
            ValidationReport with pass/fail status and all errors/warnings.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # 1. Validate bounds (if current value available)
        if classification.current_value is not None:
            for tag in classification.semantic_tags:
                tag_config = self._get_tag_config(tag)
                if tag_config and tag_config.validation_rules:
                    bounds = tag_config.validation_rules.get("bounds")
                    if bounds:
                        bounds_errors = self.bounds_validator.validate_point_value(
                            classification.point_id, tag, classification.current_value, bounds
                        )
                        errors.extend(bounds_errors)

        # 2. Validate rate of change (if historic data provided)
        hv = historic_values or classification.historic_values or {}
        if len(hv.get("values", [])) >= 2:
            for tag in classification.semantic_tags:
                tag_config = self._get_tag_config(tag)
                if tag_config and tag_config.validation_rules:
                    rate_limit = tag_config.validation_rules.get("rate_of_change")
                    if rate_limit:
                        rate_errors = self.bounds_validator.validate_rate_of_change(
                            classification.point_id,
                            tag,
                            hv["values"],
                            hv["timestamps"],
                            rate_limit,
                        )
                        # Rate violations are warnings unless alarm_if_exceeded is set
                        for err in rate_errors:
                            if err.severity == "error":
                                errors.append(err)
                            else:
                                warnings.append(err)

        # 3. Validate data quality score
        if classification.data_quality_score < 0.3:
            errors.append(
                ValidationError(
                    error_id=f"{classification.point_id}_data_quality_low",
                    category=ValidationErrorCategory.DATA_QUALITY_TOO_LOW,
                    severity="error",
                    message=(
                        f"Data quality score {classification.data_quality_score:.2f} too low for control decisions"
                    ),
                    point_id=classification.point_id,
                    suggestion="Investigate sensor reliability before enabling control",
                )
            )

        # 4. Check for conflicting tags
        for conflict in self._detect_tag_conflicts(classification.semantic_tags):
            errors.append(
                ValidationError(
                    error_id=f"{classification.point_id}_conflict",
                    category=ValidationErrorCategory.CONFLICTING_TAGS,
                    severity="error",
                    message=f"Conflicting semantic tags: {conflict['tags']}",
                    point_id=classification.point_id,
                    suggestion=(f"Review classification - point cannot be both {conflict['description']}"),
                )
            )

        return ValidationReport(
            classification_id=classification.point_id,
            validation_passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            completeness_score=0.0,  # Meaningless for a single point
            validation_timestamp=datetime.utcnow().isoformat(),
        )

    # ------------------------------------------------------------------
    # Equipment-batch validation
    # ------------------------------------------------------------------

    def validate_equipment_batch(
        self,
        equipment_type: str,
        classifications: list[PointClassification],
    ) -> ValidationReport:
        """Validate a batch of classifications belonging to one equipment.

        Aggregates per-point errors and adds template-completeness scoring.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # 1. Calculate template completeness
        present_tags = [tag for pc in classifications for tag in pc.semantic_tags]
        template = self.equipment_templates.get(equipment_type.lower(), {})
        completeness_score = self.completeness_calculator.calculate_completeness(
            equipment_type,
            [{"semantic_tag": tag} for tag in present_tags],
            template,
        )

        # 2. Validate each point
        for classification in classifications:
            single_report = self.validate_classification(classification)
            errors.extend(single_report.errors)
            warnings.extend(single_report.warnings)

        return ValidationReport(
            classification_id=equipment_type,
            validation_passed=len(errors) == 0 and completeness_score >= 0.5,
            errors=errors,
            warnings=warnings,
            completeness_score=completeness_score,
            validation_timestamp=datetime.utcnow().isoformat(),
        )
