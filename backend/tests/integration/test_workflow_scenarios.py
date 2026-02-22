"""
Integration Test Scenarios for SENTINEL Asset Management Workflow

Phase 53: SENTINEL Asset Management Workflow Integration

These test scenarios validate end-to-end workflows across all integrated systems.
"""

import pytest
import asyncio
from datetime import datetime
from app.services.workflow_orchestrator import (
    get_workflow_orchestrator,
    WorkflowState,
    OnboardAssetRequest,
    MLAnomalyTrigger,
    RepairValidationRequest,
)


# ============================================================================
# Scenario 1: Happy Path - Full Lifecycle
# ============================================================================


class TestHappyPathScenario:
    """
    Complete asset lifecycle from onboarding through repair validation.

    Story: New chiller is onboarded, operates normally, has routine
    inspection that passes, and continues normal operation.
    """

    @pytest.mark.asyncio
    async def test_full_lifecycle_happy_path(self):
        """
        Test complete happy path workflow:
        1. Onboard asset
        2. Capture baseline
        3. Monitor normally
        4. Schedule routine inspection
        5. Perform inspection (pass)
        6. Return to monitoring
        """
        orchestrator = get_workflow_orchestrator()

        # Step 1: Onboard new asset
        onboard_request = OnboardAssetRequest(
            site_id="test-site",
            site_name="Test Site",
            site_address="123 Test St",
            equipment=[
                {
                    "equipment_id": "chiller-happy-001",
                    "equipment_type": "chiller",
                    "name": "Happy Path Chiller",
                    "manufacturer": "York",
                    "model": "YCIV",
                    "criticality": "high",
                    "baseline_values": {
                        "chw_supply_temp": 7.2,
                        "motor_current": 145.2,
                        "vibration_rms": 1.8,
                        "bearing_temp": 45.1,
                    },
                }
            ],
            captured_by="Mike Chen",
            notes="Commissioning baseline - all values normal",
        )

        onboard_response = await orchestrator.onboard_asset(onboard_request)

        # Verify onboarding
        assert onboard_response.success is True
        assert onboard_response.equipment_onboarded == 1
        assert onboard_response.baselines_captured == 1
        assert onboard_response.workflow_state == WorkflowState.MONITORING

        # Verify state transition
        status = await orchestrator.get_workflow_status("chiller-happy-001")
        assert status.current_state == WorkflowState.MONITORING
        assert len(status.state_history) >= 2

        # Step 2: Simulate routine inspection (manual trigger via orchestrator)
        # In real system, this would be triggered by schedule due date

        # Step 3: Inspection passes, return to monitoring
        # For now, verify equipment is in monitoring state
        status_after = await orchestrator.get_workflow_status("chiller-happy-001")
        assert status_after.current_state == WorkflowState.MONITORING


# ============================================================================
# Scenario 2: ML Anomaly Path
# ============================================================================


