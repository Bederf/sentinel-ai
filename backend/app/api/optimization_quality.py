"""Quality Gate endpoint for optimization pipeline — Phase 109.

Exposes GET /api/optimization/quality-gate/{site_id} to return the
current quality gate evaluation for a site including all 14 metrics,
per-metric rule results, overall status, and enforcement action.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.config.settings import settings
from app.models.quality_gate import QualityGateStatusResponse, QualityMetricDetail
from app.services.quality_gate_evaluator import QualityGateEvaluator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/quality-gate/{site_id}",
    response_model=QualityGateStatusResponse,
    summary="Evaluate quality gate for a site",
    description=(
        "Collects all 14 quality metrics and evaluates them against the "
        "threshold registry for the current ingestion mode. Returns "
        "per-metric results, overall status, and enforcement action."
    ),
)
async def get_quality_gate(site_id: str):
    """Evaluate quality gate metrics for a site.

    Collects metrics from MonitoringService, CommissioningService,
    MVVerificationService, MLFeedbackService, and audit logs. Evaluates
    against thresholds for the current ingestion mode.

    Args:
        site_id: Site/building identifier (e.g. 'site-002', 'S002')

    Returns:
        QualityGateStatusResponse with full evaluation details

    Raises:
        404: If site_id is invalid/unknown
        500: If metric collection or evaluation fails
    """
    if not site_id or not site_id.strip():
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")

    try:
        evaluator = QualityGateEvaluator()
        from app.services.commissioning_service import CommissioningService

        db_mode = CommissioningService()._get_site_phase(site_id)
        mode = db_mode if db_mode else settings.resolved_ingestion_mode.value

        # Collect all 14 raw metric values
        metrics = await evaluator.collect_metrics(site_id)

        # Evaluate against thresholds for current mode
        result = evaluator.evaluate(mode, metrics, site_id=site_id)

        # Build per-metric detail list
        rule_details = []
        for rr in result.rule_results:
            rule_details.append(
                QualityMetricDetail(
                    metric=rr.metric,
                    value=rr.value,
                    state=rr.state.value,
                    pass_bound=rr.threshold.pass_bound,
                    warn_bound=rr.threshold.warn_bound,
                )
            )

        return QualityGateStatusResponse(
            site_id=site_id,
            ingestion_mode=mode,
            mode=mode,
            thresholds_used=mode,
            metric_values=metrics,
            rule_results=rule_details,
            overall_status=result.overall.value,
            enforcement_action=result.enforcement.value,
            reason_codes=[rc.value for rc in result.reason_codes],
        )

    except Exception as e:
        logger.error(f"Error evaluating quality gate for {site_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Quality gate evaluation failed: {e}",
        )
