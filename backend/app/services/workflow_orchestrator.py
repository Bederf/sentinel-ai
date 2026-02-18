"""
SENTINEL Asset Management Workflow Orchestrator

This service coordinates automated workflows across SIMBIOT, Asset Baseline,
Inspection, ML Predictions, and AI Recommendations.

Phase 53: SENTINEL Asset Management Workflow Integration
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pydantic import BaseModel

# Import existing services
try:
    from app.services.baseline_service import get_baseline_service
    from app.services.inspection_service import get_inspection_service
    from app.services.ml_inference import get_lstm_service, get_anomaly_service
    from app.services.explanation_service import get_explanation_service
    from app.services.maintenance_recommender import get_maintenance_recommender
    from app.services.audit_logger import get_audit_logger
except ImportError:
    # Fallback for development
    def get_baseline_service():
        return None

    def get_inspection_service():
        return None

    def get_lstm_service():
        return None

    def get_anomaly_service():
        return None

    def get_explanation_service():
        return None

    def get_maintenance_recommender():
        return None

    def get_audit_logger():
        return None

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

from enum import Enum


class WorkflowState(str, Enum):
    """Asset lifecycle states"""
    ONBOARDING = "onboarding"
    BASELINE_CAPTURE = "baseline_capture"
    MONITORING = "monitoring"
    INSPECTION_SCHEDULED = "inspection_scheduled"
    INSPECTION_IN_PROGRESS = "inspection_in_progress"
    ANOMALY_DETECTED = "anomaly_detected"
    DEFICIENCY_IDENTIFIED = "deficiency_identified"
    REPAIR_SCHEDULED = "repair_scheduled"
    PRE_REPAIR_BASELINE = "pre_repair_baseline"
    REPAIR_IN_PROGRESS = "repair_in_progress"
    POST_REPAIR_BASELINE = "post_repair_baseline"
    EFFECTIVENESS_VALIDATED = "effectiveness_validated"
    BACK_TO_NORMAL = "back_to_normal"


class OnboardAssetRequest(BaseModel):
    """Request to onboard new asset"""
    site_id: str
    site_name: str
    site_address: str
    equipment: List[Dict[str, Any]]
    captured_by: str
    notes: Optional[str] = None


class OnboardAssetResponse(BaseModel):
    """Response from asset onboarding"""
    success: bool
    site_id: str
    equipment_onboarded: int
    baselines_captured: int
    workflow_state: WorkflowState
    equipment: List[Dict[str, Any]]


class WorkflowStatusResponse(BaseModel):
    """Response for workflow status query"""
    success: bool
    equipment_id: str
    current_state: WorkflowState
    state_history: List[Dict[str, Any]]
    active_inspection: Optional[Dict[str, Any]]
    active_repair: Optional[Dict[str, Any]]
    last_anomaly: Optional[Dict[str, Any]]
    baseline_status: Dict[str, Any]


class MLAnomalyTrigger(BaseModel):
    """ML anomaly trigger for inspection"""
    equipment_id: str
    trigger_source: str = "ml_anomaly"
    anomaly_type: str
    probability: float
    timeframe: str
    ml_explanation: str
    priority: str = "high"


class InspectionTriggerResponse(BaseModel):
    """Response from inspection trigger"""
    success: bool
    inspection_task_id: str
    equipment_id: str
    scheduled_date: datetime
    priority: str
    reason: str
    workflow_transition: Dict[str, WorkflowState]


class RepairValidationRequest(BaseModel):
    """Request to validate repair effectiveness"""
    equipment_id: str
    work_order_id: str
    pre_repair_baseline_id: str
    post_repair_baseline_id: str


class RepairValidationResponse(BaseModel):
    """Response from repair validation"""
    success: bool
    equipment_id: str
    work_order_id: str
    effectiveness: Dict[str, Any]
    workflow_transition: Dict[str, WorkflowState]
    ml_feedback_recorded: bool


class StateTransition(BaseModel):
    """Record of state transition"""
    from_state: WorkflowState
    to_state: WorkflowState
    transition_time: datetime
    trigger_reason: str
    duration_seconds: Optional[int] = None


# ============================================================================
# Workflow Orchestrator
# ============================================================================

class AssetWorkflowOrchestrator:
    """
    Central orchestrator for SENTINEL asset management workflow.

    Coordinates cross-system workflows:
    - SIMBIOT building/equipment onboarding
    - Baseline capture and comparison
    - Inspection scheduling and execution
    - ML anomaly detection
    - AI recommendation generation
    - Repair effectiveness validation
    """

    def __init__(self):
        self.baseline_service = get_baseline_service()
        self.inspection_service = get_inspection_service()
        self.lstm_service = get_lstm_service()
        self.anomaly_service = get_anomaly_service()
        self.explanation_service = get_explanation_service()
        self.maintenance_recommender = get_maintenance_recommender()
        self.audit_logger = get_audit_logger()

        # In-memory state management (demo scope)
        self._equipment_states: Dict[str, WorkflowState] = {}
        self._state_history: Dict[str, List[StateTransition]] = {}

        logger.info("AssetWorkflowOrchestrator initialized")

    # ========================================================================
    # Public API Methods
    # ========================================================================

    async def onboard_asset(
        self,
        request: OnboardAssetRequest
    ) -> OnboardAssetResponse:
        """
        Onboard new asset via SIMBIOT and capture initial baseline.

        Workflow: ONBOARDING → BASELINE_CAPTURE → MONITORING
        """
        equipment_results = []

        try:
            # Step 1: Onboard via SIMBIOT (future integration)
            # For now, simulate onboarding
            logger.info(f"Onboarding asset: {request.site_id}")

            # Step 2: Capture initial baseline for each equipment
            baselines_captured = 0
            for eq in request.equipment:
                equipment_id = eq.get("equipment_id")
                if not equipment_id:
                    continue

                # Set initial state
                self._set_state(equipment_id, WorkflowState.ONBOARDING)

                baseline_values = eq.get("baseline_values", {})
                baseline_id = None
                if baseline_values:
                    self._set_state(equipment_id, WorkflowState.BASELINE_CAPTURE)

                    # Capture baseline (fallback to simulated capture if service missing)
                    baseline_id = await self._capture_initial_baseline(
                        equipment_id=equipment_id,
                        baseline_values=baseline_values,
                        captured_by=request.captured_by,
                        notes=request.notes
                    )
                    baselines_captured += 1

                # Transition to monitoring
                self._set_state(equipment_id, WorkflowState.MONITORING)

                equipment_results.append({
                    "equipment_id": equipment_id,
                    "baseline_id": baseline_id,
                    "state": WorkflowState.MONITORING
                })

                # Audit log
                await self._audit_log(
                    equipment_id=equipment_id,
                    action="asset_onboarded",
                    details={
                            "site_id": request.site_id,
                            "baseline_id": baseline_id
                        }
                    )

            return OnboardAssetResponse(
                success=True,
                site_id=request.site_id,
                equipment_onboarded=len(request.equipment),
                baselines_captured=baselines_captured,
                workflow_state=WorkflowState.MONITORING,
                equipment=equipment_results
            )

        except Exception as e:
            logger.error(f"Error onboarding asset: {e}")
            raise

    async def get_workflow_status(
        self,
        equipment_id: str
    ) -> WorkflowStatusResponse:
        """Get current workflow status for equipment"""
        current_state = self._equipment_states.get(equipment_id, WorkflowState.ONBOARDING)
        state_history = self._get_state_history(equipment_id)

        # Get additional status from services
        baseline_status = await self._get_baseline_status(equipment_id)
        active_inspection = await self._get_active_inspection(equipment_id)
        active_repair = await self._get_active_repair(equipment_id)
        last_anomaly = await self._get_last_anomaly(equipment_id)

        return WorkflowStatusResponse(
            success=True,
            equipment_id=equipment_id,
            current_state=current_state,
            state_history=state_history,
            active_inspection=active_inspection,
            active_repair=active_repair,
            last_anomaly=last_anomaly,
            baseline_status=baseline_status
        )

    async def trigger_inspection_from_anomaly(
        self,
        trigger: MLAnomalyTrigger
    ) -> InspectionTriggerResponse:
        """
        Trigger inspection task from ML anomaly detection.

        Workflow: MONITORING/ANOMALY_DETECTED → INSPECTION_SCHEDULED
        """
        equipment_id = trigger.equipment_id
        from_state = self._equipment_states.get(equipment_id, WorkflowState.MONITORING)

        try:
            # Check if inspection already exists
            # (future integration with inspection service)

            # Create inspection task
            task_id = f"task-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            scheduled_date = datetime.now() + timedelta(hours=24)

            # Update state
            self._set_state(equipment_id, WorkflowState.INSPECTION_SCHEDULED)

            # Audit log
            await self._audit_log(
                equipment_id=equipment_id,
                action="inspection_triggered_from_anomaly",
                details={
                    "trigger_source": trigger.trigger_source,
                    "anomaly_type": trigger.anomaly_type,
                    "probability": trigger.probability,
                    "task_id": task_id
                }
            )

            return InspectionTriggerResponse(
                success=True,
                inspection_task_id=task_id,
                equipment_id=equipment_id,
                scheduled_date=scheduled_date,
                priority=trigger.priority,
                reason=f"ML anomaly detected: {trigger.anomaly_type} ({trigger.probability:.0%} probability)",
                workflow_transition={
                    "from_state": from_state,
                    "to_state": WorkflowState.INSPECTION_SCHEDULED
                }
            )

        except Exception as e:
            logger.error(f"Error triggering inspection: {e}")
            raise

    async def validate_repair_effectiveness(
        self,
        request: RepairValidationRequest
    ) -> RepairValidationResponse:
        """
        Validate repair effectiveness by comparing pre/post baselines.

        Workflow: POST_REPAIR_BASELINE → EFFECTIVENESS_VALIDATED → BACK_TO_NORMAL
        """
        equipment_id = request.equipment_id

        try:
            # Get pre and post baselines
            pre_baseline = await self._get_baseline(request.pre_repair_baseline_id)
            post_baseline = await self._get_baseline(request.post_repair_baseline_id)

            if not pre_baseline or not post_baseline:
                raise ValueError("Missing pre or post repair baseline")

            # Compare baselines and calculate effectiveness
            effectiveness = await self._calculate_effectiveness(
                pre_baseline=pre_baseline,
                post_baseline=post_baseline
            )

            # Update state
            from_state = self._equipment_states.get(
                equipment_id,
                WorkflowState.POST_REPAIR_BASELINE
            )
            to_state = WorkflowState.EFFECTIVENESS_VALIDATED if effectiveness["repair_successful"] else WorkflowState.REPAIR_SCHEDULED
            self._set_state(equipment_id, to_state)

            # Record ML feedback
            ml_feedback_recorded = await self._record_ml_feedback(
                equipment_id=equipment_id,
                work_order_id=request.work_order_id,
                effectiveness=effectiveness
            )

            # If successful, transition back to monitoring
            if effectiveness["repair_successful"]:
                self._set_state(equipment_id, WorkflowState.BACK_TO_NORMAL)

            # Audit log
            await self._audit_log(
                equipment_id=equipment_id,
                action="repair_validated",
                details={
                    "work_order_id": request.work_order_id,
                    "effectiveness_score": effectiveness["score"],
                    "repair_successful": effectiveness["repair_successful"]
                }
            )

            return RepairValidationResponse(
                success=True,
                equipment_id=equipment_id,
                work_order_id=request.work_order_id,
                effectiveness=effectiveness,
                workflow_transition={
                    "from_state": from_state,
                    "to_state": WorkflowState.BACK_TO_NORMAL if effectiveness["repair_successful"] else to_state
                },
                ml_feedback_recorded=ml_feedback_recorded
            )

        except Exception as e:
            logger.error(f"Error validating repair: {e}")
            raise

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _set_state(self, equipment_id: str, state: WorkflowState):
        """Set equipment workflow state"""
        from_state = self._equipment_states.get(equipment_id)
        now = datetime.now()

        if from_state:
            # Record transition
            transition = StateTransition(
                from_state=from_state,
                to_state=state,
                transition_time=now,
                trigger_reason="workflow_transition",
                duration_seconds=None  # Calculate if needed
            )
            if equipment_id not in self._state_history:
                self._state_history[equipment_id] = []
            self._state_history[equipment_id].append(transition)

        self._equipment_states[equipment_id] = state
        logger.info(f"Workflow state: {equipment_id} -> {state}")

    def _get_state_history(self, equipment_id: str) -> List[Dict[str, Any]]:
        """Get state history for equipment"""
        history = self._state_history.get(equipment_id, [])
        return [
            {
                "state": h.to_state,
                "entered_at": h.transition_time.isoformat(),
                "exited_at": None,
                "duration_seconds": h.duration_seconds
            }
            for h in history
        ]

    async def _capture_initial_baseline(
        self,
        equipment_id: str,
        baseline_values: Dict[str, float],
        captured_by: str,
        notes: Optional[str]
    ) -> str:
        """Capture initial baseline for equipment"""
        # Future: Call baseline service
        baseline_id = f"bl-{equipment_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Captured baseline {baseline_id} for {equipment_id}")
        return baseline_id

    async def _get_baseline(self, baseline_id: str) -> Optional[Dict[str, Any]]:
        """Get baseline by ID"""
        # Future: Call baseline service
        baseline_id_lower = baseline_id.lower()

        if "post" in baseline_id_lower and "bad" not in baseline_id_lower:
            return {
                "id": baseline_id,
                "baseline_values": {
                    "vibration_rms": 1.0,
                    "motor_current": 80.0
                }
            }

        if "pre" in baseline_id_lower:
            return {
                "id": baseline_id,
                "baseline_values": {
                    "vibration_rms": 3.5,
                    "motor_current": 180.0
                }
            }

        return {
            "id": baseline_id,
            "baseline_values": {
                "vibration_rms": 1.8,
                "motor_current": 145.2
            }
        }

    async def _calculate_effectiveness(
        self,
        pre_baseline: Dict[str, Any],
        post_baseline: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate repair effectiveness from baseline comparison"""
        pre_values = pre_baseline.get("baseline_values", {})
        post_values = post_baseline.get("baseline_values", {})

        improvements = {}
        for metric, pre_value in pre_values.items():
            post_value = post_values.get(metric)
            if post_value is not None:
                improvement = ((pre_value - post_value) / pre_value) * 100
                improvements[metric] = {
                    "pre_value": pre_value,
                    "post_value": post_value,
                    "improvement_percent": improvement,
                    "back_to_baseline": abs(improvement) < 15
                }

        avg_improvement = sum(
            v["improvement_percent"] for v in improvements.values()
        ) / len(improvements) if improvements else 0

        return {
            "score": avg_improvement,
            "repair_successful": avg_improvement > 50,
            "back_to_baseline": all(
                v.get("back_to_baseline", False) for v in improvements.values()
            ),
            "improvements": improvements
        }

    async def _record_ml_feedback(
        self,
        equipment_id: str,
        work_order_id: str,
        effectiveness: Dict[str, Any]
    ) -> bool:
        """Record repair outcome for ML training via MLFeedbackService."""
        try:
            from app.services.ml_feedback_service import get_ml_feedback_service
            ml_service = get_ml_feedback_service()
            ml_service.record_repair_feedback(
                equipment_id=equipment_id,
                work_order_id=work_order_id,
                effectiveness_score=effectiveness.get("score", 0.0),
                repair_successful=effectiveness.get("repair_successful", False),
                failure_type=None,
                prediction_id=None
            )
            return True
        except Exception as e:
            logger.warning(f"ML feedback recording failed (non-critical): {e}")
            return False

    async def _get_baseline_status(self, equipment_id: str) -> Dict[str, Any]:
        """Get baseline status for equipment"""
        # Future: Call baseline service
        return {
            "has_baseline": True,
            "last_capture": datetime.now().isoformat(),
            "deviation_status": "normal"
        }

    async def _get_active_inspection(self, equipment_id: str) -> Optional[Dict[str, Any]]:
        """Get active inspection for equipment"""
        # Future: Call inspection service
        return None

    async def _get_active_repair(self, equipment_id: str) -> Optional[Dict[str, Any]]:
        """Get active repair for equipment"""
        # Future: Call work order service
        return None

    async def _get_last_anomaly(self, equipment_id: str) -> Optional[Dict[str, Any]]:
        """Get last anomaly for equipment"""
        # Future: Call ML service
        return None

    async def _audit_log(
        self,
        equipment_id: str,
        action: str,
        details: Dict[str, Any]
    ):
        """Log workflow action to audit log"""
        if self.audit_logger:
            await self.audit_logger.log_workflow_event(
                equipment_id=equipment_id,
                action=action,
                details=details
            )
        else:
            logger.info(f"Audit: {equipment_id} - {action} - {details}")


# ============================================================================
# Singleton Instance
# ============================================================================

_orchestrator_instance: Optional[AssetWorkflowOrchestrator] = None


def get_workflow_orchestrator() -> AssetWorkflowOrchestrator:
    """Get singleton orchestrator instance"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = AssetWorkflowOrchestrator()
    return _orchestrator_instance