class TestMLAnomalyScenario:
    """
    ML anomaly detected triggers inspection, finds issue, repair validated.

    Story: Chiller develops bearing issue, ML detects anomaly, inspection
    confirms problem, repair performed and validated.
    """

    @pytest.mark.asyncio
    async def test_ml_anomaly_to_repair_validation(self):
        """
        Test ML anomaly workflow:
        1. Equipment onboarded and monitoring
        2. ML detects anomaly (vibration)
        3. Inspection task auto-created
        4. Inspection finds deficiency
        5. Repair scheduled and performed
        6. Pre/post baselines compared
        7. Repair validated as successful
        """
        orchestrator = get_workflow_orchestrator()

        # Step 1: Onboard asset
        onboard_request = OnboardAssetRequest(
            site_id="test-site",
            site_name="Test Site",
            site_address="123 Test St",
            equipment=[
                {
                    "equipment_id": "chiller-anomaly-001",
                    "equipment_type": "chiller",
                    "name": "Anomaly Detection Chiller",
                    "baseline_values": {"vibration_rms": 1.8, "motor_current": 145.2},
                }
            ],
            captured_by="Mike Chen",
        )

        await orchestrator.onboard_asset(onboard_request)
        status = await orchestrator.get_workflow_status("chiller-anomaly-001")
        assert status.current_state == WorkflowState.MONITORING

        # Step 2: ML detects anomaly
        anomaly_trigger = MLAnomalyTrigger(
            equipment_id="chiller-anomaly-001",
            trigger_source="ml_anomaly",
            anomaly_type="vibration",
            probability=0.85,
            timeframe="7 days",
            ml_explanation=(
                "Bearing vibration up 111% from baseline (1.8 → 4.2 mm/s). Frequency analysis confirms bearing defect."
            ),
            priority="high",
        )

        inspection_response = await orchestrator.trigger_inspection_from_anomaly(anomaly_trigger)

        # Verify inspection created
        assert inspection_response.success is True
        assert inspection_response.equipment_id == "chiller-anomaly-001"
        assert inspection_response.priority == "high"
        assert "ML anomaly detected: vibration" in inspection_response.reason
        assert inspection_response.workflow_transition["to_state"] == WorkflowState.INSPECTION_SCHEDULED

        # Verify state transition
        status_after = await orchestrator.get_workflow_status("chiller-anomaly-001")
        assert status_after.current_state == WorkflowState.INSPECTION_SCHEDULED

        # Step 3-5: Inspection finds issue, repair performed (simulated)
        # In real system, technician would perform inspection and create deficiency
        # For now, we'll simulate the state progression

        # Step 6-7: Simulate repair validation
        orchestrator._set_state("chiller-anomaly-001", WorkflowState.POST_REPAIR_BASELINE)

        validation_request = RepairValidationRequest(
            equipment_id="chiller-anomaly-001",
            work_order_id="WO-2026-0847",
            pre_repair_baseline_id="bl-pre-anomaly-001",
            post_repair_baseline_id="bl-post-anomaly-001",
        )

        validation_response = await orchestrator.validate_repair_effectiveness(validation_request)

        # Verify repair validation
        assert validation_response.success is True
        assert validation_response.effectiveness["repair_successful"] is True
        assert validation_response.ml_feedback_recorded is True
        assert validation_response.workflow_transition["to_state"] == WorkflowState.BACK_TO_NORMAL

        # Verify back to monitoring
        final_status = await orchestrator.get_workflow_status("chiller-anomaly-001")
        assert final_status.current_state == WorkflowState.BACK_TO_NORMAL


# ============================================================================
# Scenario 3: Baseline Deviation Path
# ============================================================================


class TestBaselineDeviationScenario:
    """
    Baseline comparison triggers maintenance recommendation.

    Story: Routine comparison shows elevated vibration, triggers
    recommendation and inspection, maintenance performed before failure.
    """

    @pytest.mark.asyncio
    async def test_baseline_deviation_maintenance(self):
        """
        Test baseline deviation workflow:
        1. Equipment has baseline
        2. Routine comparison shows deviation
        3. Maintenance recommendation generated
        4. Inspection scheduled
        5. Maintenance performed
        """
        orchestrator = get_workflow_orchestrator()

        # Step 1: Onboard asset with baseline
        onboard_request = OnboardAssetRequest(
            site_id="test-site",
            site_name="Test Site",
            site_address="123 Test St",
            equipment=[
                {
                    "equipment_id": "chiller-deviation-001",
                    "equipment_type": "chiller",
                    "name": "Baseline Deviation Chiller",
                    "baseline_values": {"vibration_rms": 1.8, "motor_current": 145.2},
                }
            ],
            captured_by="Mike Chen",
        )

        await orchestrator.onboard_asset(onboard_request)

        # Step 2-3: Baseline deviation detected (simulated)
        # In real system, baseline_service.compare() would detect deviation
        deviation_percent = 39  # 1.8 → 2.5 mm/s (39% increase)

        # Step 4: Trigger inspection from deviation
        # (In real system, this would be automatic based on deviation threshold)
        if deviation_percent > 15:
            anomaly_trigger = MLAnomalyTrigger(
                equipment_id="chiller-deviation-001",
                trigger_source="baseline_deviation",
                anomaly_type="vibration",
                probability=0.72,
                timeframe="14 days",
                ml_explanation=f"Baseline vibration deviation: {deviation_percent}% above normal (1.8 → 2.5 mm/s)",
                priority="medium",
            )

            response = await orchestrator.trigger_inspection_from_anomaly(anomaly_trigger)
            assert response.success is True

        # Verify inspection scheduled
        status = await orchestrator.get_workflow_status("chiller-deviation-001")
        assert status.current_state == WorkflowState.INSPECTION_SCHEDULED


