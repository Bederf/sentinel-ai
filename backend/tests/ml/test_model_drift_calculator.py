"""Tests for the ML model drift calculator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ml.models.model_drift_calculator import ModelDriftCalculator


@pytest.fixture()
def calc(tmp_path: Path):
    models_path = tmp_path / "ml_models.json"
    models_path.write_text(
        json.dumps(
            [
                {
                    "model_id": "lstm_chiller_001",
                    "model_type": "lstm",
                    "status": "active",
                    "r_squared_avg": 0.95,
                    "notes": "Chiller LSTM",
                },
                {
                    "model_id": "lstm_ahu_002",
                    "model_type": "lstm",
                    "status": "active",
                    "r_squared_avg": 0.80,
                    "notes": "AHU LSTM",
                },
                {
                    "model_id": "retired_model",
                    "model_type": "lstm",
                    "status": "retired",
                    "r_squared_avg": 0.50,
                    "notes": "Old model",
                },
            ]
        )
    )
    return ModelDriftCalculator(models_path=models_path)


def test_drift_score_no_drift():
    c = ModelDriftCalculator()
    score = c.calculate_drift_score("m1", baseline_r_squared=0.95, recent_r_squared=0.95)
    assert score == 0.0


def test_drift_score_moderate_drift():
    c = ModelDriftCalculator()
    score = c.calculate_drift_score("m1", baseline_r_squared=0.95, recent_r_squared=0.65)
    # 1 - (0.65/0.95) ≈ 0.3158
    assert 0.31 < score < 0.32


def test_drift_score_severe_drift():
    c = ModelDriftCalculator()
    score = c.calculate_drift_score("m1", baseline_r_squared=0.95, recent_r_squared=0.1)
    # 1 - (0.1/0.95) ≈ 0.8947
    assert 0.89 < score < 0.90


def test_drift_score_zero_baseline():
    c = ModelDriftCalculator()
    score = c.calculate_drift_score("m1", baseline_r_squared=0.0, recent_r_squared=0.5)
    assert score == 0.0


def test_drift_score_negative_baseline():
    c = ModelDriftCalculator()
    score = c.calculate_drift_score("m1", baseline_r_squared=-0.5, recent_r_squared=0.5)
    assert score == 0.0


def test_drift_score_clamped_0_to_1():
    c = ModelDriftCalculator()
    # recent > baseline → raw drift negative → clamped to 0
    score = c.calculate_drift_score("m1", baseline_r_squared=0.5, recent_r_squared=0.9)
    assert score == 0.0

    # recent very negative → raw drift > 1 → clamped to 1
    score = c.calculate_drift_score("m1", baseline_r_squared=0.95, recent_r_squared=-1.0)
    assert score == 1.0


def test_drift_score_negative_r_squared():
    """Negative recent_r_squared should still produce a valid clamped score."""
    c = ModelDriftCalculator()
    score = c.calculate_drift_score("m1", baseline_r_squared=0.8, recent_r_squared=-0.5)
    assert 0.0 <= score <= 1.0


def test_drift_score_none_model_id():
    """model_id=None shouldn't crash (it's just a label)."""
    c = ModelDriftCalculator()
    score = c.calculate_drift_score(None, baseline_r_squared=0.9, recent_r_squared=0.7)  # type: ignore[arg-type]
    assert 0.0 <= score <= 1.0


def test_alert_levels():
    c = ModelDriftCalculator()
    assert c._alert_level(0.0) == "ok"
    assert c._alert_level(0.29) == "ok"
    assert c._alert_level(0.3) == "warning"
    assert c._alert_level(0.59) == "warning"
    assert c._alert_level(0.6) == "critical"
    assert c._alert_level(1.0) == "critical"


def test_get_drift_alerts_filters_above_threshold():
    scores = [
        {"model_id": "a", "drift_score": 0.1},
        {"model_id": "b", "drift_score": 0.5},
        {"model_id": "c", "drift_score": 0.8},
        {"model_id": "d", "drift_score": 0.3},
    ]
    alerts = ModelDriftCalculator.get_drift_alerts(scores, threshold=0.3)
    assert len(alerts) == 2
    assert alerts[0]["model_id"] == "c"
    assert alerts[1]["model_id"] == "b"


@pytest.mark.asyncio
async def test_get_all_drift_scores_skips_retired(calc):
    scores = await calc.get_all_drift_scores()
    model_ids = [s["model_id"] for s in scores]
    assert "retired_model" not in model_ids
    assert len(scores) == 2


@pytest.mark.asyncio
async def test_get_all_drift_scores_structure(calc):
    scores = await calc.get_all_drift_scores()
    for s in scores:
        assert "model_id" in s
        assert "model_type" in s
        assert "baseline_r_squared" in s
        assert "drift_score" in s
        assert s["alert_level"] in ("ok", "warning", "critical")
