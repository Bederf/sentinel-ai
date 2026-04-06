"""Floor Plan Validator - Validate extracted equipment positions and zone coverage.

Catches extraction errors before they reach the 3D Digital Twin view.
Checks coordinates, overlaps, equipment types, zone coverage, and floor assignments.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Valid SENTINEL equipment types (uppercase)
VALID_EQUIPMENT_TYPES = {
    "CHILLER",
    "AHU",
    "FCU",
    "VAV",
    "SPLIT",
    "CT",
    "CRAC",
    "GEN",
    "TX",
    "UPS",
    "ATS",
    "MSB",
    "MTR",
    "PFC",
    "FDR",
    "MV",
    "DB",
    "DALI",
    "LUM",
    "FIRE",
    "ACC",
    "CCTV",
    "BESS",
    "INV",  # Solar/BESS
}

# Minimum distance between equipment in meters
MIN_EQUIPMENT_DISTANCE = 0.5


@dataclass
class ValidationReport:
    """Result of floor plan validation.

    Attributes:
        valid: True if no errors found (warnings are OK).
        warnings: Non-critical issues that should be reviewed.
        errors: Critical issues that must be fixed.
        stats: Summary statistics.
    """

    valid: bool = True
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    stats: dict = field(
        default_factory=lambda: {
            "equipment_count": 0,
            "floor_count": 0,
            "zone_count": 0,
            "overlap_count": 0,
        }
    )

    def to_dict(self) -> dict:
        """Convert to serializable dict."""
        return {
            "valid": self.valid,
            "warnings": self.warnings,
            "errors": self.errors,
            "stats": self.stats,
        }


class FloorPlanValidator:
    """Validate floor plan extraction results.

    Checks:
    - All equipment have valid coordinates (not 0,0)
    - No two equipment overlap (min 0.5m distance)
    - All equipment within building bounding box
    - At least 1 equipment per floor (warn if empty)
    - Equipment types are valid SENTINEL types
    - Zone coverage (at least 50% of floor area has assigned zones)
    """

    def validate_extraction(self, extraction_result: dict[str, Any]) -> ValidationReport:
        """Validate a complete extraction result.

        Args:
            extraction_result: Dict with keys: equipment, floors, zones.

        Returns:
            ValidationReport with errors, warnings, and stats.
        """
        report = ValidationReport()

        equipment = extraction_result.get("equipment", [])
        floors = extraction_result.get("floors", [])
        zones = extraction_result.get("zones", [])

        # Compute stats
        report.stats["equipment_count"] = len(equipment)
        report.stats["floor_count"] = len(floors)
        report.stats["zone_count"] = len(zones)

        if not equipment:
            report.errors.append("No equipment found in extraction result")
            report.valid = False
            return report

        # Run all checks
        self._check_zero_coordinates(equipment, report)
        self._check_equipment_overlaps(equipment, report)
        self._check_bounding_box(equipment, floors, report)
        self._check_floor_coverage(equipment, floors, report)
        self._check_equipment_types(equipment, report)
        self._check_zone_coverage(equipment, zones, floors, report)

        # Set valid based on errors
        report.valid = len(report.errors) == 0

        logger.info(f"Validation: valid={report.valid}, errors={len(report.errors)}, warnings={len(report.warnings)}")

        return report

    def _check_zero_coordinates(self, equipment: list[dict], report: ValidationReport) -> None:
        """Reject equipment at exact (0, 0) — likely extraction failure."""
        for eq in equipment:
            x = eq.get("x", 0)
            y = eq.get("y", 0)
            if x == 0.0 and y == 0.0:
                name = eq.get("name", "unknown")
                report.errors.append(f"Equipment '{name}' has zero coordinates (0, 0) — likely extraction failure")

    def _check_equipment_overlaps(self, equipment: list[dict], report: ValidationReport) -> None:
        """Check that no two equipment are closer than MIN_EQUIPMENT_DISTANCE."""
        overlap_count = 0
        for i in range(len(equipment)):
            for j in range(i + 1, len(equipment)):
                eq_a = equipment[i]
                eq_b = equipment[j]

                # Only check same floor
                if eq_a.get("floor") != eq_b.get("floor"):
                    continue

                dx = eq_a.get("x", 0) - eq_b.get("x", 0)
                dy = eq_a.get("y", 0) - eq_b.get("y", 0)
                dist = math.sqrt(dx * dx + dy * dy)

                if dist < MIN_EQUIPMENT_DISTANCE:
                    overlap_count += 1
                    name_a = eq_a.get("name", "unknown")
                    name_b = eq_b.get("name", "unknown")
                    report.warnings.append(
                        f"Equipment '{name_a}' and '{name_b}' overlap "
                        f"(distance: {dist:.2f}m, min: {MIN_EQUIPMENT_DISTANCE}m)"
                    )

        report.stats["overlap_count"] = overlap_count

    def _check_bounding_box(
        self,
        equipment: list[dict],
        floors: list[dict],
        report: ValidationReport,
    ) -> None:
        """Check all equipment are within building bounding box."""
        if not floors:
            return

        # Determine max building dimensions from floors
        max_width = max((f.get("width", 200) for f in floors), default=200)
        max_depth = max((f.get("depth", 200) for f in floors), default=200)

        for eq in equipment:
            x = eq.get("x", 0)
            y = eq.get("y", 0)
            name = eq.get("name", "unknown")

            if x < -10 or x > max_width + 10:
                report.errors.append(f"Equipment '{name}' x={x:.1f} outside building bounds (0 to {max_width:.0f}m)")
            if y < -10 or y > max_depth + 10:
                report.errors.append(f"Equipment '{name}' y={y:.1f} outside building bounds (0 to {max_depth:.0f}m)")

    def _check_floor_coverage(
        self,
        equipment: list[dict],
        floors: list[dict],
        report: ValidationReport,
    ) -> None:
        """Warn if any defined floor has no equipment."""
        if not floors:
            return

        equipment_floors = {eq.get("floor") for eq in equipment}

        for floor_def in floors:
            level = floor_def.get("level", "")
            if level and level not in equipment_floors:
                report.warnings.append(f"Floor '{level}' has no equipment — may indicate extraction gap")

    def _check_equipment_types(self, equipment: list[dict], report: ValidationReport) -> None:
        """Check all equipment types are valid SENTINEL types."""
        for eq in equipment:
            eq_type = eq.get("equipment_type", "").upper()
            if eq_type and eq_type not in VALID_EQUIPMENT_TYPES:
                name = eq.get("name", "unknown")
                report.errors.append(
                    f"Equipment '{name}' has invalid type '{eq_type}' — not a recognized SENTINEL equipment type"
                )

    def _check_zone_coverage(
        self,
        equipment: list[dict],
        zones: list[dict],
        floors: list[dict],
        report: ValidationReport,
    ) -> None:
        """Check that at least 50% of floors have zone assignments."""
        if not floors:
            return

        equipment_floors = {eq.get("floor") for eq in equipment}
        zone_floors = {z.get("floor") for z in zones if z.get("floor")}

        if not equipment_floors:
            return

        coverage = len(zone_floors & equipment_floors) / len(equipment_floors)
        if coverage < 0.5:
            report.warnings.append(f"Zone coverage is {coverage:.0%} — less than 50% of floors have assigned zones")


# Singleton
_floor_plan_validator = None


def get_floor_plan_validator() -> FloorPlanValidator:
    """Get or create singleton floor plan validator."""
    global _floor_plan_validator
    if _floor_plan_validator is None:
        _floor_plan_validator = FloorPlanValidator()
    return _floor_plan_validator
