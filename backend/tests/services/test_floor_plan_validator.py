"""Tests for floor plan validator service.

Tests coordinate validation, overlap detection, bounding box checks,
equipment type validation, and zone coverage analysis.
"""

from app.services.floor_plan_validator import (
    FloorPlanValidator,
    ValidationReport,
    get_floor_plan_validator,
)


def _make_extraction(equipment=None, floors=None, zones=None):
    """Helper to build an extraction result dict."""
    return {
        "equipment": equipment or [],
        "floors": floors or [],
        "zones": zones or [],
    }


def _make_equipment(name="EQ-1", eq_type="fcu", floor="L1", x=50.0, y=40.0, zone="A"):
    """Helper to create equipment dict."""
    return {
        "name": name,
        "equipment_type": eq_type,
        "floor": floor,
        "x": x,
        "y": y,
        "zone": zone,
        "confidence": 0.95,
    }


def _make_floor(level="L1", height=3.2, width=100, depth=80):
    """Helper to create floor definition."""
    return {"level": level, "height": height, "width": width, "depth": depth}


def _make_zone(zone_id="Zone-L1-A", floor="L1", zone_type="open_office", equipment=None):
    """Helper to create zone definition."""
    return {
        "zone_id": zone_id,
        "floor": floor,
        "zone_type": zone_type,
        "equipment": equipment or [],
    }


class TestFloorPlanValidatorValid:
    """Test valid extraction results pass validation."""

    def test_valid_extraction_passes(self):
        """A well-formed extraction passes all checks."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[
                _make_equipment("S002-FCU-L1-A", "fcu", "L1", 30, 40),
                _make_equipment("S002-AHU-L1-B", "ahu", "L1", 60, 40),
            ],
            floors=[_make_floor("L1")],
            zones=[_make_zone("Zone-L1-A", "L1")],
        )
        report = validator.validate_extraction(result)
        assert report.valid is True
        assert len(report.errors) == 0
        assert report.stats["equipment_count"] == 2

    def test_empty_equipment_is_error(self):
        """Empty equipment list is an error."""
        validator = FloorPlanValidator()
        result = _make_extraction(equipment=[], floors=[_make_floor("L1")])
        report = validator.validate_extraction(result)
        assert report.valid is False
        assert any("No equipment" in e for e in report.errors)


class TestZeroCoordinates:
    """Test zero-coordinate rejection."""

    def test_zero_coordinates_flagged(self):
        """Equipment at (0, 0) is flagged as error."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[_make_equipment("EQ-BAD", "fcu", "L1", 0.0, 0.0)],
            floors=[_make_floor("L1")],
            zones=[_make_zone()],
        )
        report = validator.validate_extraction(result)
        assert any("zero coordinates" in e for e in report.errors)

    def test_nonzero_coordinates_pass(self):
        """Equipment at non-zero coordinates passes."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[_make_equipment("EQ-OK", "fcu", "L1", 10.0, 20.0)],
            floors=[_make_floor("L1")],
            zones=[_make_zone()],
        )
        report = validator.validate_extraction(result)
        zero_errors = [e for e in report.errors if "zero coordinates" in e]
        assert len(zero_errors) == 0


class TestOverlapDetection:
    """Test equipment overlap detection."""

    def test_overlapping_equipment_detected(self):
        """Two equipment on same floor within 0.5m triggers warning."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[
                _make_equipment("EQ-1", "fcu", "L1", 50.0, 40.0),
                _make_equipment("EQ-2", "fcu", "L1", 50.1, 40.1),  # ~0.14m apart
            ],
            floors=[_make_floor("L1")],
            zones=[_make_zone()],
        )
        report = validator.validate_extraction(result)
        assert report.stats["overlap_count"] > 0
        assert any("overlap" in w for w in report.warnings)

    def test_distant_equipment_no_overlap(self):
        """Equipment far apart do not trigger overlap warning."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[
                _make_equipment("EQ-1", "fcu", "L1", 10.0, 10.0),
                _make_equipment("EQ-2", "fcu", "L1", 50.0, 50.0),
            ],
            floors=[_make_floor("L1")],
            zones=[_make_zone()],
        )
        report = validator.validate_extraction(result)
        assert report.stats["overlap_count"] == 0

    def test_overlap_different_floors_ignored(self):
        """Equipment on different floors at same position are not overlapping."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[
                _make_equipment("EQ-1", "fcu", "L1", 50.0, 40.0),
                _make_equipment("EQ-2", "fcu", "L2", 50.0, 40.0),
            ],
            floors=[_make_floor("L1"), _make_floor("L2")],
            zones=[_make_zone("Zone-L1-A", "L1"), _make_zone("Zone-L2-A", "L2")],
        )
        report = validator.validate_extraction(result)
        assert report.stats["overlap_count"] == 0


