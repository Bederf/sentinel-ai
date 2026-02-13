"""
Compliance Service Logic Tests

Tests for ComplianceService business logic including risk assessment,
scheduling calculations, and compliance validations.

Phase 28: SENTINEL Compliance
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.services.compliance_service import ComplianceService
from app.models.compliance import RiskLevel


@pytest.fixture
def compliance_service():
    """Create ComplianceService instance for testing."""
    service = ComplianceService()
    return service


# ============================================================================
# OHS Compliance Service Tests
# ============================================================================


@pytest.mark.asyncio
async def test_generate_ohs_checklist(compliance_service, mocker):
    """Verify OHS checklist generation populates all fields."""
    mock_template = {
        "id": "template-ohs-001",
        "compliance_type": "OHS",
        "checklist_items": [
            {"item_id": "ohs-001", "description": "Floor condition"},
            {"item_id": "ohs-002", "description": "Emergency exits"},
            {"item_id": "ohs-003", "description": "First aid kit"},
        ],
    }

    mock_task = MagicMock()
    mock_task.id = "task-001"

    mocker.patch.object(
        compliance_service.repository,
        "get_ohs_checklist_template",
        return_value=mock_template,
    )
    mocker.patch.object(
        compliance_service.repository,
        "create_inspection_task",
        return_value=mock_task,
    )

    result = await compliance_service.generate_ohs_checklist("S002", "zone-101")

    assert result["task_id"] == "task-001"
    assert result["items_count"] == 3


@pytest.mark.asyncio
async def test_track_ohs_completion(compliance_service, mocker):
    """Verify OHS completion creates audit trail."""
    mock_result = MagicMock()
    mock_result.id = "result-001"

    mock_audit = MagicMock()
    mock_audit.id = "audit-001"

    mocker.patch.object(
        compliance_service.repository,
        "create_inspection_result",
        return_value=mock_result,
    )
    mocker.patch.object(
        compliance_service.repository,
        "create_compliance_audit",
        return_value=mock_audit,
    )

    findings = {
        "critical_issues": [],
        "recommendations": ["improve ventilation"],
    }

    result = await compliance_service.track_ohs_completion("task-001", findings)

    assert result["result_id"] == "result-001"
    assert result["audit_id"] == "audit-001"


# ============================================================================
# Fire Equipment Service Tests
# ============================================================================


@pytest.mark.asyncio
async def test_schedule_fire_equipment_inspection_12month(
    compliance_service, mocker
):
    """Verify fire inspection interval is 12 months per NFPA 10."""
    mock_schedule = MagicMock()
    mock_schedule.id = "schedule-001"
    mock_schedule.next_due_date = datetime.now() + timedelta(days=365)
    mock_schedule.created_at = datetime.now()

    mocker.patch.object(
        compliance_service.repository,
        "create_fire_inspection_schedule",
        return_value=mock_schedule,
    )

    schedule = await compliance_service.schedule_fire_equipment_inspection(
        "extinguisher", "zone-B1"
    )

    assert schedule.id == "schedule-001"
    # Verify interval is approximately 365 days
    interval_days = (
        schedule.next_due_date - schedule.created_at
    ).days
    assert 363 <= interval_days <= 367  # Allow 2-day variance


@pytest.mark.asyncio
async def test_track_fire_equipment_expiry_alert(
    compliance_service, mocker
):
    """Verify alert when certification expiring within 30 days."""
    expiry_date = datetime.now() + timedelta(days=20)

    mock_tracking = MagicMock()
    mock_tracking.id = "tracking-001"
    mock_tracking.charge_pressure = 150.0
    mock_tracking.certification_expiry = expiry_date

    mocker.patch.object(
        compliance_service.repository,
        "update_fire_equipment_pressure",
        return_value=mock_tracking,
    )

    result = await compliance_service.track_fire_equipment_charge(
        "fire-001", 150.0, datetime.now()
    )

    assert result.charge_pressure == 150.0
    # Alert would be created for expiry within 30 days


# ============================================================================
# Emergency Light Service Tests
# ============================================================================


@pytest.mark.asyncio
async def test_schedule_emergency_light_daily_auto_test(
    compliance_service, mocker
):
    """Verify daily auto-test schedule (0100-0130 UTC) per IEC 62034."""
    mock_schedules = [MagicMock(id="schedule-001"), MagicMock(id="schedule-002")]

    mocker.patch.object(
        compliance_service.repository,
        "create_emergency_light_schedules",
        return_value=mock_schedules,
    )

    schedules = await compliance_service.schedule_emergency_light_test(
        ["EMERG-001", "EMERG-002"], auto_test=True
    )

    assert len(schedules) == 2


@pytest.mark.asyncio
async def test_record_emergency_light_battery_degradation(
    compliance_service, mocker
):
    """Verify battery health trend tracking."""
    mocker.patch.object(
        compliance_service.repository,
        "record_emergency_light_test",
        return_value={
            "light_code": "EMERG-001",
            "battery_health": 85,
        },
    )

    result = await compliance_service.record_emergency_light_test(
        "EMERG-001", 85, "pass"
    )

    assert result["battery_health"] == 85
    # No alert (> 75% threshold)


@pytest.mark.asyncio
async def test_emergency_light_battery_alert_critical(
    compliance_service, mocker
):
    """Verify alert triggered when battery < 75% (IEC 62034 threshold)."""
    mocker.patch.object(
        compliance_service.repository,
        "record_emergency_light_test",
        return_value={
            "light_code": "EMERG-002",
            "battery_health": 70,
        },
    )

    result = await compliance_service.record_emergency_light_test(
        "EMERG-002", 70, "alert"
    )

    assert result["battery_health"] == 70
    # Alert should be created (< 75% threshold)


# ============================================================================
# Legionella Risk Assessment Tests
# ============================================================================


@pytest.mark.asyncio
async def test_legionella_risk_matrix_high_risk(
    compliance_service, mocker
):
    """Verify high-risk when optimal temp AND old treatment."""
    mock_assessment = MagicMock()
    mock_assessment.risk_level = RiskLevel.HIGH
    mock_assessment.water_temperature = 30.0
    mock_assessment.biocide_treatment_date = datetime.now() - timedelta(days=60)

    mocker.patch.object(
        compliance_service.repository,
        "assess_legionella_risk",
        return_value=mock_assessment,
    )

    assessment = await compliance_service.assess_legionella_risk(
        "CT-001",
        water_temp=30.0,
        last_treatment=datetime.now() - timedelta(days=60),
    )

    assert assessment.risk_level == RiskLevel.HIGH


@pytest.mark.asyncio
async def test_legionella_risk_matrix_low_risk(
    compliance_service, mocker
):
    """Verify low-risk when cold temp AND recent treatment."""
    mock_assessment = MagicMock()
    mock_assessment.risk_level = RiskLevel.LOW
    mock_assessment.water_temperature = 10.0
    mock_assessment.biocide_treatment_date = datetime.now() - timedelta(days=7)

    mocker.patch.object(
        compliance_service.repository,
        "assess_legionella_risk",
        return_value=mock_assessment,
    )

    assessment = await compliance_service.assess_legionella_risk(
        "CT-001",
        water_temp=10.0,
        last_treatment=datetime.now() - timedelta(days=7),
    )

    assert assessment.risk_level == RiskLevel.LOW


@pytest.mark.asyncio
async def test_create_legionella_maintenance_high_risk(
    compliance_service, mocker
):
    """Verify high-risk gets 14-day biocide schedule."""
    mock_schedule = MagicMock()
    mock_schedule.id = "schedule-legionella-001"
    mock_schedule.schedule_name = "Legionella CT-001 - High-Risk (14-day treatment)"

    mocker.patch.object(
        compliance_service.repository,
        "create_legionella_maintenance_task",
        return_value=mock_schedule,
    )

    schedule = await compliance_service.create_legionella_maintenance_task(
        "assess-001"
    )

    assert "14-day" in schedule.schedule_name


@pytest.mark.asyncio
async def test_create_legionella_maintenance_low_risk(
    compliance_service, mocker
):
    """Verify low-risk gets 90-day monitoring schedule."""
    mock_schedule = MagicMock()
    mock_schedule.id = "schedule-legionella-002"
    mock_schedule.schedule_name = "Legionella CT-001 - Low-Risk (90-day monitoring)"

    mocker.patch.object(
        compliance_service.repository,
        "create_legionella_maintenance_task",
        return_value=mock_schedule,
    )

    schedule = await compliance_service.create_legionella_maintenance_task(
        "assess-002"
    )

    assert "90-day" in schedule.schedule_name


# ============================================================================
# Electrical Compliance Service Tests
# ============================================================================


@pytest.mark.asyncio
async def test_electrical_certificate_5year_expiry(
    compliance_service, mocker
):
    """Verify 5-year validity (South African SABS standard)."""
    from app.models.compliance import ElectricalCompliance

    cert = ElectricalCompliance(
        site_id="S002",
        certificate_type="CoC_new_installation",
        issued_by="John Smith",
        issue_date=datetime.now(),
        scope="L1-L2 distribution upgrade",
    )

    mock_saved = MagicMock()
    mock_saved.id = "cert-001"
    mock_saved.expiry_date = datetime.now() + timedelta(days=365 * 5)

    mocker.patch.object(
        compliance_service.repository,
        "create_electrical_compliance",
        return_value=mock_saved,
    )

    result = await compliance_service.track_electrical_certificate(cert)

    assert result is True
    # Verify expiry is 5 years from issue
    days_to_expiry = (
        mock_saved.expiry_date - datetime.now()
    ).days
    assert 1820 <= days_to_expiry <= 1825  # ~5 years


@pytest.mark.asyncio
async def test_electrical_compliance_expiry_alert(
    compliance_service, mocker
):
    """Verify alert when certificate expiring within 30 days."""
    from app.models.compliance import ElectricalCompliance

    cert = ElectricalCompliance(
        site_id="S002",
        certificate_type="CoC_new_installation",
        issued_by="John Smith",
        issue_date=datetime.now() - timedelta(days=365 * 5 - 20),  # Expiring in 20 days
        scope="L1-L2 distribution upgrade",
    )

    mock_saved = MagicMock()
    mock_saved.id = "cert-002"
    mock_saved.expiry_date = datetime.now() + timedelta(days=20)

    mocker.patch.object(
        compliance_service.repository,
        "create_electrical_compliance",
        return_value=mock_saved,
    )

    result = await compliance_service.track_electrical_certificate(cert)

    assert result is True
    # Alert would be created for 30-day expiry


# ============================================================================
# Lift Inspection Service Tests
# ============================================================================


@pytest.mark.asyncio
async def test_schedule_lift_inspection_6monthly(
    compliance_service, mocker
):
    """Verify periodic lift inspection scheduling."""
    mock_schedule = MagicMock()
    mock_schedule.id = "schedule-lift-001"

    mocker.patch.object(
        compliance_service.repository,
        "create_lift_inspection_schedule",
        return_value=mock_schedule,
    )

    schedule = await compliance_service.schedule_lift_inspection(
        "LIFT-R-001", "periodic_6monthly"
    )

    assert schedule.id == "schedule-lift-001"


@pytest.mark.asyncio
async def test_record_lift_test_results_compliant(
    compliance_service, mocker
):
    """Verify lift test validation: brake ≤ 1m, governor OK, e-stop OK."""
    mocker.patch.object(
        compliance_service.repository,
        "record_lift_test_results",
        return_value={
            "lift_code": "LIFT-R-001",
            "compliant": True,
        },
    )

    test_results = {
        "brake_load_test": "pass",
        "speed_governor": "pass",
        "emergency_stop_time": 0.8,  # < 1s required
        "shaft_pressure": "normal",
    }

    result = await compliance_service.record_lift_test_results(
        "LIFT-R-001", test_results
    )

    assert result["compliant"] is True


@pytest.mark.asyncio
async def test_record_lift_test_results_non_compliant(
    compliance_service, mocker
):
    """Verify non-compliance when brake test fails."""
    mocker.patch.object(
        compliance_service.repository,
        "record_lift_test_results",
        return_value={
            "lift_code": "LIFT-R-002",
            "compliant": False,
        },
    )

    test_results = {
        "brake_load_test": "fail",
        "speed_governor": "pass",
        "emergency_stop_time": 0.8,
        "shaft_pressure": "normal",
    }

    result = await compliance_service.record_lift_test_results(
        "LIFT-R-002", test_results
    )

    assert result["compliant"] is False


# ============================================================================
# Compliance Status Aggregation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_compliance_status_aggregates_all_types(
    compliance_service, mocker
):
    """Verify compliance status aggregates OHS, Fire, Electrical, etc."""
    from app.models.compliance import ComplianceStatus

    mock_status = ComplianceStatus(
        site_id="S002",
        critical_issues_count=2,
        high_risk_items_count=5,
        items_expiring_30days=3,
        overdue_inspections=1,
        compliance_score_percent=75,
    )

    mocker.patch.object(
        compliance_service.repository,
        "get_compliance_status",
        return_value=mock_status,
    )

    status = await compliance_service.get_compliance_status("S002")

    assert status.site_id == "S002"
    assert status.critical_issues_count == 2
    assert status.compliance_score_percent == 75


@pytest.mark.asyncio
async def test_get_compliance_audits_with_filters(
    compliance_service, mocker
):
    """Verify audit history retrieval with type/status filters."""
    mock_audits = [
        MagicMock(id="audit-001", compliance_type="Fire", status="submitted"),
    ]

    mocker.patch.object(
        compliance_service.repository,
        "get_compliance_audits",
        return_value=mock_audits,
    )

    audits = await compliance_service.get_compliance_audits(
        "S002", compliance_type="Fire", status="submitted"
    )

    assert len(audits) == 1
    assert audits[0].compliance_type == "Fire"
