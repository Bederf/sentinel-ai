import pytest

from app.services.equipment_baseline_rollup_service import EquipmentBaselineRollupService


def _service(window: int = 8) -> EquipmentBaselineRollupService:
    service = EquipmentBaselineRollupService.__new__(EquipmentBaselineRollupService)
    service.window = window
    return service


def test_rollup_uses_tolerance_as_sigma_until_window_is_full():
    service = _service(window=8)

    result = service._rollup_element(
        values=[10.0, 12.0, 14.0, 16.0],
        element_id="bearing_temp",
        unit="degC",
        tolerance=5.0,
        captured_at="2026-07-05T08:00:00Z",
        source_record_id="record-1",
    )

    assert result["value"] == 13.0
    assert result["sigma"] == 5.0
    assert result["n"] == 4
    assert result["source_record_id"] == "record-1"


def test_rollup_uses_observed_sigma_when_window_is_full():
    service = _service(window=4)

    result = service._rollup_element(
        values=[10.0, 12.0, 14.0, 16.0],
        element_id="bearing_temp",
        unit="degC",
        tolerance=5.0,
        captured_at="2026-07-05T08:00:00Z",
        source_record_id="record-1",
    )

    assert result["value"] == 13.0
    assert result["sigma"] == pytest.approx(2.582, abs=0.001)
    assert result["n"] == 4


def test_group_numeric_readings_accepts_element_id_and_legacy_reading_type():
    readings = [
        {"element_id": "vibration", "numeric_value": 1.2},
        {"reading_type": "vibration", "value": "1.6"},
        {"reading_type": "vibration", "value": "not numeric"},
        {"reading_type": "oil_pressure", "value": "42"},
    ]

    grouped = EquipmentBaselineRollupService._group_numeric_readings(readings, {"vibration"})

    assert grouped == {"vibration": [1.2, 1.6]}


def test_extract_tolerances_handles_old_flat_and_new_nested_shapes():
    active_baseline = {
        "baseline_values": {
            "flat_value": 12.0,
            "bearing_temp": {"value": 30.0, "tolerance": "3.5"},
            "bad": {"value": 1.0, "tolerance": "n/a"},
        }
    }

    assert EquipmentBaselineRollupService._extract_tolerances(active_baseline) == {"bearing_temp": 3.5}
