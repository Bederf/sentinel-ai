"""Phase 236-03: measured model accuracy + real drift verdicts.

Daily job: join logged LSTM forecasts (ml_prediction_log) to telemetry_hourly
actuals on strict UTC (equipment_id, point_name, target_hour) equality and
write rolling MAE/R² per model; for AE models, write rolling score
distribution stats. Drift verdicts compare ONLY measured rows against the
model's own registered training metrics:

  - lstm_forecast: drift_suspected when measured MAE > DRIFT_MAE_RATIO x the
    model's training mae_avg
  - ae_score:      drift_suspected when the rolling median score sits above
    the model's own anomaly threshold (persistent over-threshold means the
    score distribution shifted — or a sustained real fault; either way a
    human reviews)
  - anything without enough joined samples: insufficient_data — never a
    fake verdict (AC-17)

Report-only (AC-18): a drift_suspected verdict creates/updates one advisory
finding per model and marks nothing else. No retrain, no activation change.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from app.config.settings import settings
from app.models.recommendation import ActionRiskLevel, Recommendation, RecommendationStatus

logger = logging.getLogger(__name__)

WINDOWS_DAYS = (7, 30)
MIN_SAMPLES = 24  # joined prediction/actual pairs needed before any verdict
DRIFT_MAE_RATIO = 1.5
SOURCE = "ml_drift_monitor"


def lstm_drift_verdict(measured_mae: float | None, baseline_mae: float | None, n_samples: int) -> str:
    if n_samples < MIN_SAMPLES or measured_mae is None:
        return "insufficient_data"
    if baseline_mae is None or baseline_mae <= 0:
        return "insufficient_data"  # no training reference — fail closed
    return "drift_suspected" if measured_mae > DRIFT_MAE_RATIO * baseline_mae else "ok"


def ae_drift_verdict(score_median: float | None, threshold: float | None, n_samples: int) -> str:
    if n_samples < MIN_SAMPLES or score_median is None:
        return "insufficient_data"
    if threshold is None or threshold <= 0:
        return "insufficient_data"
    return "drift_suspected" if score_median > threshold else "ok"


class MLAccuracyService:
    """Compute rolling measured accuracy and report-only drift findings."""

    def __init__(self, database_url: str | None = None):
        # Same DSN pattern as SupabaseRetentionService (never bare
        # os.getenv("DATABASE_URL") in APScheduler context).
        self._db_url = database_url or os.environ.get("DATABASE_URL_DIRECT") or settings.database_url

    def _db_connect(self):
        import psycopg2

        return psycopg2.connect(self._db_url)

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def _lstm_window_stats(self, window_days: int) -> list[tuple]:
        """(model_id, site_id, n, mae, r2) per model from the forecasts↔actuals join."""
        conn = self._db_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH joined AS (
                        SELECT p.model_id,
                               p.site_id,
                               p.predicted_value::float AS pred,
                               t.value_avg::float AS actual
                        FROM ml_prediction_log p
                        JOIN telemetry_hourly t
                          ON t.site_id = p.site_id
                         AND t.equipment_id = p.equipment_id
                         AND t.point_name = p.point_name
                         AND t.hour_bucket = p.target_hour
                        WHERE p.model_kind = 'lstm_forecast'
                          AND p.predicted_at > now() - make_interval(days => %s)
                          AND p.target_hour <= now()
                          AND t.value_avg IS NOT NULL
                    )
                    SELECT model_id,
                           site_id,
                           count(*),
                           avg(abs(pred - actual)),
                           CASE WHEN var_pop(actual) > 0
                                THEN 1.0 - (avg((pred - actual) ^ 2) / var_pop(actual))
                                ELSE NULL END
                    FROM joined
                    GROUP BY model_id, site_id
                    """,
                    (window_days,),
                )
                return cur.fetchall()
        finally:
            conn.close()

    def _ae_window_stats(self, window_days: int) -> list[tuple]:
        """(model_id, site_id, n, score_median, score_p95, threshold) per AE model."""
        conn = self._db_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT model_id,
                           site_id,
                           count(*),
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY predicted_value),
                           percentile_cont(0.95) WITHIN GROUP (ORDER BY predicted_value),
                           max(threshold)
                    FROM ml_prediction_log
                    WHERE model_kind = 'ae_score'
                      AND predicted_at > now() - make_interval(days => %s)
                      AND predicted_value IS NOT NULL
                    GROUP BY model_id, site_id
                    """,
                    (window_days,),
                )
                return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _registry_baseline_mae(model_id: str) -> float | None:
        try:
            from ml.registry import get_model_registry

            entry = get_model_registry().get_model(model_id)
            metrics = (entry or {}).get("metrics") or {}
            mae = metrics.get("mae_avg") or metrics.get("mae")
            return float(mae) if mae is not None else None
        except Exception as e:
            logger.debug("[ML-ACC] Registry baseline lookup failed for %s: %s", model_id, e)
            return None

    async def compute_rolling_accuracy(self) -> dict[str, Any]:
        """Write measured accuracy rows for every model with logged predictions."""
        import asyncio

        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        now = datetime.now(UTC).isoformat()
        written = 0
        verdicts: dict[str, str] = {}
        # model_id → real site_id, carried from ml_prediction_log (no string-parsing).
        sites: dict[str, str | None] = {}

        for window in WINDOWS_DAYS:
            # Multi-second GROUP BY scans over telemetry_hourly — run off the event loop.
            lstm_rows = await asyncio.to_thread(self._lstm_window_stats, window)
            for model_id, site_id, n, mae, r2 in lstm_rows:
                baseline_mae = self._registry_baseline_mae(str(model_id))
                verdict = lstm_drift_verdict(float(mae) if mae is not None else None, baseline_mae, int(n))
                await (
                    client.table("ml_model_accuracy")
                    .insert(
                        {
                            "model_id": str(model_id),
                            "site_id": site_id,
                            "model_kind": "lstm_forecast",
                            "window_days": window,
                            "n_samples": int(n),
                            "mae": float(mae) if mae is not None else None,
                            "r2": float(r2) if r2 is not None else None,
                            "baseline_mae": baseline_mae,
                            "drift_verdict": verdict,
                            "computed_at": now,
                        }
                    )
                    .execute()
                )
                written += 1
                if window == 7:
                    verdicts[str(model_id)] = verdict
                    sites[str(model_id)] = site_id

            ae_rows = await asyncio.to_thread(self._ae_window_stats, window)
            for model_id, site_id, n, median, p95, threshold in ae_rows:
                verdict = ae_drift_verdict(
                    float(median) if median is not None else None,
                    float(threshold) if threshold is not None else None,
                    int(n),
                )
                await (
                    client.table("ml_model_accuracy")
                    .insert(
                        {
                            "model_id": str(model_id),
                            "site_id": site_id,
                            "model_kind": "ae_score",
                            "window_days": window,
                            "n_samples": int(n),
                            "score_median": float(median) if median is not None else None,
                            "score_p95": float(p95) if p95 is not None else None,
                            "baseline_threshold": float(threshold) if threshold is not None else None,
                            "drift_verdict": verdict,
                            "computed_at": now,
                        }
                    )
                    .execute()
                )
                written += 1
                if window == 7:
                    verdicts[str(model_id)] = verdict
                    sites[str(model_id)] = site_id

        findings = await self.reconcile_drift_findings(verdicts, sites)
        result = {"accuracy_rows": written, "models": len(verdicts), "verdicts": verdicts, "findings": findings}
        logger.info("[ML-ACC] accuracy pass complete: %s", result)
        return result

    # ------------------------------------------------------------------
    # Report-only drift findings (one per model, dedup + resolve)
    # ------------------------------------------------------------------

    async def reconcile_drift_findings(self, verdicts: dict[str, str], sites: dict[str, str | None]) -> dict[str, int]:
        from app.database.repositories.recommendation_repository import get_recommendation_repository
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        now = datetime.now(UTC)
        active = (
            await client.table("recommendations")
            .select("*")
            .eq("source", SOURCE)
            .in_("status", ["pending", "advisory_info"])
            .limit(200)
            .execute()
        )
        active_by_model = {str((r.get("metadata") or {}).get("model_id") or ""): r for r in active.data or []}
        stats = {"created": 0, "updated": 0, "resolved": 0, "skipped_unknown_site": 0}

        for model_id, verdict in verdicts.items():
            row = active_by_model.get(model_id)
            if verdict == "drift_suspected":
                if row is None:
                    # Real site carried from ml_prediction_log — never a fabricated default.
                    site_id = sites.get(model_id)
                    if not site_id:
                        # No site attribution → cannot create a correct finding; skip rather
                        # than misattribute (Production Reality Rule). The measured accuracy
                        # row is still written; a human sees it via the ml_model_accuracy table.
                        logger.warning("[ML-ACC] drift on %s has no site_id — skipping finding", model_id)
                        stats["skipped_unknown_site"] += 1
                        continue
                    rec = Recommendation(
                        site_id=site_id,
                        timestamp=now.replace(tzinfo=None),
                        action_type="ml_model_drift",
                        risk_level=ActionRiskLevel.MEDIUM,
                        target_equipment=f"{site_id.upper()}-ML-{model_id}",
                        action={
                            "type": "manual_operator_review",
                            "rule_key": "ml_drift.measured_accuracy",
                            "auto_actionable": False,
                        },
                        reason=(
                            f"Measured accuracy drift on model {model_id}: rolling 7d performance "
                            "degraded beyond the model's own training reference. Review before "
                            "trusting its outputs; retraining/activation stays a human decision."
                        ),
                        expected_impact={"category": "ml_drift", "manual_action_required": True},
                        confidence="high",
                        confidence_score=0.9,
                        profile="ml_drift_monitor",
                        status=RecommendationStatus.ADVISORY_INFO,
                        requires_approval=False,
                        source=SOURCE,
                        source_type="deterministic_rule",
                        shadow_mode=False,
                        metadata={
                            "model_id": model_id,
                            "first_observed_at": now.isoformat(),
                            "last_observed_at": now.isoformat(),
                            "observation_count": 1,
                        },
                    )
                    await get_recommendation_repository().create(rec)
                    stats["created"] += 1
                else:
                    metadata = dict(row.get("metadata") or {})
                    metadata.update(
                        {
                            "last_observed_at": now.isoformat(),
                            "observation_count": int(metadata.get("observation_count") or 1) + 1,
                        }
                    )
                    await client.table("recommendations").update({"metadata": metadata}).eq("id", row["id"]).execute()
                    stats["updated"] += 1
            elif verdict == "ok" and row is not None:
                metadata = dict(row.get("metadata") or {})
                metadata.update({"resolved_at": now.isoformat(), "resolution_reason": "accuracy_recovered"})
                await (
                    client.table("recommendations")
                    .update({"status": RecommendationStatus.EXPIRED.value, "metadata": metadata})
                    .eq("id", row["id"])
                    .execute()
                )
                stats["resolved"] += 1
            # insufficient_data: leave any existing finding untouched (no fake all-clear)
        return stats


_service: MLAccuracyService | None = None


def get_ml_accuracy_service() -> MLAccuracyService:
    global _service
    if _service is None:
        _service = MLAccuracyService()
    return _service
