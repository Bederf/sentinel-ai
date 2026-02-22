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
)
from app.database.supabase_client import get_supabase_client
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.prediction_repository import PredictionRepository
from app.database.repositories.baseline_repository import BaselineRepository
from app.database.repositories.inspection_repository import InspectionRepository
from app.database.repositories.work_order_repository import get_work_order_repository
from app.database.repositories.workflow_event_repository import get_workflow_event_repository

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


class WorkflowEventResponse(BaseModel):
    """Response containing workflow events."""

    count: int
    events: List[dict]


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
        timeframe=request.timeframe,
    )

    result = await trigger_engine.on_ml_anomaly(equipment_id=request.equipment_id, anomaly=anomaly)

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
        within_threshold=request.max_deviation_percent < 15.0,
    )

    result = await trigger_engine.on_baseline_deviation(equipment_id=request.equipment_id, comparison=comparison)

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
        estimated_repair_hours=request.estimated_repair_hours,
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
        "actual_hours": request.actual_hours,
    }

    result = await trigger_engine.on_repair_completed(
        work_order_id=request.work_order_id, equipment_id=request.equipment_id, completion_data=completion_data
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
        post_baseline=request.post_baseline,
    )

    return result.model_dump()


# ============================================================================
# Query Endpoints
# ============================================================================


@router.get("/triggers/history", response_model=TriggerHistoryResponse)
async def get_trigger_history(equipment_id: Optional[str] = Query(None, description="Filter by equipment ID")):
    """
    Get trigger history, optionally filtered by equipment.
    """
    trigger_engine = get_trigger_engine()
    history = trigger_engine.get_trigger_history(equipment_id)

    return TriggerHistoryResponse(count=len(history), triggers=[t.model_dump() for t in history])


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
        "inspections": [i.model_dump() for i in inspections],
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
        "work_orders": [wo.model_dump() for wo in work_orders],
    }


@router.get("/triggers/baseline-tasks/{equipment_id}")
async def get_pending_baseline_tasks(equipment_id: str):
    """
    Get pending baseline capture tasks for equipment.
    """
    trigger_engine = get_trigger_engine()
    tasks = trigger_engine.get_pending_baseline_tasks(equipment_id)

    return {"equipment_id": equipment_id, "count": len(tasks), "baseline_tasks": [t.model_dump() for t in tasks]}


@router.get("/triggers/effectiveness/{work_order_id}")
async def get_effectiveness_result(work_order_id: str):
    """
    Get effectiveness validation result for work order.
    """
    trigger_engine = get_trigger_engine()
    result = trigger_engine.get_effectiveness_result(work_order_id)

    if not result:
        raise HTTPException(status_code=404, detail=f"No effectiveness result found for work order {work_order_id}")

    return result.model_dump()


@router.get("/events", response_model=WorkflowEventResponse)
async def get_workflow_events(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID"),
    trigger_type: Optional[str] = Query(None, description="Filter by trigger type"),
    limit: int = Query(100, ge=1, le=500, description="Max number of events to return"),
):
    """
    Get workflow event log entries.
    """
    repository = get_workflow_event_repository()
    events = repository.list(equipment_id=equipment_id, trigger_type=trigger_type, limit=limit)

    return WorkflowEventResponse(count=len(events), events=events)


# ============================================================================
# Dashboard Endpoints
# ============================================================================


class DashboardEquipmentItem(BaseModel):
    """Equipment item for workflow dashboard."""

    equipment_id: str
    name: str
    type: str
    current_state: str


class DashboardWorkflowState(BaseModel):
    """Workflow state for dashboard."""

    equipment_id: str
    current_state: str
    state_history: List[dict]
    baseline_summary: dict
    inspection_status: dict
    ml_prediction: Optional[dict]
    active_repairs: List[dict]


class DashboardResponse(BaseModel):
    """Response for workflow dashboard."""

    equipment: List[DashboardEquipmentItem]
    workflow_states: dict  # keyed by equipment_id