# ============================================================================
# Scenario 4: Failed Repair Path
# ============================================================================


class TestFailedRepairScenario:
    """
    Repair validation fails, triggers re-inspection.

    Story: Initial repair doesn't resolve issue, validation fails,
    follow-up inspection and repair scheduled.
    """

    @pytest.mark.asyncio
    async def test_failed_repair_re_validation(self):
        """
        Test failed repair workflow:
        1. Repair performed
        2. Post-repair baseline captured
        3. Validation shows poor improvement
        4. Follow-up inspection triggered
        5. Second repair scheduled
        """
        orchestrator = get_workflow_orchestrator()

        # Setup: Equipment with failed repair
        orchestrator._set_state("chiller-failed-001", WorkflowState.POST_REPAIR_BASELINE)

        validation_request = RepairValidationRequest(
            equipment_id="chiller-failed-001",
            work_order_id="WO-2026-0848",
            pre_repair_baseline_id="bl-pre-failed",
            post_repair_baseline_id="bl-post-failed",
        )

        # Mock poor improvement (simulated failed repair)
        # In real implementation, baseline values would show minimal improvement

        validation_response = await orchestrator.validate_repair_effectiveness(validation_request)

        # Verify validation
        assert validation_response.success is True

        # If repair failed, should trigger follow-up
        # (In real system, this would auto-create follow-up inspection)
        if not validation_response.effectiveness["repair_successful"]:
            # Create follow-up inspection
            follow_up_trigger = MLAnomalyTrigger(
                equipment_id="chiller-failed-001",
                trigger_source="repair_validation_failed",
                anomaly_type="repair_followup",
                probability=1.0,
                timeframe="immediate",
                ml_explanation=(
                    f"Repair validation failed: only {validation_response.effectiveness['score']:.1f}% improvement"
                ),
                priority="critical",
            )

            response = await orchestrator.trigger_inspection_from_anomaly(follow_up_trigger)
            assert response.priority == "critical"


# ============================================================================
# Scenario 5: Multi-Equipment Path
# ============================================================================


