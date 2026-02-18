"""
Unit Tests for Workflow Trigger Engine

Tests all 5 automated triggers:
1. ML Anomaly → Inspection Task
2. Baseline Deviation → Maintenance Recommendation
3. Critical Deficiency → Work Order
4. Repair Completion → Post-Repair Inspection
5. Effectiveness Validation → ML Feedback

Phase 53-02: Automated Triggers & Workflow Automation
"""

import pytest

from app.services.workflow_triggers import (
    WorkflowTriggerEngine,
    get_trigger_engine,
    AnomalyAlert,
    BaselineComparison,
    InspectionDeficiency,
    TriggerType,
)


class TestWorkflowTriggerEngine:
    """Test suite for WorkflowTriggerEngine."""

    @pytest.fixture
    def trigger_engine(self):
        """Create a fresh trigger engine for each test."""
        return WorkflowTriggerEngine()

    # ========================================================================
    # Trigger 1: ML Anomaly Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_ml_anomaly_creates_inspection_task(self, trigger_engine):
        """Test that ML anomaly creates inspection task."""
        anomaly = AnomalyAlert(
            id="anomaly-001",
            equipment_id="chiller-001",
            anomaly_type="vibration",
            description="High vibration detected",
            probability=0.85
        )

        result = await trigger_engine.on_ml_anomaly("chiller-001", anomaly)

        assert result.success is True
        assert result.trigger_type == TriggerType.ML_ANOMALY
        assert result.action_taken == "created_inspection_task"
        assert result.follow_up_scheduled is True
        assert "task_id" in result.details

    @pytest.mark.asyncio
    async def test_ml_anomaly_skips_duplicate_inspection(self, trigger_engine):
        """Test that duplicate anomalies are suppressed."""
        anomaly1 = AnomalyAlert(
            id="anomaly-001",
            equipment_id="chiller-001",
            anomaly_type="vibration",
            description="High vibration",
            probability=0.85
        )
        anomaly2 = AnomalyAlert(
            id="anomaly-002",
            equipment_id="chiller-001",
            anomaly_type="temperature",
            description="High temperature",
            probability=0.9
        )

        # First anomaly creates inspection
        result1 = await trigger_engine.on_ml_anomaly("chiller-001", anomaly1)
        assert result1.action_taken == "created_inspection_task"

        # Second anomaly is suppressed by cooldown/dedupe
        result2 = await trigger_engine.on_ml_anomaly("chiller-001", anomaly2)
        assert result2.action_taken == "duplicate_suppressed"

    @pytest.mark.asyncio
    async def test_ml_anomaly_priority_calculation(self, trigger_engine):
        """Test priority is calculated based on probability."""
        test_cases = [
            (0.95, "critical"),
            (0.75, "high"),
            (0.55, "medium"),
            (0.30, "low"),
        ]

        for probability, expected_priority in test_cases:
            engine = WorkflowTriggerEngine()
            anomaly = AnomalyAlert(
                id=f"anomaly-{probability}",
                equipment_id=f"eq-{probability}",
                anomaly_type="vibration",
                description="Test",
                probability=probability
            )
            result = await engine.on_ml_anomaly(f"eq-{probability}", anomaly)
            assert result.details["priority"] == expected_priority

    # ========================================================================
    # Trigger 2: Baseline Deviation Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_baseline_deviation_below_threshold(self, trigger_engine):
        """Test that small deviations don't trigger action."""
        comparison = BaselineComparison(
            equipment_id="chiller-001",
            baseline_id="bl-001",
            max_deviation_percent=10.0,
            deviating_metrics={"vibration": 10.0}
        )

        result = await trigger_engine.on_baseline_deviation("chiller-001", comparison)

        assert result.success is True
        assert result.action_taken == "within_threshold"

    @pytest.mark.asyncio
    async def test_baseline_deviation_generates_recommendation(self, trigger_engine):
        """Test that moderate deviation generates recommendation."""
        comparison = BaselineComparison(
            equipment_id="chiller-001",
            baseline_id="bl-001",
            max_deviation_percent=17.0,
            deviating_metrics={"vibration": 17.0, "current": 15.5}
        )

        result = await trigger_engine.on_baseline_deviation("chiller-001", comparison)

        assert result.success is True
        assert result.action_taken == "generated_recommendation"
        assert "recommendation" in result.details
        assert result.details["inspection_created"] is False

    @pytest.mark.asyncio
    async def test_baseline_deviation_critical_creates_inspection(self, trigger_engine):
        """Test that critical deviation also creates inspection."""
        comparison = BaselineComparison(
            equipment_id="chiller-001",
            baseline_id="bl-001",
            max_deviation_percent=25.0,
            deviating_metrics={"vibration": 25.0}
        )

        result = await trigger_engine.on_baseline_deviation("chiller-001", comparison)

        assert result.success is True
        assert result.action_taken == "generated_recommendation"
        assert result.details["inspection_created"] is True
        assert result.follow_up_scheduled is True

    # ========================================================================
    # Trigger 3: Critical Deficiency Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_critical_deficiency_creates_work_order(self, trigger_engine):
        """Test that critical deficiency creates work order."""
        deficiency = InspectionDeficiency(
            id="def-001",
            inspection_id="insp-001",
            equipment_id="chiller-001",
            severity="critical",
            deficiency_title="Bearing failure imminent",
            deficiency_description="Bearing wear beyond tolerance",
            recommended_action="Replace bearings",
            estimated_repair_cost_min=5000.0,
            estimated_repair_cost_max=8000.0,
            estimated_repair_hours=4.0
        )

        result = await trigger_engine.on_critical_deficiency(deficiency)

        assert result.success is True
        assert result.trigger_type == TriggerType.CRITICAL_DEFICIENCY
        assert result.action_taken == "created_work_order"
        assert "work_order_id" in result.details
        assert "baseline_task_id" in result.details

    @pytest.mark.asyncio
    async def test_safety_deficiency_creates_work_order(self, trigger_engine):
        """Test that safety deficiency creates work order."""
        deficiency = InspectionDeficiency(
            id="def-002",
            inspection_id="insp-001",
            equipment_id="pump-001",
            severity="safety",
            deficiency_title="Leak detected near electrical",
            deficiency_description="Water leak near control panel",
            recommended_action="Isolate and repair immediately"
        )

        result = await trigger_engine.on_critical_deficiency(deficiency)

        assert result.success is True
        assert result.action_taken == "created_work_order"

    @pytest.mark.asyncio
    async def test_minor_deficiency_skipped(self, trigger_engine):
        """Test that minor deficiency doesn't create work order."""
        deficiency = InspectionDeficiency(
            id="def-003",
            inspection_id="insp-001",
            equipment_id="ahu-001",
            severity="minor",
            deficiency_title="Filter slightly dirty",
            deficiency_description="Filter at 60% capacity",
            recommended_action="Schedule replacement"
        )

        result = await trigger_engine.on_critical_deficiency(deficiency)

        assert result.success is True
        assert result.action_taken == "below_threshold"

    # ========================================================================
    # Trigger 4: Repair Completion Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_repair_completed_schedules_inspection(self, trigger_engine):
        """Test that repair completion schedules post-repair inspection."""
        result = await trigger_engine.on_repair_completed(
            work_order_id="WO-001",
            equipment_id="chiller-001",
            completion_data={"notes": "Bearings replaced"}
        )

        assert result.success is True
        assert result.trigger_type == TriggerType.REPAIR_COMPLETED
        assert result.action_taken == "scheduled_post_repair_inspection"
        assert "baseline_task_id" in result.details
        assert "inspection_task_id" in result.details
        assert "validation_scheduled" in result.details

    @pytest.mark.asyncio
    async def test_repair_completed_creates_baseline_task(self, trigger_engine):
        """Test that repair completion creates baseline capture task."""
        await trigger_engine.on_repair_completed(
            work_order_id="WO-002",
            equipment_id="pump-001",
            completion_data={}
        )

        tasks = trigger_engine.get_pending_baseline_tasks("pump-001")
        assert len(tasks) >= 1
        assert tasks[-1].baseline_type == "post_repair"

    # ========================================================================
    # Trigger 5: Effectiveness Validation Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_effectiveness_validation_successful(self, trigger_engine):
        """Test successful repair validation."""
        pre_baseline = {
            "baseline_values": {
                "vibration_rms": 3.5,
                "motor_current": 180.0
            }
        }
        post_baseline = {
            "baseline_values": {
                "vibration_rms": 1.2,  # 66% improvement
                "motor_current": 90.0  # 50% improvement
            }
        }
        # Average improvement: (66 + 50) / 2 = 58%, which is > 50%

        result = await trigger_engine.validate_repair_effectiveness(
            equipment_id="chiller-001",
            work_order_id="WO-001",
            pre_baseline=pre_baseline,
            post_baseline=post_baseline
        )

        assert result.success is True
        assert result.trigger_type == TriggerType.REPAIR_VALIDATION
        assert result.details["repair_successful"] is True
        assert result.details["effectiveness_score"] > 50.0

    @pytest.mark.asyncio
    async def test_effectiveness_validation_failed(self, trigger_engine):
        """Test failed repair validation creates follow-up."""
        pre_baseline = {
            "baseline_values": {
                "vibration_rms": 3.5,
                "motor_current": 152.0
            }
        }
        post_baseline = {
            "baseline_values": {
                "vibration_rms": 3.0,  # Only 14% improvement
                "motor_current": 150.0  # Only 1.3% improvement
            }
        }

        result = await trigger_engine.validate_repair_effectiveness(
            equipment_id="chiller-002",
            work_order_id="WO-002",
            pre_baseline=pre_baseline,
            post_baseline=post_baseline
        )

        assert result.success is True
        assert result.details["repair_successful"] is False
        assert result.details["follow_up_created"] is True
        assert result.follow_up_scheduled is True

    @pytest.mark.asyncio
    async def test_effectiveness_validation_ml_feedback(self, trigger_engine):
        """Test that effectiveness validation records ML feedback."""
        pre_baseline = {"baseline_values": {"vibration": 3.5}}
        post_baseline = {"baseline_values": {"vibration": 1.0}}

        result = await trigger_engine.validate_repair_effectiveness(
            equipment_id="pump-001",
            work_order_id="WO-003",
            pre_baseline=pre_baseline,
            post_baseline=post_baseline
        )

        assert result.details["ml_feedback_recorded"] is True

    @pytest.mark.asyncio
    async def test_effectiveness_validation_missing_baselines(self, trigger_engine):
        """Test error handling for missing baselines."""
        result = await trigger_engine.validate_repair_effectiveness(
            equipment_id="ahu-001",
            work_order_id="WO-004",
            pre_baseline={},
            post_baseline={}
        )

        assert result.success is False
        assert "missing_baselines" in result.action_taken

    # ========================================================================
    # Query Method Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_get_pending_inspections(self, trigger_engine):
        """Test retrieving pending inspections."""
        anomaly = AnomalyAlert(
            id="anomaly-test",
            equipment_id="test-eq-001",
            anomaly_type="vibration",
            description="Test",
            probability=0.8
        )
        await trigger_engine.on_ml_anomaly("test-eq-001", anomaly)

        inspections = trigger_engine.get_pending_inspections("test-eq-001")
        assert len(inspections) >= 1

    @pytest.mark.asyncio
    async def test_get_trigger_history(self, trigger_engine):
        """Test retrieving trigger history."""
        anomaly = AnomalyAlert(
            id="anomaly-hist",
            equipment_id="hist-eq-001",
            anomaly_type="vibration",
            description="Test",
            probability=0.8
        )
        await trigger_engine.on_ml_anomaly("hist-eq-001", anomaly)

        history = trigger_engine.get_trigger_history("hist-eq-001")
        assert len(history) >= 1
        assert history[0].equipment_id == "hist-eq-001"

    @pytest.mark.asyncio
    async def test_get_effectiveness_result(self, trigger_engine):
        """Test retrieving effectiveness result."""
        pre_baseline = {"baseline_values": {"vibration": 3.5}}
        post_baseline = {"baseline_values": {"vibration": 1.0}}

        await trigger_engine.validate_repair_effectiveness(
            equipment_id="eff-eq-001",
            work_order_id="WO-EFF-001",
            pre_baseline=pre_baseline,
            post_baseline=post_baseline
        )

        result = trigger_engine.get_effectiveness_result("WO-EFF-001")
        assert result is not None
        assert result.work_order_id == "WO-EFF-001"


