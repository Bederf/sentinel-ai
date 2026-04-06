"""
Compliance Management Service

Provides comprehensive compliance automation for OHS Act, Fire Safety, Emergency Lighting,
Legionella Management, Electrical Certificates, and Lift Inspection.

Phase 28: SENTINEL Compliance
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.database.repositories.compliance_repository import ComplianceRepository
from app.models.compliance import (
    ComplianceAudit,
    ComplianceStatus,
    ElectricalCompliance,
    FireEquipmentTracking,
    LegionellaRiskAssessment,
    RiskLevel,
)
from app.models.inspection import InspectionSchedule

logger = logging.getLogger(__name__)


def _attr(obj, key, default=None):
    """Get attribute from dict or object (repo may return either)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class ComplianceService:
    """Service for managing all compliance requirements across the building."""

    def __init__(self, supabase=None, json_fallback=None):
        self.repository = ComplianceRepository(supabase, json_fallback)
        self.supabase = supabase
        self.json_fallback = json_fallback

    # ========================================================================
    # OHS Compliance Methods
    # ========================================================================

    async def generate_ohs_checklist(self, site_code: str, zone_id: str) -> dict[str, Any]:
        """
        Generate OHS checklist for a specific zone.

        Retrieves template, extracts zone-specific requirements, creates inspection task.

        Args:
            site_code: Building code (e.g., 'S002')
            zone_id: Zone UUID or identifier

        Returns:
            Dictionary with task_id and items_count
        """
        try:
            # Get OHS checklist template
            template = await self.repository.get_ohs_checklist_template(site_code)
            if not template:
                logger.warning(f"No OHS template found for site {site_code}")
                return {"task_id": None, "items_count": 0}

            # Create inspection task from template
            task = await self.repository.create_inspection_task(template, zone_id)
            task_id = _attr(task, "id")
            logger.info(f"Generated OHS checklist for zone {zone_id}: {task_id}")

            return {
                "task_id": str(task_id),
                "items_count": len(_attr(template, "checklist_items", [])),
            }

        except Exception as e:
            logger.error(f"Failed to generate OHS checklist: {e}")
            raise

    async def track_ohs_completion(self, task_id: str, findings: dict[str, Any]) -> dict[str, Any]:
        """
        Mark OHS checklist complete with findings.

        Creates inspection result and compliance audit record.

        Args:
            task_id: Inspection task UUID
            findings: Dictionary with {critical_issues, recommendations, cost_estimates}

        Returns:
            Dictionary with result_id and audit_id
        """
        try:
            # Create inspection result
            result = await self.repository.create_inspection_result(task_id, findings)

            # Create compliance audit
            audit = await self.repository.create_compliance_audit(
                audit_type="OHS",
                findings=findings,
                auditor_info={"role": "OHS Inspector"},
            )

            logger.info(f"Completed OHS checklist task {task_id}")
            return {"result_id": str(_attr(result, "id")), "audit_id": str(_attr(audit, "id"))}

        except Exception as e:
            logger.error(f"Failed to track OHS completion: {e}")
            raise

    # ========================================================================
    # Fire Equipment Methods
    # ========================================================================

    async def schedule_fire_equipment_inspection(self, equipment_type: str, location_zone: str) -> InspectionSchedule:
        """
        Schedule fire equipment inspection.

        Creates 12-month inspection schedule per NFPA 10 / SABS 4066.

        Args:
            equipment_type: 'extinguisher', 'hose_reel', 'hydrant', 'alarm', 'detector'
            location_zone: Zone identifier

        Returns:
            InspectionSchedule with next_due_date
        """
        try:
            schedule = await self.repository.create_fire_inspection_schedule(equipment_type, location_zone)
            logger.info(f"Scheduled {equipment_type} inspection at {location_zone}: {_attr(schedule, 'id')}")
            return schedule

        except Exception as e:
            logger.error(f"Failed to schedule fire equipment inspection: {e}")
            raise

    async def track_fire_equipment_charge(
        self,
        equipment_id: str,
        pressure: float,
        test_date: datetime,
        certified_by: str | None = None,
    ) -> FireEquipmentTracking:
        """
        Record fire equipment pressure test.

        Validates pressure within manufacturer specs and checks certification expiry.

        Args:
            equipment_id: Equipment UUID
            pressure: Pressure in PSI
            test_date: Date of test
            certified_by: Inspector name

        Returns:
            Updated FireEquipmentTracking record
        """
        try:
            tracking = await self.repository.update_fire_equipment_pressure(
                equipment_id, pressure, test_date, certified_by
            )

            # Check if certification expiring within 30 days
            if tracking.certification_expiry and (tracking.certification_expiry - datetime.now()) < timedelta(days=30):
                logger.warning(f"Fire equipment {equipment_id} certification expiring soon")
                # TODO: Create alert in alerts table

            return tracking

        except Exception as e:
            logger.error(f"Failed to track fire equipment charge: {e}")
            raise

    # ========================================================================
    # Emergency Light Testing (IEC 62034)
    # ========================================================================

    async def schedule_emergency_light_test(
        self, light_codes: list[str], auto_test: bool = True
    ) -> list[InspectionSchedule]:
        """
        Schedule emergency light testing.

        Creates daily auto-test schedule (0100-0130 UTC) per IEC 62034.

        Args:
            light_codes: List of light equipment codes
            auto_test: Enable automated testing

        Returns:
            List of InspectionSchedule UUIDs
        """
        try:
            schedules = await self.repository.create_emergency_light_schedules(light_codes, auto_test)
            logger.info(f"Scheduled {len(schedules)} emergency light tests")
            return schedules

        except Exception as e:
            logger.error(f"Failed to schedule emergency light tests: {e}")
            raise

    async def record_emergency_light_test(
        self,
        light_code: str,
        battery_health_percent: int,
        test_result: str,
    ) -> dict[str, Any]:
        """
        Record emergency light test result.

        Tracks battery health trend and creates alert if degradation detected.

        IEC 62034 requires 3-hour emergency runtime → alert if health < 75%.

        Args:
            light_code: Light equipment code
            battery_health_percent: Battery health 0-100%
            test_result: 'pass', 'fail', 'warning'

        Returns:
            Dictionary with light_code and battery_health
        """
        try:
            await self.repository.record_emergency_light_test(light_code, battery_health_percent, test_result)

            # Check if battery health degraded below threshold
            if battery_health_percent < 75:
                logger.warning(f"Emergency light {light_code} battery health critical: {battery_health_percent}%")
                # TODO: Create alert in alerts table

            return {"light_code": light_code, "battery_health": battery_health_percent}

        except Exception as e:
            logger.error(f"Failed to record emergency light test: {e}")
            raise

    # ========================================================================
    # Legionella Risk Management
    # ========================================================================

    async def assess_legionella_risk(
        self,
        tower_code: str,
        water_temp: float,
        last_treatment: datetime,
    ) -> LegionellaRiskAssessment:
        """
        Assess legionella risk for cooling tower.

        Risk matrix:
        - Water temp 20-45°C = high risk (Legionella optimal growth)
        - No biocide treatment in 30 days = high risk
        - Temperature control disabled = high risk

        Args:
            tower_code: Cooling tower code (e.g., 'S002-CT-B1-001')
            water_temp: Current water temperature in Celsius
            last_treatment: Date of last biocide treatment

        Returns:
            LegionellaRiskAssessment with risk_level
        """
        try:
            assessment = await self.repository.assess_legionella_risk(tower_code, water_temp, last_treatment)

            # Log high-risk conditions
            if _attr(assessment, "risk_level") == RiskLevel.HIGH:
                logger.warning(
                    f"Legionella HIGH RISK for {tower_code}: temp={water_temp}°C, "
                    f"treatment {(datetime.now() - last_treatment).days} days ago"
                )
                # TODO: Create alert and notify technician

            return assessment

        except Exception as e:
            logger.error(f"Failed to assess legionella risk: {e}")
            raise

    async def create_legionella_maintenance_task(self, risk_assessment_id: str) -> InspectionSchedule:
        """
        Create legionella maintenance task based on risk level.

        - High risk → 14-day biocide treatment schedule
        - Medium risk → 30-day water test schedule
        - Low risk → 90-day monitoring schedule

        Args:
            risk_assessment_id: LegionellaRiskAssessment UUID

        Returns:
            InspectionSchedule for maintenance task
        """
        try:
            schedule = await self.repository.create_legionella_maintenance_task(risk_assessment_id)
            logger.info(f"Created legionella maintenance task: {_attr(schedule, 'id')}")
            return schedule

        except Exception as e:
            logger.error(f"Failed to create legionella maintenance task: {e}")
            raise

    # ========================================================================
    # Electrical Compliance
    # ========================================================================

    async def track_electrical_certificate(self, certificate: ElectricalCompliance) -> bool:
        """
        Track electrical Certificate of Compliance.

        Validates CoC format, sets 5-year expiry alert, creates work order if expiring.

        Args:
            certificate: ElectricalCompliance model with issue_date and scope

        Returns:
            True if successfully tracked
        """
        try:
            # Validate SABS format (basic check)
            if not certificate.certificate_number:
                logger.warning("Certificate number required for tracking")
                return False

            # Save certificate
            saved = await self.repository.create_electrical_compliance(certificate)

            # Set 5-year expiry (South African standard)
            expiry_date = certificate.issue_date + timedelta(days=365 * 5)

            # Check if expiring within 30 days
            days_to_expiry = (expiry_date - datetime.now()).days
            if days_to_expiry <= 30 and days_to_expiry > 0:
                logger.warning(f"Electrical certificate {_attr(saved, 'id')} expiring in {days_to_expiry} days")
                # TODO: Create work order for re-certification

            logger.info(f"Tracked electrical certificate: {_attr(saved, 'id')}")
            return True

        except Exception as e:
            logger.error(f"Failed to track electrical certificate: {e}")
            raise

    async def check_electrical_compliance_status(self, site_code: str) -> ComplianceStatus:
        """
        Get electrical compliance status for site.

        Aggregates all electrical_compliance records and returns summary.

        Args:
            site_code: Building code

        Returns:
            ComplianceStatus with electrical summary
        """
        try:
            status = await self.repository.get_electrical_compliance_status(site_code)
            return status

        except Exception as e:
            logger.error(f"Failed to check electrical compliance status: {e}")
            raise

    # ========================================================================
    # Lift Inspection
    # ========================================================================

    async def schedule_lift_inspection(self, lift_code: str, inspection_type: str) -> InspectionSchedule:
        """
        Schedule lift inspection.

        Types:
        - periodic_6monthly: Standard safety inspection
        - annual_insurance: Insurer requirements
        - after_repair: Post-maintenance verification

        Args:
            lift_code: Lift equipment code
            inspection_type: Type of inspection

        Returns:
            InspectionSchedule
        """
        try:
            schedule = await self.repository.create_lift_inspection_schedule(lift_code, inspection_type)
            logger.info(f"Scheduled lift inspection for {lift_code}: {_attr(schedule, 'id')}")
            return schedule

        except Exception as e:
            logger.error(f"Failed to schedule lift inspection: {e}")
            raise

    async def record_lift_test_results(self, lift_code: str, test_results: dict[str, Any]) -> dict[str, Any]:
        """
        Record lift inspection test results.

        Validates:
        - Brake load test: stopping distance ≤ 1m
        - Speed governor: activation at 110% rated speed
        - Emergency stop: instantaneous stop

        Args:
            lift_code: Lift equipment code
            test_results: Dictionary with test measurements

        Returns:
            Dictionary with lift_code and compliant status
        """
        try:
            await self.repository.record_lift_test_results(lift_code, test_results)

            # Check compliance
            is_compliant = True
            if test_results.get("brake_load_test") != "pass":
                is_compliant = False
                logger.error(f"Lift {lift_code} brake test FAILED")
            if test_results.get("speed_governor") != "pass":
                is_compliant = False
                logger.error(f"Lift {lift_code} speed governor FAILED")
            if test_results.get("emergency_stop_time", 99) > 1.0:
                is_compliant = False
                logger.error(f"Lift {lift_code} emergency stop FAILED")

            if not is_compliant:
                # TODO: Create alert and work order

                pass

            return {"lift_code": lift_code, "compliant": is_compliant}

        except Exception as e:
            logger.error(f"Failed to record lift test results: {e}")
            raise

    # ========================================================================
    # Audit Trail & Evidence
    # ========================================================================

    async def create_compliance_audit(
        self,
        audit_type: str,
        findings: dict[str, Any],
        auditor_info: dict[str, Any],
    ) -> ComplianceAudit:
        """
        Create comprehensive compliance audit record.

        Stores audit result with JSONB findings, links evidence files.

        Status lifecycle: draft → submitted → approved → remediation_pending → closed

        Args:
            audit_type: 'scheduled', 'unannounced', 'certification'
            findings: {critical_issues, recommendations, cost_estimates}
            auditor_info: {id, role, name}

        Returns:
            ComplianceAudit record
        """
        try:
            audit = await self.repository.create_compliance_audit(audit_type, findings, auditor_info)
            logger.info(f"Created compliance audit: {_attr(audit, 'id')}")
            return audit

        except Exception as e:
            logger.error(f"Failed to create compliance audit: {e}")
            raise

    # ========================================================================
    # Status & Reporting
    # ========================================================================

    async def get_compliance_status(self, site_code: str) -> ComplianceStatus:
        """
        Get overall compliance status for site.

        Aggregates all compliance_audits, fire_equipment_tracking, electrical_compliance, etc.

        Returns summary KPIs:
        - % critical issues
        - Items expiring soon
        - Overdue inspections
        - Compliance score (0-100%)

        Args:
            site_code: Building code

        Returns:
            ComplianceStatus with KPIs
        """
        try:
            status = await self.repository.get_compliance_status(site_code)
            logger.info(f"Retrieved compliance status for {site_code}")
            return status

        except Exception as e:
            logger.error(f"Failed to get compliance status: {e}")
            raise

    async def get_compliance_audits(
        self,
        site_code: str,
        compliance_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ComplianceAudit]:
        """
        Get compliance audit history for site.

        Args:
            site_code: Building code
            compliance_type: Filter by OHS, Fire, Electrical, etc.
            status: Filter by draft, submitted, approved, etc.
            limit: Maximum number of audits to return

        Returns:
            List of ComplianceAudit records
        """
        try:
            audits = await self.repository.get_compliance_audits(site_code, compliance_type, status, limit)
            return audits

        except Exception as e:
            logger.error(f"Failed to get compliance audits: {e}")
            raise


# Singleton instance for global access
_compliance_service: ComplianceService | None = None


def get_compliance_service() -> ComplianceService:
    """Get or create singleton ComplianceService instance."""
    global _compliance_service
    if _compliance_service is None:
        _compliance_service = ComplianceService()
    return _compliance_service


async def ensure_compliance_service_initialized() -> ComplianceService:
    """Ensure ComplianceService is initialized with dependencies."""
    service = get_compliance_service()
    return service
