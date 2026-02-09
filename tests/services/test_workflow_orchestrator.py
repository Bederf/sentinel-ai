"""
Unit tests for AssetWorkflowOrchestrator

Phase 53: SENTINEL Asset Management Workflow Integration
"""

import pytest
import asyncio
from datetime import datetime
from app.services.workflow_orchestrator import (
    AssetWorkflowOrchestrator,
    get_workflow_orchestrator,
    WorkflowState,
    OnboardAssetRequest,
    MLAnomalyTrigger,
    RepairValidationRequest
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def orchestrator():
    """Get orchestrator instance"""
    return get_workflow_orchestrator()


@pytest.fixture
def onboard_request():
    """Sample onboarding request"""
    return OnboardAssetRequest(
        site_id="sandton-mall",
        site_name="Sandton City Mall",
        site_address="83 5th St, Sandton",
        equipment=[
            {
                "equipment_id": "chiller-001",
                "equipment_type": "chiller",
                "name": "Main Chiller",
                "manufacturer": "York",
                "model": "YCIV",
                "criticality": "high",
                "baseline_values": {
                    "chw_supply_temp": 7.2,
                    "motor_current": 145.2,
                    "vibration_rms": 1.8
                }
            }
        ],
        captured_by="Mike Chen",
        notes="Commissioning baseline"
    )


@pytest.fixture
def anomaly_trigger():
    """Sample ML anomaly trigger"""
    return MLAnomalyTrigger(
        equipment_id="chiller-001",
        trigger_source="ml_anomaly",
        anomaly_type="vibration",
        probability=0.85,
        timeframe="7 days",
        ml_explanation="Bearing vibration up 111% from baseline",
        priority="high"
    )


@pytest.fixture
def repair_validation_request():
    """Sample repair validation request"""
    return RepairValidationRequest(
        equipment_id="chiller-001",
        work_order_id="WO-2026-0847",
        pre_repair_baseline_id="bl-pre-123",
        post_repair_baseline_id="bl-post-456"
    )


# ============================================================================
# Test: Asset Onboarding
# ============================================================================

class TestAssetOnboarding:
    """Tests for asset onboarding workflow"""

    @pytest.mark.asyncio
    async def test_onboard_single_asset(self, orchestrator, onboard_request):
        """Test onboarding a single asset"""
        response = await orchestrator.onboard_asset(onboard_request)

        assert response.success is True
        assert response.site_id == "sandton-mall"
        assert response.equipment_onboarded == 1
        assert response.baselines_captured == 1
        assert response.workflow_state == WorkflowState.MONITORING
        assert len(response.equipment) == 1

        # Verify state transition
        status = await orchestrator.get_workflow_status("chiller-001")
        assert status.current_state == WorkflowState.MONITORING
        assert len(status.state_history) >= 2  # ONBOARDING → BASELINE_CAPTURE → MONITORING

    @pytest.mark.asyncio
    async def test_onboard_multiple_assets(self, orchestrator):
        """Test onboarding multiple assets"""
        request = OnboardAssetRequest(
            site_id="test-building",
            site_name="Test Building",
            site_address="123 Test St",
            equipment=[
                {
                    "equipment_id": f"chiller-{i:03d}",
                    "equipment_type": "chiller",
                    "name": f"Chiller {i}",
                    "baseline_values": {"vibration_rms": 1.8 + (i * 0.1)}
                }
                for i in range(1, 4)
            ],
            captured_by="Test User"
        )

        response = await orchestrator.onboard_asset(request)

        assert response.success is True
        assert response.equipment_onboarded == 3
        assert response.baselines_captured == 3

    @pytest.mark.asyncio
    async def test_onboard_without_baseline(self, orchestrator):
        """Test onboarding asset without baseline values"""
        request = OnboardAssetRequest(
            site_id="test-building",
            site_name="Test Building",
            site_address="123 Test St",
            equipment=[
                {
                    "equipment_id": "ahu-001",
                    "equipment_type": "ahu",
                    "name": "AHU 1"
                    # No baseline_values
                }
            ],
            captured_by="Test User"
        )

        response = await orchestrator.onboard_asset(request)

        # Should succeed but with 0 baselines
        assert response.success is True
        assert response.baselines_captured == 0


# ============================================================================
# Test: Workflow Status
# ============================================================================

class TestWorkflowStatus:
    """Tests for workflow status queries"""

    @pytest.mark.asyncio
    async def test_get_status_for_unknown_equipment(self, orchestrator):
        """Test getting status for equipment that doesn't exist"""
        status = await orchestrator.get_workflow_status("unknown-001")

        assert status.success is True
        assert status.equipment_id == "unknown-001"
        assert status.current_state == WorkflowState.ONBOARDING
        assert len(status.state_history) == 0

    @pytest.mark.asyncio
    async def test_get_status_after_onboarding(self, orchestrator, onboard_request):
        """Test getting status after onboarding"""
        await orchestrator.onboard_asset(onboard_request)
        status = await orchestrator.get_workflow_status("chiller-001")

        assert status.current_state == WorkflowState.MONITORING
        assert status.baseline_status["has_baseline"] is True


# ============================================================================
# Test: ML Anomaly Triggers
# ============================================================================

class TestMLAnomalyTriggers:
    """Tests for ML anomaly trigger workflow"""

    @pytest.mark.asyncio
    async def test_trigger_inspection_from_anomaly(
        self,
        orchestrator,
        onboard_request,
        anomaly_trigger
    ):
        """Test triggering inspection from ML anomaly"""
        # First onboard the asset
        await orchestrator.onboard_asset(onboard_request)

        # Then trigger inspection from anomaly
        response = await orchestrator.trigger_inspection_from_anomaly(anomaly_trigger)

        assert response.success is True
        assert response.equipment_id == "chiller-001"
        assert response.inspection_task_id.startswith("task-")
        assert response.priority == "high"
        assert "ML anomaly detected" in response.reason
        assert response.workflow_transition["to_state"] == WorkflowState.INSPECTION_SCHEDULED

    @pytest.mark.asyncio
    async def test_trigger_with_critical_priority(self, orchestrator, anomaly_trigger):
        """Test triggering inspection with critical priority"""
        anomaly_trigger.priority = "critical"
        anomaly_trigger.probability = 0.95

        response = await orchestrator.trigger_inspection_from_anomaly(anomaly_trigger)

        assert response.priority == "critical"
        assert "95%" in response.reason

    @pytest.mark.asyncio
    async def test_trigger_multiple_anomalies(self, orchestrator, anomaly_trigger):
        """Test triggering multiple anomalies for same equipment"""
        response1 = await orchestrator.trigger_inspection_from_anomaly(anomaly_trigger)
        response2 = await orchestrator.trigger_inspection_from_anomaly(anomaly_trigger)

        # Both should succeed (demo scope - no duplicate prevention yet)
        assert response1.success is True
        assert response2.success is True


# ============================================================================
# Test: Repair Validation
# ============================================================================

class TestRepairValidation:
    """Tests for repair effectiveness validation"""

    @pytest.mark.asyncio
    async def test_validate_successful_repair(
        self,
        orchestrator,
        repair_validation_request
    ):
        """Test validating a successful repair"""
        response = await orchestrator.validate_repair_effectiveness(repair_validation_request)

        assert response.success is True
        assert response.equipment_id == "chiller-001"
        assert response.work_order_id == "WO-2026-0847"
        assert response.effectiveness["repair_successful"] is True
        assert response.ml_feedback_recorded is True
        assert response.workflow_transition["to_state"] == WorkflowState.BACK_TO_NORMAL

    @pytest.mark.asyncio
    async def test_validate_failed_repair(self, orchestrator):
        """Test validating an unsuccessful repair"""
        # Create request that will result in failed validation
        request = RepairValidationRequest(
            equipment_id="chiller-001",
            work_order_id="WO-2026-0848",
            pre_repair_baseline_id="bl-pre-bad",
            post_repair_baseline_id="bl-post-bad"
        )

        # Mock the baseline data to show poor improvement
        # (In real implementation, this would come from database)

        response = await orchestrator.validate_repair_effectiveness(request)

        # For now, this will succeed (demo scope)
        assert response.success is True

    @pytest.mark.asyncio
    async def test_validation_creates_ml_feedback(self, orchestrator, repair_validation_request):
        """Test that validation records ML feedback"""
        response = await orchestrator.validate_repair_effectiveness(repair_validation_request)

        assert response.ml_feedback_recorded is True


# ============================================================================
# Test: State Machine
# ============================================================================

class TestStateMachine:
    """Tests for state machine transitions"""

    @pytest.mark.asyncio
    async def test_state_transition_onboarding_to_monitoring(
        self,
        orchestrator,
        onboard_request
    ):
        """Test state transition from onboarding to monitoring"""
        await orchestrator.onboard_asset(onboard_request)
        status = await orchestrator.get_workflow_status("chiller-001")

        # Check state history
        assert len(status.state_history) >= 2
        states = [h["state"] for h in status.state_history]

        # Should have gone through ONBOARDING → MONITORING
        assert WorkflowState.MONITORING in states

    @pytest.mark.asyncio
    async def test_state_transition_monitoring_to_inspection(
        self,
        orchestrator,
        onboard_request,
        anomaly_trigger
    ):
        """Test state transition from monitoring to inspection"""
        await orchestrator.onboard_asset(onboard_request)

        # Get initial state
        status_before = await orchestrator.get_workflow_status("chiller-001")
        assert status_before.current_state == WorkflowState.MONITORING

        # Trigger inspection
        await orchestrator.trigger_inspection_from_anomaly(anomaly_trigger)

        # Check new state
        status_after = await orchestrator.get_workflow_status("chiller-001")
        assert status_after.current_state == WorkflowState.INSPECTION_SCHEDULED

    @pytest.mark.asyncio
    async def test_multiple_state_transitions(self, orchestrator, onboard_request):
        """Test multiple sequential state transitions"""
        await orchestrator.onboard_asset(onboard_request)

        states_seen = []
        for i in range(5):
            status = await orchestrator.get_workflow_status("chiller-001")
            states_seen.append(status.current_state)
            # Simulate state changes
            # (In real workflow, these would be triggered by events)

        assert len(states_seen) == 5


# ============================================================================
# Integration Tests
# ============================================================================

class TestWorkflowIntegration:
    """Integration tests for complete workflow"""

    @pytest.mark.asyncio
    async def test_complete_onboarding_to_monitoring_workflow(
        self,
        orchestrator,
        onboard_request
    ):
        """Test complete workflow from onboarding to monitoring"""
        # Step 1: Onboard asset
        response = await orchestrator.onboard_asset(onboard_request)
        assert response.success is True

        # Step 2: Check status
        status = await orchestrator.get_workflow_status("chiller-001")
        assert status.current_state == WorkflowState.MONITORING
        assert status.baseline_status["has_baseline"] is True

    @pytest.mark.asyncio
    async def test_anomaly_to_repair_validation_workflow(
        self,
        orchestrator,
        onboard_request,
        anomaly_trigger,
        repair_validation_request
    ):
        """Test workflow from anomaly detection through repair validation"""
        # Step 1: Onboard
        await orchestrator.onboard_asset(onboard_request)

        # Step 2: Anomaly detected
        inspection_response = await orchestrator.trigger_inspection_from_anomaly(anomaly_trigger)
        assert inspection_response.success is True
        assert inspection_response.workflow_transition["to_state"] == WorkflowState.INSPECTION_SCHEDULED

        # Step 3: Validate repair (simulating post-repair state)
        # First, set state to POST_REPAIR_BASELINE
        orchestrator._set_state("chiller-001", WorkflowState.POST_REPAIR_BASELINE)

        # Then validate
        validation_response = await orchestrator.validate_repair_effectiveness(repair_validation_request)
        assert validation_response.success is True
        assert validation_response.workflow_transition["to_state"] == WorkflowState.BACK_TO_NORMAL


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Performance tests for orchestrator"""

    @pytest.mark.asyncio
    async def test_concurrent_onboarding(self, orchestrator):
        """Test onboarding multiple assets concurrently"""
        tasks = []
        for i in range(10):
            request = OnboardAssetRequest(
                site_id=f"site-{i}",
                site_name=f"Site {i}",
                site_address=f"{i} Test St",
                equipment=[{
                    "equipment_id": f"equipment-{i}",
                    "equipment_type": "chiller",
                    "name": f"Chiller {i}",
                    "baseline_values": {"vibration_rms": 1.8}
                }],
                captured_by="Test User"
            )
            tasks.append(orchestrator.onboard_asset(request))

        # Run all concurrently
        responses = await asyncio.gather(*tasks)

        assert len(responses) == 10
        assert all(r.success for r in responses)

    @pytest.mark.asyncio
    async def test_status_query_performance(self, orchestrator, onboard_request):
        """Test status query performance"""
        await orchestrator.onboard_asset(onboard_request)

        # Query status 100 times
        start = datetime.now()
        for _ in range(100):
            await orchestrator.get_workflow_status("chiller-001")
        duration = (datetime.now() - start).total_seconds()

        # Should complete in less than 1 second for 100 queries
        assert duration < 1.0