def determine_workflow_state(
    has_active_prediction: bool,
    prediction_probability: float,
    has_pending_inspection: bool,
    has_active_work_order: bool,
    has_baseline_deviation: bool,
) -> str:
    """Determine the current workflow state based on various factors."""
    if has_active_work_order:
        return "repair_in_progress"
    if has_pending_inspection:
        return "inspection_pending"
    if has_active_prediction and prediction_probability >= 0.5:
        return "anomaly_detected"
    if has_baseline_deviation:
        return "anomaly_detected"
    return "healthy"


@router.get("/dashboard/equipment", response_model=DashboardResponse)
async def get_dashboard_equipment(site_id: Optional[str] = Query(None, description="Filter by site/building code")):
    """
    Get equipment workflow data for the dashboard.

    Returns equipment list with workflow states, predictions, baselines, and work orders.
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Get building UUID from site_id code
        building_uuid = None
        if site_id:
            building_result = client.table("buildings").select("id").eq("code", site_id).execute()
            if building_result.data:
                building_uuid = building_result.data[0]["id"]

        # Initialize repositories
        equipment_repo = EquipmentRepository()
        prediction_repo = PredictionRepository()
        baseline_repo = BaselineRepository()
        inspection_repo = InspectionRepository()
        work_order_repo = get_work_order_repository()

        # Get equipment
        if building_uuid:
            equipment_list = equipment_repo.get_all(building_id=building_uuid)
        else:
            equipment_list = equipment_repo.get_all()

        dashboard_equipment = []
        workflow_states = {}

        for eq in equipment_list:
            eq_uuid = eq.get("id")
            eq_code = eq.get("code", eq_uuid)
            eq_name = eq.get("name", eq_code)
            eq_type = eq.get("equipment_type") or eq.get("type", "unknown")

            # Get active predictions for this equipment
            predictions = prediction_repo.get_active_by_equipment(eq_uuid) if eq_uuid else []
            has_active_prediction = len(predictions) > 0
            prediction_probability = 0.0
            prediction_data = None

            if predictions:
                pred = predictions[0]
                prediction_probability = pred.get("probability_percent", 0) / 100.0
                prediction_data = {
                    "failure_probability": prediction_probability,
                    "timeframe": pred.get("timeframe", "30 days"),
                    "confidence": pred.get("severity", "medium"),
                    "explanation": pred.get("description", "ML prediction based on sensor data"),
                }

            # Get baseline summary
            try:
                baseline_summary = baseline_repo.get_baseline_summary(eq_uuid) if eq_uuid else {}
            except Exception:
                baseline_summary = {}

            total_baselines = baseline_summary.get("total_baselines", 0)
            has_baseline_deviation = False  # Would need to check recent comparisons

            # Get recent inspections
            try:
                recent_tasks = await inspection_repo.get_tasks_by_equipment(eq_uuid, limit=1) if eq_uuid else []
            except Exception:
                recent_tasks = []

            has_pending_inspection = any(t.get("status") in ("scheduled", "in_progress") for t in recent_tasks)
            last_inspection = recent_tasks[0] if recent_tasks else None

            inspection_status = {
                "last_inspection": last_inspection.get("scheduled_date") if last_inspection else None,
                "status": last_inspection.get("status") if last_inspection else "none",
                "findings": last_inspection.get("completion_notes") if last_inspection else "",
            }

            # Get active work orders
            work_orders = (
                work_order_repo.get_work_orders_for_equipment(eq_uuid, status="in_progress", limit=5) if eq_uuid else []
            )
            has_active_work_order = len(work_orders) > 0

            active_repairs = [
                {
                    "id": wo.get("code", wo.get("id")),
                    "title": wo.get("title"),
                    "priority": wo.get("priority"),
                    "status": wo.get("status"),
                }
                for wo in work_orders
            ]

            # Determine workflow state
            current_state = determine_workflow_state(
                has_active_prediction=has_active_prediction,
                prediction_probability=prediction_probability,
                has_pending_inspection=has_pending_inspection,
                has_active_work_order=has_active_work_order,
                has_baseline_deviation=has_baseline_deviation,
            )

            # Build state history from available data
            state_history = []

            # Add onboarding → monitoring transition (default)
            state_history.append(
                {
                    "from": "onboarding",
                    "to": "monitoring",
                    "timestamp": eq.get("created_at", ""),
                    "trigger": "baseline_captured",
                }
            )

            # Add prediction-triggered transitions
            if has_active_prediction:
                state_history.append(
                    {
                        "from": "monitoring",
                        "to": "anomaly_detected",
                        "timestamp": predictions[0].get("created_at", ""),
                        "trigger": "ml_prediction",
                    }
                )

            # Add inspection transitions
            if has_pending_inspection and last_inspection:
                state_history.append(
                    {
                        "from": "anomaly_detected" if has_active_prediction else "monitoring",
                        "to": "inspection_pending",
                        "timestamp": last_inspection.get("created_at", ""),
                        "trigger": "automated_task",
                    }
                )

            # Add work order transitions
            if has_active_work_order:
                state_history.append(
                    {
                        "from": "inspection_pending" if has_pending_inspection else "anomaly_detected",
                        "to": "repair_in_progress",
                        "timestamp": work_orders[0].get("created_at", ""),
                        "trigger": "work_order_created",
                    }
                )

            # Add to dashboard
            dashboard_equipment.append(
                DashboardEquipmentItem(equipment_id=eq_code, name=eq_name, type=eq_type, current_state=current_state)
            )

            workflow_states[eq_code] = DashboardWorkflowState(
                equipment_id=eq_code,
                current_state=current_state,
                state_history=state_history,
                baseline_summary={
                    "total_baselines": total_baselines,
                    "latest_baseline": baseline_summary.get("last_baseline_date"),
                    "deviation_detected": has_baseline_deviation,
                },
                inspection_status=inspection_status,
                ml_prediction=prediction_data,
                active_repairs=active_repairs,
            ).model_dump()

        return DashboardResponse(equipment=dashboard_equipment, workflow_states=workflow_states)

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard data: {str(e)}")


# ============================================================================
# Test Endpoints (for demo/development)
# ============================================================================


@router.post("/test/trigger-ml-anomaly")
async def test_trigger_ml_anomaly(
    equipment_id: str = Query(..., description="Equipment ID"),
    anomaly_type: str = Query("vibration", description="Type of anomaly"),
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
        timeframe="24h",
    )

    result = await trigger_engine.on_ml_anomaly(equipment_id=equipment_id, anomaly=anomaly)

    return result.model_dump()


@router.post("/test/full-workflow")
async def test_full_workflow(equipment_id: str = Query(..., description="Equipment ID")):
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
        probability=0.85,
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
        estimated_repair_hours=4.0,
    )
    result2 = await trigger_engine.on_critical_deficiency(deficiency)
    results.append({"step": "critical_deficiency", "result": result2.model_dump()})

    # Step 3: Repair Completed
    work_order_id = result2.details.get("work_order_id", "WO-TEST-001")
    result3 = await trigger_engine.on_repair_completed(
        work_order_id=work_order_id,
        equipment_id=equipment_id,
        completion_data={"completion_notes": "Bearings replaced", "actual_hours": 3.5},
    )
    results.append({"step": "repair_completed", "result": result3.model_dump()})

    # Step 4: Effectiveness Validation
    pre_baseline = {"baseline_values": {"vibration_rms": 3.5, "motor_current": 152.0}}
    post_baseline = {"baseline_values": {"vibration_rms": 1.2, "motor_current": 145.0}}
    result4 = await trigger_engine.validate_repair_effectiveness(
        equipment_id=equipment_id, work_order_id=work_order_id, pre_baseline=pre_baseline, post_baseline=post_baseline
    )
    results.append({"step": "effectiveness_validation", "result": result4.model_dump()})

    return {"equipment_id": equipment_id, "workflow_steps": len(results), "results": results}
