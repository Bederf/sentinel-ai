"""Phase 236-03: prediction-log row builders + drift verdict logic (pure functions)."""

from datetime import UTC, datetime, timedelta

from app.services.ml_accuracy_service import (
    DRIFT_MAE_RATIO,
    MIN_SAMPLES,
    ae_drift_verdict,
    lstm_drift_verdict,
)
from app.services.ml_prediction_logger import build_ae_log_row, build_lstm_log_rows


def _lstm_result():
    return {
        "equipment_id": "S002-CHILLER-B1-001",
        "equipment_type": "chiller",
        "predictions": {"24h": 6.4, "48h": 6.8, "72h": 7.1},
    }


def _lstm_model_info(site_id="site-002", target="chw_supply_temp"):
    return {
        "model_id": "lstm_site-002_chiller_20260701_151158",
        "site_id": site_id,
        "metadata": {"target": target},
    }


class TestLstmLogRows:
    def test_three_horizons_logged(self):
        rows = build_lstm_log_rows(_lstm_result(), _lstm_model_info())
        assert len(rows) == 3
        assert {r["horizon_hours"] for r in rows} == {24, 48, 72}
        assert all(r["point_name"] == "chw_supply_temp" for r in rows)
        assert all(r["model_kind"] == "lstm_forecast" for r in rows)

    def test_target_hour_is_utc_hour_aligned(self):
        rows = build_lstm_log_rows(_lstm_result(), _lstm_model_info())
        for r in rows:
            th = datetime.fromisoformat(r["target_hour"])
            assert th.minute == 0 and th.second == 0 and th.microsecond == 0
            pa = datetime.fromisoformat(r["predicted_at"])
            # target_hour ≈ predicted_at + horizon, floored to the hour
            expected = (
                (pa + timedelta(hours=r["horizon_hours"])).astimezone(UTC).replace(minute=0, second=0, microsecond=0)
            )
            assert th == expected

    def test_global_model_not_logged(self):
        rows = build_lstm_log_rows(_lstm_result(), _lstm_model_info(site_id=None))
        assert rows == []

    def test_missing_target_not_logged(self):
        rows = build_lstm_log_rows(_lstm_result(), _lstm_model_info(target=None))
        assert rows == []

    def test_no_predictions_not_logged(self):
        result = {"equipment_id": "x", "equipment_type": "chiller", "predictions": None}
        assert build_lstm_log_rows(result, _lstm_model_info()) == []

    def test_partial_predictions(self):
        result = _lstm_result()
        result["predictions"]["48h"] = None
        rows = build_lstm_log_rows(result, _lstm_model_info())
        assert {r["horizon_hours"] for r in rows} == {24, 72}


class TestAeLogRow:
    def test_ae_row_built(self):
        result = {
            "equipment_id": "S002-CHILLER-B1-001",
            "equipment_type": "chiller",
            "anomaly_score": 0.91,
            "threshold": 0.93,
        }
        row = build_ae_log_row(result, {"model_id": "ae_x", "site_id": "site-002"})
        assert row["model_kind"] == "ae_score"
        assert row["predicted_value"] == 0.91
        assert row["threshold"] == 0.93
        assert row.get("point_name", True)  # AE has no target

    def test_ae_global_not_logged(self):
        result = {"equipment_id": "x", "anomaly_score": 0.5, "threshold": 0.4}
        assert build_ae_log_row(result, {"model_id": "ae_x", "site_id": None}) is None

    def test_ae_no_score_not_logged(self):
        result = {"equipment_id": "x", "anomaly_score": None}
        assert build_ae_log_row(result, {"model_id": "ae_x", "site_id": "site-002"}) is None


class TestLstmDriftVerdict:
    def test_ok_when_within_ratio(self):
        assert lstm_drift_verdict(measured_mae=1.0, baseline_mae=0.8, n_samples=100) == "ok"

    def test_drift_when_beyond_ratio(self):
        # 0.8 * 1.5 = 1.2 threshold; 1.5 exceeds it
        assert lstm_drift_verdict(measured_mae=1.5, baseline_mae=0.8, n_samples=100) == "drift_suspected"

    def test_insufficient_samples(self):
        assert lstm_drift_verdict(measured_mae=5.0, baseline_mae=0.8, n_samples=MIN_SAMPLES - 1) == "insufficient_data"

    def test_no_baseline_fails_closed(self):
        assert lstm_drift_verdict(measured_mae=1.0, baseline_mae=None, n_samples=100) == "insufficient_data"
        assert lstm_drift_verdict(measured_mae=1.0, baseline_mae=0.0, n_samples=100) == "insufficient_data"

    def test_no_measured_fails_closed(self):
        assert lstm_drift_verdict(measured_mae=None, baseline_mae=0.8, n_samples=100) == "insufficient_data"

    def test_ratio_boundary(self):
        # exactly at ratio is not "beyond" → ok
        assert lstm_drift_verdict(measured_mae=0.8 * DRIFT_MAE_RATIO, baseline_mae=0.8, n_samples=100) == "ok"


class TestAeDriftVerdict:
    def test_ok_below_threshold(self):
        assert ae_drift_verdict(score_median=0.5, threshold=0.9, n_samples=100) == "ok"

    def test_drift_above_threshold(self):
        assert ae_drift_verdict(score_median=1.1, threshold=0.9, n_samples=100) == "drift_suspected"

    def test_insufficient_samples(self):
        assert ae_drift_verdict(score_median=2.0, threshold=0.9, n_samples=MIN_SAMPLES - 1) == "insufficient_data"

    def test_no_threshold_fails_closed(self):
        assert ae_drift_verdict(score_median=0.5, threshold=None, n_samples=100) == "insufficient_data"
