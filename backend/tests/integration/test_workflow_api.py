"""
Integration Tests for Workflow API Endpoints

Tests the complete workflow API including trigger chains.

Phase 53-02: Automated Triggers & Workflow Automation
"""

import pytest


class TestWorkflowAPI:
    """Integration tests for workflow API endpoints."""

    @pytest.fixture
    def client(self, test_client):
        """Create test client."""
        return test_client

    # ========================================================================
    # Trigger Endpoint Tests
    # ========================================================================

    def test_trigger_ml_anomaly(self, client):
        """Test ML anomaly trigger endpoint."""
        response = client.post(
            "/api/workflow/triggers/ml-anomaly",
            json={
                "equipment_id": "api-chiller-001",
                "anomaly_type": "vibration",
                "description": "High vibration detected during monitoring",
                "probability": 0.85,
                "timeframe": "24h",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trigger_type"] == "ml_anomaly"
        assert data["equipment_id"] == "api-chiller-001"

    def test_trigger_baseline_deviation(self, client):
        """Test baseline deviation trigger endpoint."""
        response = client.post(
            "/api/workflow/triggers/baseline-deviation",
            json={
                "equipment_id": "api-pump-001",
                "baseline_id": "bl-001",
                "max_deviation_percent": 18.5,
                "deviating_metrics": {"vibration": 18.5, "current": 15.0},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trigger_type"] == "baseline_deviation"
        assert "recommendation" in data["details"]

    def test_trigger_critical_deficiency(self, client):
        """Test critical deficiency trigger endpoint."""
        response = client.post(
            "/api/workflow/triggers/critical-deficiency",
            json={
                "inspection_id": "insp-api-001",
                "equipment_id": "api-ahu-001",
                "severity": "critical",
                "deficiency_title": "Bearing failure imminent",
                "deficiency_description": "Vibration analysis shows bearing wear",
                "recommended_action": "Replace bearings within 48 hours",
                "estimated_repair_cost_min": 5000.0,
                "estimated_repair_cost_max": 8000.0,
                "estimated_repair_hours": 4.0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trigger_type"] == "critical_deficiency"
        assert "work_order_id" in data["details"]

    def test_trigger_repair_completed(self, client):
        """Test repair completed trigger endpoint."""
        response = client.post(
            "/api/workflow/triggers/repair-completed",
            json={
                "work_order_id": "WO-API-001",
                "equipment_id": "api-fcu-001",
                "completion_notes": "Bearings replaced successfully",
                "parts_used": ["Bearing SKF 6205", "Seal kit"],
                "actual_hours": 3.5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trigger_type"] == "repair_completed"
        assert "inspection_task_id" in data["details"]
        assert "baseline_task_id" in data["details"]

    def test_trigger_validate_effectiveness(self, client):
        """Test effectiveness validation trigger endpoint."""
        response = client.post(
            "/api/workflow/triggers/validate-effectiveness",
            json={
                "equipment_id": "api-vav-001",
                "work_order_id": "WO-API-002",
                "pre_baseline": {"baseline_values": {"vibration_rms": 3.5, "motor_current": 152.0}},
                "post_baseline": {"baseline_values": {"vibration_rms": 1.2, "motor_current": 145.0}},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trigger_type"] == "repair_validation"
        assert "effectiveness_score" in data["details"]
        assert "repair_successful" in data["details"]

    # ========================================================================
    # Query Endpoint Tests
    # ========================================================================

    def test_get_trigger_history(self, client):
        """Test trigger history endpoint."""
        # First create a trigger
        client.post(
            "/api/workflow/triggers/ml-anomaly",
            json={
                "equipment_id": "history-eq-001",
                "anomaly_type": "temperature",
                "description": "High temperature",
                "probability": 0.75,
            },
        )

        # Then query history
        response = client.get("/api/workflow/triggers/history")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "triggers" in data

    def test_get_trigger_history_filtered(self, client):
        """Test trigger history with equipment filter."""
        equipment_id = "filter-eq-001"

        # Create trigger for specific equipment
        client.post(
            "/api/workflow/triggers/ml-anomaly",
            json={"equipment_id": equipment_id, "anomaly_type": "vibration", "description": "Test", "probability": 0.8},
        )

        response = client.get(f"/api/workflow/triggers/history?equipment_id={equipment_id}")
        assert response.status_code == 200
        data = response.json()
        assert all(t["equipment_id"] == equipment_id for t in data["triggers"])

    def test_get_pending_inspections(self, client):
        """Test pending inspections endpoint."""
        equipment_id = "insp-query-eq"

        # Create inspection via trigger
        client.post(
            "/api/workflow/triggers/ml-anomaly",
            json={"equipment_id": equipment_id, "anomaly_type": "vibration", "description": "Test", "probability": 0.9},
        )

        response = client.get(f"/api/workflow/triggers/inspections/{equipment_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["equipment_id"] == equipment_id
        assert "inspections" in data

    def test_get_pending_work_orders(self, client):
        """Test pending work orders endpoint."""
        equipment_id = "wo-query-eq"

        # Create work order via critical deficiency
        client.post(
            "/api/workflow/triggers/critical-deficiency",
            json={
                "inspection_id": "insp-wo",
                "equipment_id": equipment_id,
                "severity": "critical",
                "deficiency_title": "Test deficiency",
                "deficiency_description": "Test description",
                "recommended_action": "Test action",
            },
        )

        response = client.get(f"/api/workflow/triggers/work-orders/{equipment_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["equipment_id"] == equipment_id
        assert "work_orders" in data

    def test_get_effectiveness_result(self, client):
        """Test effectiveness result endpoint."""
        work_order_id = "WO-EFF-API"

        # Create effectiveness result
        client.post(
            "/api/workflow/triggers/validate-effectiveness",
            json={
                "equipment_id": "eff-query-eq",
                "work_order_id": work_order_id,
                "pre_baseline": {"baseline_values": {"vibration": 3.0}},
                "post_baseline": {"baseline_values": {"vibration": 1.0}},
            },
        )

        response = client.get(f"/api/workflow/triggers/effectiveness/{work_order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["work_order_id"] == work_order_id

    def test_effectiveness_result_not_found(self, client):
        """Test 404 for non-existent effectiveness result."""
        response = client.get("/api/workflow/triggers/effectiveness/WO-NONEXISTENT")
        assert response.status_code == 404

    # ========================================================================
    # Test Endpoint Tests
    # ========================================================================

    def test_test_trigger_ml_anomaly(self, client):
        """Test the test endpoint for ML anomaly."""
        response = client.post(
            "/api/workflow/test/trigger-ml-anomaly",
            params={"equipment_id": "test-chiller", "anomaly_type": "temperature"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["equipment_id"] == "test-chiller"

    def test_full_workflow_test_endpoint(self, client):
        """Test the full workflow test endpoint."""
        response = client.post("/api/workflow/test/full-workflow", params={"equipment_id": "full-workflow-test-eq"})

        assert response.status_code == 200
        data = response.json()
        assert data["equipment_id"] == "full-workflow-test-eq"
        assert data["workflow_steps"] == 4
        assert len(data["results"]) == 4

        # Verify all steps completed
        steps = [r["step"] for r in data["results"]]
        assert "ml_anomaly" in steps
        assert "critical_deficiency" in steps
        assert "repair_completed" in steps
        assert "effectiveness_validation" in steps

    # ========================================================================
    # Orchestrator Endpoint Tests
    # ========================================================================

    def test_get_workflow_status(self, client):
        """Test workflow status endpoint."""
        response = client.get("/api/workflow/status/status-test-eq")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["equipment_id"] == "status-test-eq"
        assert "current_state" in data
        assert "baseline_status" in data


class TestWorkflowScenarios:
    """End-to-end workflow scenario tests."""

    @pytest.fixture
    def client(self, test_client):
        """Create test client."""
        return test_client

    def test_scenario_happy_path(self, client):
        """Test happy path: Anomaly → Inspection → Deficiency → Repair → Validation (Success)."""
        equipment_id = "scenario-happy-eq"

        # Step 1: Anomaly detected
        r1 = client.post(
            "/api/workflow/triggers/ml-anomaly",
            json={
                "equipment_id": equipment_id,
                "anomaly_type": "vibration",
                "description": "Elevated vibration levels",
                "probability": 0.75,
            },
        )
        assert r1.status_code == 200

        # Step 2: Inspection finds critical deficiency
        r2 = client.post(
            "/api/workflow/triggers/critical-deficiency",
            json={
                "inspection_id": "scenario-insp",
                "equipment_id": equipment_id,
                "severity": "critical",
                "deficiency_title": "Bearing wear",
                "deficiency_description": "Bearings showing excessive wear",
                "recommended_action": "Replace bearings",
            },
        )
        assert r2.status_code == 200
        work_order_id = r2.json()["details"]["work_order_id"]

        # Step 3: Repair completed
        r3 = client.post(
            "/api/workflow/triggers/repair-completed",
            json={
                "work_order_id": work_order_id,
                "equipment_id": equipment_id,
                "completion_notes": "Bearings replaced",
            },
        )
        assert r3.status_code == 200

        # Step 4: Effectiveness validation (successful)
        r4 = client.post(
            "/api/workflow/triggers/validate-effectiveness",
            json={
                "equipment_id": equipment_id,
                "work_order_id": work_order_id,
                "pre_baseline": {"baseline_values": {"vibration": 4.0, "current": 155.0}},
                "post_baseline": {"baseline_values": {"vibration": 1.0, "current": 142.0}},
            },
        )
        assert r4.status_code == 200
        assert r4.json()["details"]["repair_successful"] is True

    def test_scenario_failed_repair_retrigger(self, client):
        """Test failed repair scenario: Validation fails → Follow-up created."""
        equipment_id = "scenario-fail-eq"
        work_order_id = "WO-SCENARIO-FAIL"

        # Repair completed
        client.post(
            "/api/workflow/triggers/repair-completed",
            json={"work_order_id": work_order_id, "equipment_id": equipment_id, "completion_notes": "Attempted repair"},
        )

        # Validation fails (minimal improvement)
        r = client.post(
            "/api/workflow/triggers/validate-effectiveness",
            json={
                "equipment_id": equipment_id,
                "work_order_id": work_order_id,
                "pre_baseline": {"baseline_values": {"vibration": 4.0}},
                "post_baseline": {"baseline_values": {"vibration": 3.8}},  # Only 5% improvement
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["details"]["repair_successful"] is False
        assert data["details"]["follow_up_created"] is True

        # Verify follow-up inspection was created
        inspections = client.get(f"/api/workflow/triggers/inspections/{equipment_id}")
        assert inspections.status_code == 200
        inspection_data = inspections.json()
        follow_ups = [i for i in inspection_data["inspections"] if "Failed Repair" in i["task_name"]]
        assert len(follow_ups) >= 1

    def test_scenario_baseline_deviation_critical(self, client):
        """Test critical baseline deviation creates both recommendation and inspection."""
        equipment_id = "scenario-baseline-eq"

        r = client.post(
            "/api/workflow/triggers/baseline-deviation",
            json={
                "equipment_id": equipment_id,
                "baseline_id": "bl-scenario",
                "max_deviation_percent": 25.0,  # Critical threshold
                "deviating_metrics": {"vibration": 25.0, "temperature": 22.0},
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["details"]["inspection_created"] is True
        assert "recommendation" in data["details"]

        # Verify inspection was created
        inspections = client.get(f"/api/workflow/triggers/inspections/{equipment_id}")
        assert inspections.json()["count"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
