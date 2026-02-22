"""
Compliance Repository - Database operations for compliance management

Handles CRUD operations for:
- Compliance audits
- Fire equipment tracking
- Emergency light testing
- Legionella risk assessment
- Electrical compliance
- Lift inspection tracking

Phase 28: SENTINEL Compliance
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import uuid
import logging

from app.models.compliance import (
    ComplianceAudit,
    FireEquipmentTracking,
    LegionellaRiskAssessment,
    ElectricalCompliance,
    ComplianceStatus,
    RiskLevel,
)
from app.models.inspection import InspectionSchedule, InspectionTask, InspectionResult
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class ComplianceRepository:
    """Repository for compliance database operations."""

    def __init__(self, supabase=None, json_fallback=None):
        self.supabase = supabase or get_supabase_client()
        self.json_fallback = json_fallback
        self.use_json_fallback = False

    # ========================================================================
    # OHS Compliance Methods
    # ========================================================================

    async def get_ohs_checklist_template(self, site_code: str) -> Optional[Dict[str, Any]]:
        """Get OHS checklist template for site."""
        try:
            result = (
                self.supabase.table("compliance_checklist_templates")
                .select("*")
                .eq("compliance_type", "OHS")
                .eq("is_active", True)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to get OHS template: {e}")
            return None

    async def create_inspection_task(self, template: Dict[str, Any], zone_id: str) -> InspectionTask:
        """Create inspection task from template."""
        task_data = {
            "id": str(uuid.uuid4()),
            "task_name": f"OHS Inspection - {zone_id}",
            "description": template.get("description"),
            "zone_id": zone_id,
            "status": "scheduled",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("inspection_tasks").insert(task_data).execute()
        return InspectionTask(**result.data[0])

    async def create_inspection_result(self, task_id: str, findings: Dict[str, Any]) -> InspectionResult:
        """Create inspection result from findings."""
        result_data = {
            "id": str(uuid.uuid4()),
            "inspection_task_id": task_id,
            "overall_status": "pass" if not findings.get("critical_issues") else "fail",
            "findings": findings,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("inspection_results").insert(result_data).execute()
        return InspectionResult(**result.data[0])

    # ========================================================================
    # Fire Equipment Methods
    # ========================================================================

    async def get_fire_equipment(self, site_code: str, zone_id: Optional[str] = None) -> List[FireEquipmentTracking]:
        """Get fire equipment at site/zone."""
        try:
            query = self.supabase.table("fire_equipment_tracking").select("*").eq("site_id", site_code)

            if zone_id:
                query = query.eq("zone_id", zone_id)

            result = query.execute()
            return [FireEquipmentTracking(**row) for row in result.data]

        except Exception as e:
            logger.error(f"Failed to get fire equipment: {e}")
            return []

    async def create_fire_inspection_schedule(self, equipment_type: str, location_zone: str) -> InspectionSchedule:
        """Create 12-month fire equipment inspection schedule."""
        schedule_data = {
            "id": str(uuid.uuid4()),
            "schedule_name": f"Fire {equipment_type} Inspection - {location_zone}",
            "frequency_type": "annual",
            "frequency_days": 365,
            "is_active": True,
            "next_due_date": (datetime.now() + timedelta(days=365)).isoformat(),
            "created_by": "system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("inspection_schedules").insert(schedule_data).execute()
        return InspectionSchedule(**result.data[0])

    async def update_fire_equipment_pressure(
        self,
        equipment_id: str,
        pressure: float,
        test_date: datetime,
        certified_by: Optional[str] = None,
    ) -> FireEquipmentTracking:
        """Update fire equipment pressure test record."""
        update_data = {
            "charge_pressure": pressure,
            "pressure_test_date": test_date.isoformat(),
            "certified_by": certified_by or "system",
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("fire_equipment_tracking").update(update_data).eq("id", equipment_id).execute()

        if result.data:
            return FireEquipmentTracking(**result.data[0])
        raise ValueError(f"Equipment {equipment_id} not found")

    # ========================================================================
    # Emergency Light Testing Methods
    # ========================================================================

    async def create_emergency_light_schedules(
        self, light_codes: List[str], auto_test: bool = True
    ) -> List[InspectionSchedule]:
        """Create daily auto-test schedules for emergency lights."""
        schedules = []

        for light_code in light_codes:
            schedule_data = {
                "id": str(uuid.uuid4()),
                "schedule_name": f"Emergency Light Auto-Test - {light_code}",
                "frequency_type": "daily",
                "frequency_days": 1,
                "is_active": True,
                "next_due_date": (datetime.now().replace(hour=1, minute=0, second=0)).isoformat(),
                "created_by": "system",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            result = self.supabase.table("inspection_schedules").insert(schedule_data).execute()
            schedules.append(InspectionSchedule(**result.data[0]))

        return schedules

    async def record_emergency_light_test(
        self, light_code: str, battery_health_percent: int, test_result: str
    ) -> Dict[str, Any]:
        """Record emergency light test result."""
        test_record = {
            "date": datetime.now().isoformat(),
            "result": test_result,
            "battery_health": battery_health_percent,
        }

        # Get existing record
        result = self.supabase.table("emergency_light_testing").select("*").eq("light_code", light_code).execute()

        if result.data:
            existing = result.data[0]
            # Update battery trend and history
            trend = existing.get("battery_health_trend", [])
            trend.append({"date": datetime.now().isoformat(), "value": battery_health_percent})

            history = existing.get("test_results_history", [])
            history.append(test_record)

            update_data = {
                "battery_health_percent": battery_health_percent,
                "battery_health_trend": trend,
                "test_results_history": history,
                "last_test_date": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            update_result = (
                self.supabase.table("emergency_light_testing")
                .update(update_data)
                .eq("light_code", light_code)
                .execute()
            )
            return update_result.data[0] if update_result.data else {}
        else:
            # Create new record
            new_data = {
                "id": str(uuid.uuid4()),
                "light_code": light_code,
                "fixture_location": "unknown",
                "site_id": "unknown",
                "battery_health_percent": battery_health_percent,
                "battery_health_trend": [{"date": datetime.now().isoformat(), "value": battery_health_percent}],
                "test_results_history": [test_record],
                "last_test_date": datetime.now().isoformat(),
                "auto_test_enabled": True,
                "created_by": "system",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            insert_result = self.supabase.table("emergency_light_testing").insert(new_data).execute()
            return insert_result.data[0] if insert_result.data else {}

    # ========================================================================
    # Legionella Risk Assessment Methods
    # ========================================================================

    async def assess_legionella_risk(
        self, tower_code: str, water_temp: float, last_treatment: datetime
    ) -> LegionellaRiskAssessment:
        """Assess legionella risk level."""
        # Risk matrix logic
        days_since_treatment = (datetime.now() - last_treatment).days

        # High risk: optimal temp (20-45°C) + no treatment in 30 days
        if 20 <= water_temp <= 45 and days_since_treatment > 30:
            risk_level = RiskLevel.HIGH
        # Medium risk: moderate conditions
        elif 20 <= water_temp <= 45 or days_since_treatment > 30 or water_temp < 20:
            risk_level = RiskLevel.MEDIUM
        # Low risk: cold water or recent treatment
        else:
            risk_level = RiskLevel.LOW

        assessment_data = {
            "id": str(uuid.uuid4()),
            "tower_code": tower_code,
            "water_temperature": water_temp,
            "water_test_date": datetime.now().isoformat(),
            "biocide_treatment_date": last_treatment.isoformat(),
            "risk_level": risk_level.value,
            "status": "at_risk" if risk_level != RiskLevel.LOW else "compliant",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("legionella_risk_assessment").insert(assessment_data).execute()

        return LegionellaRiskAssessment(**result.data[0])

    async def create_legionella_maintenance_task(self, risk_assessment_id: str) -> InspectionSchedule:
        """Create legionella maintenance task based on risk."""
        # Get risk assessment
        result = self.supabase.table("legionella_risk_assessment").select("*").eq("id", risk_assessment_id).execute()

        if not result.data:
            raise ValueError(f"Risk assessment {risk_assessment_id} not found")

        assessment = result.data[0]
        risk_level = assessment.get("risk_level")

        # Determine schedule based on risk
        if risk_level == "high":
            frequency_days = 14
            name_suffix = "High-Risk (14-day treatment)"
        elif risk_level == "medium":
            frequency_days = 30
            name_suffix = "Medium-Risk (30-day test)"
        else:
            frequency_days = 90
            name_suffix = "Low-Risk (90-day monitoring)"

        schedule_data = {
            "id": str(uuid.uuid4()),
            "schedule_name": f"Legionella {assessment.get('tower_code')} - {name_suffix}",
            "frequency_type": "custom",
            "frequency_days": frequency_days,
            "is_active": True,
            "next_due_date": (datetime.now() + timedelta(days=frequency_days)).isoformat(),
            "created_by": "system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        schedule_result = self.supabase.table("inspection_schedules").insert(schedule_data).execute()

        return InspectionSchedule(**schedule_result.data[0])

    # ========================================================================
    # Electrical Compliance Methods
    # ========================================================================

    async def create_electrical_compliance(self, certificate: ElectricalCompliance) -> ElectricalCompliance:
        """Create electrical compliance record."""
        # Auto-calculate 5-year expiry (South African standard)
        expiry_date = certificate.issue_date + timedelta(days=365 * 5)

        cert_data = {
            "id": str(uuid.uuid4()),
            "site_id": certificate.site_id,
            "certificate_type": certificate.certificate_type.value,
            "certificate_number": certificate.certificate_number or str(uuid.uuid4()),
            "issued_by": certificate.issued_by,
            "issued_by_license": certificate.issued_by_license,
            "issue_date": certificate.issue_date.isoformat(),
            "expiry_date": expiry_date.isoformat(),
            "scope": certificate.scope,
            "equipment_codes": certificate.equipment_codes,
            "status": "active",
            "created_by": "system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("electrical_compliance").insert(cert_data).execute()

        return ElectricalCompliance(**result.data[0])

    async def get_electrical_compliance_status(self, site_code: str) -> ComplianceStatus:
        """Get electrical compliance status for site."""
        result = self.supabase.table("electrical_compliance").select("*").eq("site_id", site_code).execute()

        certs = result.data or []
        now = datetime.now()

        expiring_30 = 0
        expired = 0

        for cert in certs:
            expiry = datetime.fromisoformat(cert.get("expiry_date", ""))
            if expiry < now:
                expired += 1
            elif (expiry - now).days <= 30:
                expiring_30 += 1

        return ComplianceStatus(
            site_id=site_code,
            items_expiring_30days=expiring_30,
            compliance_score_percent=100 - (expired * 10),
            summary={"electrical_status": "compliant" if expired == 0 else "at_risk"},
        )

    # ========================================================================
    # Lift Inspection Methods
    # ========================================================================

    async def create_lift_inspection_schedule(self, lift_code: str, inspection_type: str) -> InspectionSchedule:
        """Create lift inspection schedule."""
        if inspection_type == "periodic_6monthly":
            frequency_days = 180
        elif inspection_type == "annual_insurance":
            frequency_days = 365
        else:
            frequency_days = 90

        schedule_data = {
            "id": str(uuid.uuid4()),
            "schedule_name": f"Lift {lift_code} - {inspection_type}",
            "frequency_type": "custom",
            "frequency_days": frequency_days,
            "is_active": True,
            "next_due_date": (datetime.now() + timedelta(days=frequency_days)).isoformat(),
            "created_by": "system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("inspection_schedules").insert(schedule_data).execute()

        return InspectionSchedule(**result.data[0])

    async def record_lift_test_results(self, lift_code: str, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Record lift inspection test results."""
        is_compliant = (
            test_results.get("brake_load_test") == "pass"
            and test_results.get("speed_governor") == "pass"
            and test_results.get("emergency_stop_time", 99) <= 1.0
        )

        result_data = {
            "id": str(uuid.uuid4()),
            "lift_code": lift_code,
            "test_results": test_results,
            "test_date": datetime.now().isoformat(),
            "is_compliant": is_compliant,
            "status": "completed",
            "created_by": "system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("lift_inspection_tracking").insert(result_data).execute()

        return result.data[0] if result.data else {"compliant": is_compliant}

    # ========================================================================
    # Compliance Audit Methods
    # ========================================================================

    async def create_compliance_audit(
        self,
        audit_type: str,
        findings: Dict[str, Any],
        auditor_info: Dict[str, Any],
    ) -> ComplianceAudit:
        """Create compliance audit record."""
        audit_data = {
            "id": str(uuid.uuid4()),
            "audit_type": audit_type,
            "findings": findings,
            "auditor_role": auditor_info.get("role"),
            "status": "draft",
            "audit_date": datetime.now().isoformat(),
            "created_by": "system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        result = self.supabase.table("compliance_audits").insert(audit_data).execute()

        return ComplianceAudit(**result.data[0])

    async def get_compliance_audits(
        self,
        site_code: str,
        compliance_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ComplianceAudit]:
        """Get compliance audit history."""
        query = self.supabase.table("compliance_audits").select("*").eq("site_id", site_code)

        if compliance_type:
            query = query.eq("compliance_type", compliance_type)

        if status:
            query = query.eq("status", status)

        result = query.order("created_at", desc=True).limit(limit).execute()

        return [ComplianceAudit(**row) for row in result.data]

    # ========================================================================
    # Overall Status
    # ========================================================================

    async def get_compliance_status(self, site_code: str) -> ComplianceStatus:
        """Get overall compliance status for site."""
        # Aggregate all compliance data
        audits = await self.get_compliance_audits(site_code, limit=100)

        critical_count = sum(
            1
            for audit in audits
            if audit.findings.get("critical_issues") and len(audit.findings.get("critical_issues", [])) > 0
        )

        return ComplianceStatus(
            site_id=site_code,
            critical_issues_count=critical_count,
            compliance_score_percent=max(0, 100 - (critical_count * 5)),
            last_audit_date=audits[0].created_at if audits else None,
            summary={
                "audits_count": len(audits),
                "critical_audits": critical_count,
            },
        )