class TestSingletonInstance:
    """Test singleton pattern for trigger engine."""

    def test_singleton_returns_same_instance(self):
        """Test that get_trigger_engine returns singleton."""
        engine1 = get_trigger_engine()
        engine2 = get_trigger_engine()
        assert engine1 is engine2


class TestTriggerChain:
    """Test complete trigger chains (integration scenarios)."""

    @pytest.mark.asyncio
    async def test_full_workflow_chain(self):
        """Test complete workflow: Anomaly → Deficiency → Repair → Validation."""
        engine = WorkflowTriggerEngine()

        # Step 1: ML Anomaly detected
        anomaly = AnomalyAlert(
            id="chain-anomaly",
            equipment_id="chain-chiller",
            anomaly_type="vibration",
            description="High vibration detected",
            probability=0.85
        )
        result1 = await engine.on_ml_anomaly("chain-chiller", anomaly)
        assert result1.success is True

        # Step 2: Critical deficiency found during inspection
        deficiency = InspectionDeficiency(
            id="chain-def",
            inspection_id="chain-insp",
            equipment_id="chain-chiller",
            severity="critical",
            deficiency_title="Bearing failure",
            deficiency_description="Bearing wear beyond tolerance",
            recommended_action="Replace bearings"
        )
        result2 = await engine.on_critical_deficiency(deficiency)
        assert result2.success is True
        work_order_id = result2.details["work_order_id"]

        # Step 3: Repair completed
        result3 = await engine.on_repair_completed(
            work_order_id=work_order_id,
            equipment_id="chain-chiller",
            completion_data={"notes": "Bearings replaced"}
        )
        assert result3.success is True

        # Step 4: Effectiveness validation
        result4 = await engine.validate_repair_effectiveness(
            equipment_id="chain-chiller",
            work_order_id=work_order_id,
            pre_baseline={"baseline_values": {"vibration": 3.5}},
            post_baseline={"baseline_values": {"vibration": 1.0}}
        )
        assert result4.success is True
        assert result4.details["repair_successful"] is True

        # Verify trigger history has all 4 triggers
        history = engine.get_trigger_history("chain-chiller")
        assert len(history) >= 4

    @pytest.mark.asyncio
    async def test_failed_repair_retrigger_chain(self):
        """Test that failed repair creates follow-up inspection."""
        engine = WorkflowTriggerEngine()

        # Repair that failed
        result = await engine.validate_repair_effectiveness(
            equipment_id="fail-chiller",
            work_order_id="WO-FAIL",
            pre_baseline={"baseline_values": {"vibration": 3.5}},
            post_baseline={"baseline_values": {"vibration": 3.2}}  # Only 8.5% improvement
        )

        assert result.details["repair_successful"] is False
        assert result.details["follow_up_created"] is True

        # Verify follow-up inspection was created
        inspections = engine.get_pending_inspections("fail-chiller")
        follow_ups = [i for i in inspections if "Failed Repair" in i.task_name]
        assert len(follow_ups) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