class TestBoundingBox:
    """Test out-of-bounds equipment detection."""

    def test_out_of_bounds_equipment_flagged(self):
        """Equipment outside building bounds triggers error."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[_make_equipment("EQ-FAR", "fcu", "L1", 500.0, 40.0)],
            floors=[_make_floor("L1", width=100, depth=80)],
            zones=[_make_zone()],
        )
        report = validator.validate_extraction(result)
        assert any("outside building bounds" in e for e in report.errors)

    def test_in_bounds_equipment_passes(self):
        """Equipment within building bounds passes."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[_make_equipment("EQ-OK", "fcu", "L1", 50.0, 40.0)],
            floors=[_make_floor("L1", width=100, depth=80)],
            zones=[_make_zone()],
        )
        report = validator.validate_extraction(result)
        bounds_errors = [e for e in report.errors if "outside building bounds" in e]
        assert len(bounds_errors) == 0


class TestFloorCoverage:
    """Test empty floor warnings."""

    def test_empty_floor_warning(self):
        """Floor with no equipment triggers warning."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[_make_equipment("EQ-1", "fcu", "L1", 50.0, 40.0)],
            floors=[_make_floor("L1"), _make_floor("L2")],  # L2 has no equipment
            zones=[_make_zone()],
        )
        report = validator.validate_extraction(result)
        assert any("Floor 'L2' has no equipment" in w for w in report.warnings)


class TestEquipmentTypes:
    """Test equipment type validation."""

    def test_invalid_equipment_type_error(self):
        """Invalid equipment type triggers error."""
        validator = FloorPlanValidator()
        result = _make_extraction(
            equipment=[_make_equipment("EQ-BAD", "FOOBAR", "L1", 50.0, 40.0)],
            floors=[_make_floor("L1")],
            zones=[_make_zone()],
        )
        report = validator.validate_extraction(result)
        assert any("invalid type" in e for e in report.errors)

    def test_valid_equipment_types_pass(self):
        """All standard SENTINEL types pass."""
        validator = FloorPlanValidator()
        for eq_type in ["fcu", "ahu", "chiller", "vav", "gen", "ups"]:
            result = _make_extraction(
                equipment=[_make_equipment("EQ", eq_type, "L1", 50.0, 40.0)],
                floors=[_make_floor("L1")],
                zones=[_make_zone()],
            )
            report = validator.validate_extraction(result)
            type_errors = [e for e in report.errors if "invalid type" in e]
            assert len(type_errors) == 0, f"Type '{eq_type}' should be valid"


class TestValidationReport:
    """Test ValidationReport model."""

    def test_to_dict(self):
        """ValidationReport serializes to dict."""
        report = ValidationReport(
            valid=True,
            warnings=["test warning"],
            errors=[],
            stats={"equipment_count": 5, "floor_count": 2, "zone_count": 3, "overlap_count": 0},
        )
        d = report.to_dict()
        assert d["valid"] is True
        assert len(d["warnings"]) == 1
        assert d["stats"]["equipment_count"] == 5


class TestFloorPlanValidatorFactory:
    """Test singleton factory."""

    def test_get_floor_plan_validator_returns_instance(self):
        """Factory returns a FloorPlanValidator instance."""
        v = get_floor_plan_validator()
        assert isinstance(v, FloorPlanValidator)

    def test_get_floor_plan_validator_singleton(self):
        """Factory returns the same instance."""
        v1 = get_floor_plan_validator()
        v2 = get_floor_plan_validator()
        assert v1 is v2
