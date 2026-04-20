from datetime import datetime, timedelta

from app.api import hvac
from app.services import prediction_calculator as prediction_calculator_module
from app.services import prediction_generator as prediction_generator_module
from app.services.condition_scorer import ConditionScorer
from app.services.prediction_calculator import PredictionCalculator
from app.services.prediction_generator import PredictionGeneratorService


def test_hvac_health_formula_weighted_sum_deterministic(monkeypatch):
    config = {
        "generator": {
            "expected_life_years": 20,
            "service_interval_days": 90,
            "weights": {
                "age_factor": 0.2,
                "service_compliance": 0.3,
                "runtime_hours": 0.2,
                "fault_history": 0.3,
            },
            "thresholds": {
                "runtime_hours_warning": 20000,
                "runtime_hours_critical": 40000,
                "age_warning_years": 15,
                "age_critical_years": 18,
                "service_overdue_days_warning": 30,
                "service_overdue_days_critical": 90,
            },
        }
    }
    monkeypatch.setattr(hvac, "load_json", lambda _path: config)
    monkeypatch.setattr(
        hvac,
        "get_health_status",
        lambda score: "healthy" if score >= 90 else "warning" if score >= 50 else "critical",
    )

    equipment = {
        "type": "generator",
        "status": "normal",
        # No install/last_service to keep deterministic fallback factor scores.
    }
    result = hvac.calculate_equipment_health(equipment)

    # Expected factor scores from fallback paths:
    # age=80, service=70, runtime=85 (10k/20k warning), fault_history=100
    expected = (80 * 0.2) + (70 * 0.3) + (85 * 0.2) + (100 * 0.3)
    assert result["health_score"] == round(expected, 1)
    assert result["status"] == "warning"


def test_prediction_calculator_returns_none_for_healthy(monkeypatch):
    monkeypatch.setattr(
        prediction_calculator_module,
        "get_health_thresholds",
        lambda: {"healthy": 90, "warning": 70, "critical": 50},
    )

    prediction = PredictionCalculator._calculate_prediction_from_health(
        equipment={"id": "eqp-001", "name": "Gen 1", "type": "generator", "health_score": 95},
        asset=None,
        work_orders=[],
        alarms=[],
        site={},
        site_name="Site A",
    )
    assert prediction is None


def test_prediction_calculator_probability_increases_with_risk_factors(monkeypatch):
    monkeypatch.setattr(
        prediction_calculator_module,
        "get_health_thresholds",
        lambda: {"healthy": 90, "warning": 70, "critical": 50},
    )
    now = datetime.now()

    base_prediction = PredictionCalculator._calculate_prediction_from_health(
        equipment={"id": "eqp-001", "name": "Gen 1", "type": "generator", "health_score": 65},
        asset=None,
        work_orders=[],
        alarms=[],
        site={},
        site_name="Site A",
    )
    assert base_prediction is not None
    base_probability = base_prediction["probability_percent"]

    work_orders = [
        {
            "reported_date": now - timedelta(days=10),
            "repeat_call": True,
            "fault_code": "bearing",
            "technician_notes": "urgent replacement needed",
        },
        {
            "reported_date": now - timedelta(days=20),
            "repeat_call": True,
            "fault_code": "bearing",
            "technician_notes": "failing and deteriorating",
        },
        {
            "reported_date": now - timedelta(days=30),
            "repeat_call": True,
            "fault_code": "bearing",
            "technician_notes": "recommend replacement soon",
        },
    ]
    alarms = [{"triggered_at": now - timedelta(days=1), "alarm_code": f"A{i}"} for i in range(10)]

    elevated_prediction = PredictionCalculator._calculate_prediction_from_health(
        equipment={"id": "eqp-001", "name": "Gen 1", "type": "generator", "health_score": 65},
        asset=None,
        work_orders=work_orders,
        alarms=alarms,
        site={},
        site_name="Site A",
    )
    assert elevated_prediction is not None
    assert elevated_prediction["probability_percent"] > base_probability
    assert 50 <= elevated_prediction["probability_percent"] <= 95
    assert elevated_prediction["severity"] in {"healthy", "warning", "critical"}


def test_prediction_generator_probability_bounds_and_severity(monkeypatch):
    monkeypatch.setattr(
        prediction_generator_module,
        "get_health_status",
        lambda score: "critical" if score < 50 else "warning" if score < 90 else "healthy",
    )

    service = PredictionGeneratorService.__new__(PredictionGeneratorService)
    service._determine_prediction_type = lambda equipment_type, health_score: "general_failure"
    service._build_evidence = lambda equipment: {}
    service._calculate_financial_impact = lambda equipment_type, severity: {
        "repair_cost": 1,
        "replacement_cost": 2,
        "downtime_cost_per_hour": 3,
        "potential_loss": 4,
    }
    service._get_contributing_factors = lambda equipment: []
    service._get_recommended_action = lambda equipment_type, severity, prediction_type: "Inspect"

    critical = service._generate_prediction({"id": "eqp-1", "type": "generator", "health_score": 0, "site_id": "b1"})
    warning = service._generate_prediction({"id": "eqp-2", "type": "generator", "health_score": 65, "site_id": "b1"})

    assert critical["probability_percent"] == 95  # upper bound cap
    assert critical["severity"] == "critical"
    assert warning["probability_percent"] == 60  # floor for degraded equipment
    assert warning["severity"] == "warning"


def test_prediction_calculator_severity_uses_normalized_states(monkeypatch):
    monkeypatch.setattr(
        prediction_calculator_module,
        "get_health_thresholds",
        lambda: {"healthy": 90, "warning": 70, "critical": 50},
    )

    # Low degraded probability path
    pred_low = PredictionCalculator._calculate_prediction_from_health(
        equipment={"id": "eqp-a", "name": "Eq A", "type": "generator", "health_score": 88},
        asset=None,
        work_orders=[],
        alarms=[],
        site={},
        site_name="Site A",
    )
    assert pred_low is not None
    assert pred_low["severity"] == "healthy"

    now = datetime.now()

    # Warning path (probability uplift via evidence)
    pred_warn = PredictionCalculator._calculate_prediction_from_health(
        equipment={"id": "eqp-b", "name": "Eq B", "type": "generator", "health_score": 65},
        asset=None,
        work_orders=[
            {
                "reported_date": now - timedelta(days=5),
                "repeat_call": True,
                "fault_code": "bearing",
                "technician_notes": "urgent replacement needed",
            },
            {
                "reported_date": now - timedelta(days=10),
                "repeat_call": True,
                "fault_code": "bearing",
                "technician_notes": "failing and deteriorating",
            },
        ],
        alarms=[],
        site={},
        site_name="Site A",
    )
    assert pred_warn is not None
    assert pred_warn["severity"] == "warning"


def test_condition_scorer_rms_monotonicity_and_score_bounds():
    scorer = ConditionScorer()

    low_rms = scorer.calculate_score(
        reading={"rms_total_ms2": 1.0, "peak_frequencies_hz": [25, 50, 75]},
        baseline=None,
        equipment_profile="generator_default",
        asset_class="generator",
    )
    high_rms = scorer.calculate_score(
        reading={"rms_total_ms2": 14.0, "peak_frequencies_hz": [25, 50, 75]},
        baseline=None,
        equipment_profile="generator_default",
        asset_class="generator",
    )

    assert 0 <= low_rms["score"] <= 100
    assert 0 <= high_rms["score"] <= 100
    assert low_rms["score"] > high_rms["score"]
