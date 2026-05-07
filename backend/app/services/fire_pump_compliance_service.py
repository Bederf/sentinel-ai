"""
Fire Pump Compliance Service

Service for managing FNBFW:32335 fire pump weekly run test compliance.
Provides scheduling, result recording, overdue detection, and reporting.
"""

import logging
from datetime import date, timedelta

from app.database.repositories.fire_pump_compliance_repository import (
    FirePumpComplianceRepository,
)
from app.models.fire_pump_compliance import (
    ComplianceReport,
    FirePumpInspection,
    InspectionResult,
    OverdueAlert,
)

logger = logging.getLogger(__name__)

# Weeks per year for recurring schedule generation
WEEKS_PER_YEAR = 52


class FirePumpComplianceService:
    """Service for fire pump compliance management (FNBFW:32335)."""

    def __init__(self, repository: FirePumpComplianceRepository | None = None):
        self.repository = repository or FirePumpComplianceRepository()

    # ========================================================================
    # Schedule Weekly Test
    # ========================================================================

    async def schedule_weekly_test(
        self,
        site_code: str,
        equipment_id: str,
    ) -> list[FirePumpInspection]:
        """
        Create 52 weekly recurring inspection records (one year ahead).

        Args:
            site_code: Site identifier (e.g., 'S002')
            equipment_id: Fire pump equipment ID

        Returns:
            List of created inspection records
        """
        scheduled: list[FirePumpInspection] = []
        today = date.today()

        try:
            for week in range(WEEKS_PER_YEAR):
                scheduled_date = today + timedelta(weeks=week)
                inspection = await self.repository.schedule_inspection(
                    site_code=site_code,
                    equipment_id=equipment_id,
                    scheduled_date=scheduled_date,
                )
                scheduled.append(inspection)

            logger.info(f"Scheduled {len(scheduled)} weekly fire pump inspections for {site_code}/{equipment_id}")
        except Exception as e:
            logger.error(f"Failed to schedule weekly tests: {e}")
            # Return empty list on failure (non-blocking)
            return []

        return scheduled

    # ========================================================================
    # Record Test Result
    # ========================================================================

    async def record_test_result(
        self,
        site_code: str,
        equipment_id: str,
        result: InspectionResult,
        certified_by: str | None = None,
        notes: str | None = None,
    ) -> FirePumpInspection | None:
        """
        Record a fire pump test result.

        Updates the most recent uncompleted inspection for the equipment.

        Args:
            site_code: Site identifier
            equipment_id: Fire pump equipment ID
            result: Inspection result (PASS, FAIL, INCONCLUSIVE)
            certified_by: Inspector/technician name
            notes: Inspection notes

        Returns:
            Updated inspection record or None if not found
        """
        # Find the most recent uncompleted inspection for this equipment
        try:
            from app.database.repositories.fire_pump_compliance_repository import (
                FirePumpComplianceRepository,
            )

            repo = FirePumpComplianceRepository()
            all_inspections = await repo.get_upcoming_inspections(site_code, days=365)
            # Find first uncompleted inspection for this equipment
            target = None
            for insp in all_inspections:
                if insp.equipment_id == equipment_id and insp.completed_date is None:
                    target = insp
                    break

            if target is None:
                # Fallback: search overdue
                overdue = await repo.get_overdue_inspections(site_code)
                for insp in overdue:
                    if insp.equipment_id == equipment_id:
                        target = insp
                        break

            if target is None:
                logger.warning(f"No open inspection found for {site_code}/{equipment_id}")
                return None

            updated = await repo.record_inspection_result(
                inspection_id=target.id,
                result=result,
                certified_by=certified_by,
                notes=notes,
            )

            if updated:
                logger.info(f"Recorded fire pump test result for {site_code}/{equipment_id}: {result.value}")

            return updated

        except Exception as e:
            logger.error(f"Failed to record test result: {e}")
            return None

    # ========================================================================
    # Get Overdue Alerts
    # ========================================================================

    async def get_overdue_alerts(self, site_code: str) -> list[OverdueAlert]:
        """
        Return all overdue fire pump tests with days_overdue and FNBFW:32335 reference.

        Args:
            site_code: Site identifier

        Returns:
            List of OverdueAlert objects
        """
        today = date.today()
        alerts: list[OverdueAlert] = []

        try:
            overdue = await self.repository.get_overdue_inspections(site_code)

            for insp in overdue:
                if insp.equipment_id is None:
                    continue

                days_overdue = (today - insp.scheduled_date).days

                # Determine last test date (completed_date if available, else scheduled_date)
                last_test = insp.completed_date or insp.scheduled_date

                alert = OverdueAlert(
                    equipment_id=insp.equipment_id,
                    site_code=site_code,
                    last_test_date=last_test,
                    scheduled_date=insp.scheduled_date,
                    days_overdue=days_overdue,
                    regulatory_reference="FNBFW:32335",
                )
                alerts.append(alert)

                # Log at WARNING level per Phase 207-05 spec
                logger.warning(
                    f"Fire pump compliance alert | equipment_id={insp.equipment_id} "
                    f"site_code={site_code} last_test_date={last_test} "
                    f"days_overdue={days_overdue} regulatory_reference=FNBFW:32335"
                )

        except Exception as e:
            logger.warning(f"get_overdue_alerts failed for {site_code}: {e}")
            # Non-blocking: return empty list
            return []

        return alerts

    # ========================================================================
    # Generate Compliance Report
    # ========================================================================

    async def generate_compliance_report(
        self,
        site_code: str,
        start_date: date,
        end_date: date,
    ) -> ComplianceReport:
        """
        Generate compliance report for a date range.

        Args:
            site_code: Site identifier
            start_date: Report start date
            end_date: Report end date

        Returns:
            ComplianceReport with compliance rate, test counts, FNBFW:32335 reference
        """
        try:
            inspections = await self.repository.get_inspections_in_range(site_code, start_date, end_date)

            total = len(inspections)
            passed = sum(1 for i in inspections if i.result == InspectionResult.PASS)
            failed = sum(1 for i in inspections if i.result == InspectionResult.FAIL)
            inconclusive = sum(1 for i in inspections if i.result == InspectionResult.INCONCLUSIVE)
            overdue = await self.repository.get_overdue_inspections(site_code)
            overdue_count = sum(1 for i in overdue if i.scheduled_date < date.today())

            compliance_rate = (passed / total * 100) if total > 0 else 0.0

            report = ComplianceReport(
                site_code=site_code,
                start_date=start_date,
                end_date=end_date,
                total_tests=total,
                passed=passed,
                failed=failed,
                inconclusive=inconclusive,
                overdue_count=overdue_count,
                compliance_rate=compliance_rate,
                regulatory_reference="FNBFW:32335",
            )

            logger.info(
                f"Generated compliance report for {site_code}: "
                f"compliance_rate={compliance_rate:.1f}% "
                f"({passed}/{total} passed, {overdue_count} overdue)"
            )

            return report

        except Exception as e:
            logger.error(f"Failed to generate compliance report: {e}")
            # Return empty report on failure (non-blocking)
            return ComplianceReport(
                site_code=site_code,
                start_date=start_date,
                end_date=end_date,
                total_tests=0,
                passed=0,
                failed=0,
                inconclusive=0,
                overdue_count=0,
                compliance_rate=0.0,
                regulatory_reference="FNBFW:32335",
            )


# =============================================================================
# Singleton
# =============================================================================

_fire_pump_compliance_service: FirePumpComplianceService | None = None


def get_fire_pump_compliance_service() -> FirePumpComplianceService:
    """Get or create singleton FirePumpComplianceService instance."""
    global _fire_pump_compliance_service
    if _fire_pump_compliance_service is None:
        _fire_pump_compliance_service = FirePumpComplianceService()
    return _fire_pump_compliance_service
