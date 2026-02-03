"""
SENTINEL Workflow API Endpoints

REST API for workflow orchestration and automated triggers.

Phase 53-02: Automated Triggers & Workflow Automation
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.workflow_orchestrator import (
    get_workflow_orchestrator,
    OnboardAssetRequest,
    OnboardAssetResponse,
    WorkflowStatusResponse,
    MLAnomalyTrigger,
    InspectionTriggerResponse,
    RepairValidationRequest,
    RepairValidationResponse,
)
from app.services.workflow_triggers import (
    get_trigger_engine,
    AnomalyAlert,
    BaselineComparison,
    InspectionDeficiency,
    TriggerResult,
    EffectivenessResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


# ============================================================================
# Request/Response Models
# ============================================================================

class TriggerMLAnomalyRequest(BaseModel):
    """Request to trigger ML anomaly workflow."""
    equipment_id: str
    anomaly_type: str
    description: str
    probability: float = Field(ge=0.0, le=1.0)
    timeframe: str = "24h"


class TriggerBaselineDeviationRequest(BaseModel):
    """Request to trigger baseline deviation workflow."""
    equipment_id: str
    baseline_id: str
    max_deviation_percent: float
    deviating_metrics: dict = {}


class TriggerCriticalDeficiencyRequest(BaseModel):
    """Request to trigger critical deficiency workflow."""
    inspection_id: str
    equipment_id: str
    severity: str  # critical, safety, major, minor
    deficiency_title: str
    deficiency_description: str
    recommended_action: str
    estimated_repair_cost_min: float = 0.0
    estimated_repair_cost_max: float = 0.0
    estimated_repair_hours: float = 0.0


class TriggerRepairCompletedRequest(BaseModel):
    """Request to trigger repair completed workflow."""
    work_order_id: str
    equipment_id: str
    completion_notes: str = ""
    parts_used: list = []
    actual_hours: float = 0.0


class ValidateEffectivenessRequest(BaseModel):
    """Request to validate repair effectiveness."""
    equipment_id: str
    work_order_id: str
    pre_baseline: dict
    post_baseline: dict


class TriggerHistoryResponse(BaseModel):
    """Response containing trigger history."""
    count: int
    triggers: List[dict]


# ============================================================================
# Workflow Orchestrator Endpoints
# ============================================================================

@router.post("/onboard-asset", response_model=OnboardAssetResponse)
async def onboard_asset(request: OnboardAssetRequest):
    """
    Onboard new asset with baseline capture.

    Workflow: ONBOARDING → BASELINE_CAPTURE → MONITORING
    """
    orchestrator = get_workflow_orchestrator()
    return await orchestrator.onboard_asset(request)


@router.get("/status/{equipment_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(equipment_id: str):
    """
    Get current workflow status for equipment.

    Returns current state, state history, active inspection/repair, and baseline status.
    """
    orchestrator = get_workflow_orchestrator()
    return await orchestrator.get_workflow_status(equipment_id)


@router.post("/trigger-inspection", response_model=InspectionTriggerResponse)
async def trigger_inspection_from_anomaly(trigger: MLAnomalyTrigger):
    """
    Trigger inspection from ML anomaly.

    Workflow: MONITORING/ANOMALY_DETECTED → INSPECTION_SCHEDULED
    """
    orchestrator = get_workflow_orchestrator()
    return await orchestrator.trigger_inspection_from_anomaly(trigger)


@router.post("/validate-repair", response_model=RepairValidationResponse)
async def validate_repair_effectiveness(request: RepairValidationRequest):
    """
    Validate repair effectiveness by comparing baselines.

    Workflow: POST_REPAIR_BASELINE → EFFECTIVENESS_VALIDATED → BACK_TO_NORMAL
    """
    orchestrator = get_workflow_orchestrator()
    return await orchestrator.validate_repair_effectiveness(request)


# ============================================================================
# Workflow Trigger Endpoints
# ============================================================================

@router.post("/triggers/ml-anomaly", response_model=dict)
async def trigger_ml_anomaly(request: TriggerMLAnomalyRequest):
    """
    Handle ML anomaly detection trigger.

    Creates inspection task when ML detects anomaly.
    """
    trigger_engine = get_trigger_engine()

    anomaly = AnomalyAlert(
        id=f"anomaly-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        equipment_id=request.equipment_id,
        anomaly_type=request.anomaly_type,
        description=request.description,
        probability=request.probability,
        timeframe=request.timeframe
    )

    result = await trigger_engine.on_ml_anomaly(
        equipment_id=request.equipment_id,
        anomaly=anomaly
    )

    return result.model_dump()


@router.post("/triggers/baseline-deviation", response_model=dict)
async def trigger_baseline_deviation(request: TriggerBaselineDeviationRequest):
    """
    Handle baseline deviation trigger.

    Generates AI recommendation when baseline deviation detected.
    Creates inspection task for critical deviations (>20%).
    """
    trigger_engine = get_trigger_engine()

    comparison = BaselineComparison(
        equipment_id=request.equipment_id,
        baseline_id=request.baseline_id,
        max_deviation_percent=request.max_deviation_percent,
        deviating_metrics=request.deviating_metrics,
        within_threshold=request.max_deviation_percent < 15.0
    )

    result = await trigger_engine.on_baseline_deviation(
        equipment_id=request.equipment_id,
        comparison=comparison
    )

    return result.model_dump()


@router.post("/triggers/critical-deficiency", response_model=dict)
async def trigger_critical_deficiency(request: TriggerCriticalDeficiencyRequest):
    """
    Handle critical deficiency trigger.

    Auto-creates work order for critical/safety deficiencies.
    Schedules pre-repair baseline capture.
    """
    trigger_engine = get_trigger_engine()

    deficiency = InspectionDeficiency(
        id=f"def-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        inspection_id=request.inspection_id,
        equipment_id=request.equipment_id,
        severity=request.severity,
        deficiency_title=request.deficiency_title,
        deficiency_description=request.deficiency_description,
        recommended_action=request.recommended_action,
        estimated_repair_cost_min=request.estimated_repair_cost_min,
        estimated_repair_cost_max=request.estimated_repair_cost_max,
        estimated_repair_hours=request.estimated_repair_hours
    )

    result = await trigger_engine.on_critical_deficiency(deficiency)

    return result.model_dump()


@router.post("/triggers/repair-completed", response_model=dict)
async def trigger_repair_completed(request: TriggerRepairCompletedRequest):
    """
    Handle repair completed trigger.

    Triggers post-repair baseline capture and verification inspection.
    Schedules effectiveness validation.
    """
    trigger_engine = get_trigger_engine()

    completion_data = {
        "completion_notes": request.completion_notes,
        "parts_used": request.parts_used,
        "actual_hours": request.actual_hours
    }

    result = await trigger_engine.on_repair_completed(
        work_order_id=request.work_order_id,
        equipment_id=request.equipment_id,
        completion_data=completion_data
    )

    return result.model_dump()


@router.post("/triggers/validate-effectiveness", response_model=dict)
async def trigger_validate_effectiveness(request: ValidateEffectivenessRequest):
    """
    Validate repair effectiveness by comparing baselines.

    Compares pre/post repair baselines to calculate effectiveness.
    Creates follow-up task if repair unsuccessful.
    Records ML feedback for continuous learning.
    """
    trigger_engine = get_trigger_engine()

    result = await trigger_engine.validate_repair_effectiveness(
        equipment_id=request.equipment_id,
        work_order_id=request.work_order_id,
        pre_baseline=request.pre_baseline,
        post_baseline=request.post_baseline
    )

    return result.model_dump()


# ============================================================================
# Query Endpoints
# ============================================================================

@router.get("/triggers/history", response_model=TriggerHistoryResponse)
async def get_trigger_history(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID")
):
    """
    Get trigger history, optionally filtered by equipment.
    """
    trigger_engine = get_trigger_engine()
    history = trigger_engine.get_trigger_history(equipment_id)

    return TriggerHistoryResponse(
        count=len(history),
        triggers=[t.model_dump() for t in history]
    )


@router.get("/triggers/inspections/{equipment_id}")
async def get_pending_inspections(equipment_id: str):
    """
    Get pending inspection tasks for equipment.
    """
    trigger_engine = get_trigger_engine()
    inspections = trigger_engine.get_pending_inspections(equipment_id)

    return {
        "equipment_id": equipment_id,
        "count": len(inspections),
        "inspections": [i.model_dump() for i in inspections]
    }


@router.get("/triggers/work-orders/{equipment_id}")
async def get_pending_work_orders(equipment_id: str):
    """
    Get pending work orders for equipment.
    """
    trigger_engine = get_trigger_engine()
    work_orders = trigger_engine.get_pending_work_orders(equipment_id)

    return {
        "equipment_id": equipment_id,
        "count": len(work_orders),
        "work_orders": [wo.model_dump() for wo in work_orders]
    }


@router.get("/triggers/baseline-tasks/{equipment_id}")
async def get_pending_baseline_tasks(equipment_id: str):
    """
    Get pending baseline capture tasks for equipment.
    """
    trigger_engine = get_trigger_engine()
    tasks = trigger_engine.get_pending_baseline_tasks(equipment_id)

    return {
        "equipment_id": equipment_id,
        "count": len(tasks),
        "baseline_tasks": [t.model_dump() for t in tasks]
    }


@router.get("/triggers/effectiveness/{work_order_id}")
async def get_effectiveness_result(work_order_id: str):
    """
    Get effectiveness validation result for work order.
    """
    trigger_engine = get_trigger_engine()
    result = trigger_engine.get_effectiveness_result(work_order_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No effectiveness result found for work order {work_order_id}"
        )

    return result.model_dump()


# ============================================================================
# Test Endpoints (for demo/development)
# ============================================================================

@router.post("/test/trigger-ml-anomaly")
async def test_trigger_ml_anomaly(
    equipment_id: str = Query(..., description="Equipment ID"),
    anomaly_type: str = Query("vibration", description="Type of anomaly")
):
    """
    Test endpoint to trigger ML anomaly workflow.

    For demo and development testing.
    """
    trigger_engine = get_trigger_engine()

    anomaly = AnomalyAlert(
        id=f"test-anomaly-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        equipment_id=equipment_id,
        anomaly_type=anomaly_type,
        description=f"Test {anomaly_type} anomaly for {equipment_id}",
        probability=0.85,
        timeframe="24h"
    )

    result = await trigger_engine.on_ml_anomaly(
        equipment_id=equipment_id,
        anomaly=anomaly
    )

    return result.model_dump()


@router.post("/test/full-workflow")
async def test_full_workflow(
    equipment_id: str = Query(..., description="Equipment ID")
):
    """
    Test endpoint to run full workflow cycle.

    Simulates: ML Anomaly → Inspection → Deficiency → Work Order → Repair → Validation

    For demo and development testing.
    """
    trigger_engine = get_trigger_engine()
    results = []

    # Step 1: ML Anomaly
    anomaly = AnomalyAlert(
        id=f"test-anomaly-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        equipment_id=equipment_id,
        anomaly_type="vibration",
        description=f"High vibration detected on {equipment_id}",
        probability=0.85
    )
    result1 = await trigger_engine.on_ml_anomaly(equipment_id, anomaly)
    results.append({"step": "ml_anomaly", "result": result1.model_dump()})

    # Step 2: Critical Deficiency (simulating inspection result)
    deficiency = InspectionDeficiency(
        id=f"def-test-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        inspection_id="insp-test-001",
        equipment_id=equipment_id,
        severity="critical",
        deficiency_title="Bearing failure imminent",
        deficiency_description="Vibration analysis indicates bearing wear beyond tolerance",
        recommended_action="Replace bearings within 48 hours",
        estimated_repair_cost_min=5000.0,
        estimated_repair_cost_max=8000.0,
        estimated_repair_hours=4.0
    )
    result2 = await trigger_engine.on_critical_deficiency(deficiency)
    results.append({"step": "critical_deficiency", "result": result2.model_dump()})

    # Step 3: Repair Completed
    work_order_id = result2.details.get("work_order_id", "WO-TEST-001")
    result3 = await trigger_engine.on_repair_completed(
        work_order_id=work_order_id,
        equipment_id=equipment_id,
        completion_data={"completion_notes": "Bearings replaced", "actual_hours": 3.5}
    )
    results.append({"step": "repair_completed", "result": result3.model_dump()})

    # Step 4: Effectiveness Validation
    pre_baseline = {"baseline_values": {"vibration_rms": 3.5, "motor_current": 152.0}}
    post_baseline = {"baseline_values": {"vibration_rms": 1.2, "motor_current": 145.0}}
    result4 = await trigger_engine.validate_repair_effectiveness(
        equipment_id=equipment_id,
        work_order_id=work_order_id,
        pre_baseline=pre_baseline,
        post_baseline=post_baseline
    )
    results.append({"step": "effectiveness_validation", "result": result4.model_dump()})

    return {
        "equipment_id": equipment_id,
        "workflow_steps": len(results),
        "results": results
    }
