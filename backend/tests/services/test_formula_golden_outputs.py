import json
from pathlib import Path

from app.api import hvac
from app.services.prediction_taxonomy import (
    FORMULA_VERSION_STATIC,
    confidence_from_probability,
    severity_from_probability,
    urgency_from_severity,
)


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "formula_golden_outputs.json"


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_formula_version_is_frozen_to_static():
    fixture = _load_fixture()
    assert FORMULA_VERSION_STATIC == fixture["formula_version"] == "v1.0-static"


def test_prediction_taxonomy_golden_mappings():
    fixture = _load_fixture()

    for row in fixture["severity_by_probability"]:
        assert severity_from_probability(row["probability"]) == row["severity"]

    for row in fixture["confidence_by_probability_default"]:
        assert confidence_from_probability(row["probability"]) == row["confidence"]

    for row in fixture["urgency_by_severity"]:
        assert urgency_from_severity(row["severity"]) == row["urgency"]


def test_hvac_formula_golden_output(monkeypatch):
    fixture = _load_fixture()
    expected = fixture["hvac_health_default_generator_no_dates"]

    config = {
        "generator": {
            "expected_life_years": 20,
            "service_interval_days": 90,
            "weights": {
                "age_factor": 0.2,
                "service_compliance": 0.3,
                "runtime_hours": 0.2,
                "fault_history": 0.3
            },
            "thresholds": {
                "runtime_hours_warning": 20000,
                "runtime_hours_critical": 40000,
                "age_warning_years": 15,
                "age_critical_years": 18,
                "service_overdue_days_warning": 30,
                "service_overdue_days_critical": 90
            }
        }
    }
    monkeypatch.setattr(hvac, "load_json", lambda _path: config)
    monkeypatch.setattr(
        hvac,
        "get_health_status",
        lambda score: "healthy" if score >= 90 else "warning" if score >= 50 else "critical",
    )

    result = hvac.calculate_equipment_health({"type": "generator", "status": "normal"})
    assert result["health_score"] == expected["health_score"]
    assert result["status"] == expected["status"]
    assert result["formula_version"] == expected["formula_version"]