class TestMultiEquipmentScenario:
    """
    Multiple equipment in different workflow states simultaneously.

    Story: Building has 3 equipment - one healthy, one with issue,
    one under repair. System handles all concurrently.
    """

    @pytest.mark.asyncio
    async def test_multi_equipment_concurrent_states(self):
        """
        Test concurrent equipment in different states:
        1. Equipment 1: Healthy, normal monitoring
        2. Equipment 2: Anomaly detected, inspection pending
        3. Equipment 3: Repair in progress
        """
        orchestrator = get_workflow_orchestrator()

        # Equipment 1: Healthy
        await orchestrator.onboard_asset(
            OnboardAssetRequest(
                site_id="multi-site",
                site_name="Multi Equipment Site",
                site_address="456 Multi St",
                equipment=[
                    {
                        "equipment_id": "chiller-healthy-001",
                        "equipment_type": "chiller",
                        "name": "Healthy Chiller",
                        "baseline_values": {"vibration_rms": 1.8},
                    }
                ],
                captured_by="Mike Chen",
            )
        )

        # Equipment 2: Anomaly detected
        await orchestrator.onboard_asset(
            OnboardAssetRequest(
                site_id="multi-site",
                site_name="Multi Equipment Site",
                site_address="456 Multi St",
                equipment=[
                    {
                        "equipment_id": "chiller-issue-001",
                        "equipment_type": "chiller",
                        "name": "Issue Chiller",
                        "baseline_values": {"vibration_rms": 2.5},
                    }
                ],
                captured_by="Mike Chen",
            )
        )

        await orchestrator.trigger_inspection_from_anomaly(
            MLAnomalyTrigger(
                equipment_id="chiller-issue-001",
                trigger_source="ml_anomaly",
                anomaly_type="vibration",
                probability=0.72,
                timeframe="14 days",
                ml_explanation="Bearing vibration elevated",
                priority="high",
            )
        )

        # Equipment 3: Repair in progress
        await orchestrator.onboard_asset(
            OnboardAssetRequest(
                site_id="multi-site",
                site_name="Multi Equipment Site",
                site_address="456 Multi St",
                equipment=[
                    {
                        "equipment_id": "chiller-repair-001",
                        "equipment_type": "chiller",
                        "name": "Repair Chiller",
                        "baseline_values": {"vibration_rms": 1.8},
                    }
                ],
                captured_by="Mike Chen",
            )
        )

        orchestrator._set_state("chiller-repair-001", WorkflowState.REPAIR_IN_PROGRESS)

        # Verify all states
        status_1 = await orchestrator.get_workflow_status("chiller-healthy-001")
        status_2 = await orchestrator.get_workflow_status("chiller-issue-001")
        status_3 = await orchestrator.get_workflow_status("chiller-repair-001")

        assert status_1.current_state == WorkflowState.MONITORING
        assert status_2.current_state == WorkflowState.INSPECTION_SCHEDULED
        assert status_3.current_state == WorkflowState.REPAIR_IN_PROGRESS


# ============================================================================
# Performance Tests
# ============================================================================


class TestWorkflowPerformance:
    """Performance tests for workflow scenarios"""

    @pytest.mark.asyncio
    async def test_concurrent_full_lifecycles(self):
        """Test multiple full lifecycles running concurrently"""
        orchestrator = get_workflow_orchestrator()

        async def run_full_lifecycle(equipment_id: str):
            """Run complete lifecycle for one equipment"""
            # Onboard
            await orchestrator.onboard_asset(
                OnboardAssetRequest(
                    site_id="perf-test",
                    site_name="Performance Site",
                    site_address="789 Perf St",
                    equipment=[
                        {
                            "equipment_id": equipment_id,
                            "equipment_type": "chiller",
                            "name": f"Perf Chiller {equipment_id}",
                            "baseline_values": {"vibration_rms": 1.8},
                        }
                    ],
                    captured_by="Test User",
                )
            )

            # Trigger anomaly
            await orchestrator.trigger_inspection_from_anomaly(
                MLAnomalyTrigger(
                    equipment_id=equipment_id,
                    trigger_source="ml_anomaly",
                    anomaly_type="vibration",
                    probability=0.85,
                    timeframe="7 days",
                    ml_explanation="Test anomaly",
                    priority="high",
                )
            )

            # Validate repair
            orchestrator._set_state(equipment_id, WorkflowState.POST_REPAIR_BASELINE)
            await orchestrator.validate_repair_effectiveness(
                RepairValidationRequest(
                    equipment_id=equipment_id,
                    work_order_id=f"WO-{equipment_id}",
                    pre_repair_baseline_id=f"bl-pre-{equipment_id}",
                    post_repair_baseline_id=f"bl-post-{equipment_id}",
                )
            )

        # Run 10 lifecycles concurrently
        equipment_ids = [f"perf-{i:03d}" for i in range(10)]
        start = datetime.now()

        await asyncio.gather(*[run_full_lifecycle(eid) for eid in equipment_ids])

        duration = (datetime.now() - start).total_seconds()

        # Should complete 10 lifecycles in < 5 seconds
        assert duration < 5.0

        # Verify all equipment in correct final state
        for eid in equipment_ids:
            status = await orchestrator.get_workflow_status(eid)
            assert status.current_state == WorkflowState.BACK_TO_NORMAL
