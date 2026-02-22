"""
SLA Compliance Calculation Service (Phase 50)

Calculates SLA compliance, detects breaches, and computes clawbacks for contract performance monitoring.
Supports multiple metric types with real-time breach detection and severity classification.

Key capabilities:
- Period performance calculation (monthly/quarterly/annual)
- Breach detection with severity levels (minor, major, critical)
- Clawback calculations (fixed, percentage, tiered penalties)
- Background compliance scanning job
- Work order integration for response/resolution time tracking
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
import logging

from app.models.contract import (
    SLABreachEvent,
    SLABreachSeverity,
    SLAComplianceStatus,
    SLAMetricType,
    SLAPerformanceWithCompliance,
    SLATerm,
    PenaltyType,
)

logger = logging.getLogger(__name__)


class SLAComplianceService:
    """
    Service for calculating SLA compliance, detecting breaches, and computing clawbacks.

    Singleton pattern - use get_sla_compliance_service() factory.
    """

    def __init__(self):
        """Initialize SLA compliance service with repository dependencies."""
        # Repositories will be initialized lazily
        self._work_order_repo = None
        self._sla_repo = None

    def get_work_order_repository(self):
        """Lazy initialization of work order repository."""
        if self._work_order_repo is None:
            from app.database.repositories import get_work_order_repository

            self._work_order_repo = get_work_order_repository()
        return self._work_order_repo

    def get_sla_repository(self):
        """Lazy initialization of SLA repository."""
        if self._sla_repo is None:
            from app.database.repositories import get_sla_repository

            self._sla_repo = get_sla_repository()
        return self._sla_repo

    def calculate_period_performance(
        self,
        contract_id: str,
        sla_term_id: str,
        period_start: date,
        period_end: date,
    ) -> SLAPerformanceWithCompliance:
        """
        Calculate SLA performance for a specific period.

        Args:
            contract_id: Contract identifier
            sla_term_id: SLA term identifier
            period_start: Period start date
            period_end: Period end date

        Returns:
            SLAPerformanceWithCompliance with compliance metrics and breach details
        """
        # Get SLA term definition
        sla_term = self._get_sla_term(sla_term_id)
        if not sla_term:
            raise ValueError(f"SLA term {sla_term_id} not found")

        # Determine metric type from SLA type
        metric_type = self._map_sla_type_to_metric(sla_term.sla_type)

        # Calculate actual performance based on metric type
        actual_value = self._calculate_actual_value(
            contract_id,
            sla_term,
            period_start,
            period_end,
        )

        # Calculate compliance percentage
        compliance_percentage = self._calculate_compliance_percentage(
            target_value=Decimal(str(sla_term.target_value)),
            actual_value=Decimal(str(actual_value)),
            metric_type=metric_type,
        )

        # Determine compliance status
        compliance_status = self._determine_compliance_status(compliance_percentage)

        # Detect breaches
        breaches = self._detect_breaches(
            contract_id=contract_id,
            sla_term_id=sla_term_id,
            metric_type=metric_type,
            target_value=Decimal(str(sla_term.target_value)),
            actual_value=Decimal(str(actual_value)),
            period_start=period_start,
            period_end=period_end,
        )

        # Calculate clawbacks
        clawback_amount = sum(b.clawback_amount_zar for b in breaches)

        # Create extended performance record
        performance = SLAPerformanceWithCompliance(
            id=f"perf-{contract_id}-{sla_term_id}-{period_start.isoformat()}",
            contract_id=contract_id,
            sla_term_id=sla_term_id,
            period_start=period_start,
            period_end=period_end,
            target_value=sla_term.target_value,
            actual_value=float(actual_value),
            met_target=compliance_status != SLAComplianceStatus.BREACH,
            incidents_count=len(breaches),
            metric_type=metric_type,
            compliance_percentage=float(compliance_percentage),
            compliance_status=compliance_status,
            breach_count=len(breaches),
            breach_details=[self._serialize_breach(b) for b in breaches],
            clawback_amount_zar=float(clawback_amount),
            status=self._map_compliance_to_performance_status(compliance_status),
            created_at=datetime.now(),
        )

        return performance

    def detect_breach(
        self,
        metric_type: SLAMetricType,
        target: Decimal,
        actual: Decimal,
    ) -> Optional[SLABreachEvent]:
        """
        Detect if SLA breach occurred for a single metric reading.

        Args:
            metric_type: Type of SLA metric
            target: Target value
            actual: Actual value

        Returns:
            SLABreachEvent if breach detected, None otherwise
        """
        # Determine if breach occurred based on metric type
        is_breach = self._is_breach(metric_type, target, actual)

        if not is_breach:
            return None

        # Calculate breach percentage
        breach_percentage = self._calculate_breach_percentage(metric_type, target, actual)

        # Determine severity
        severity = self._determine_severity(float(breach_percentage))

        return SLABreachEvent(
            contract_id="",  # To be filled by caller
            sla_term_id="",  # To be filled by caller
            metric_type=metric_type,
            breach_severity=severity,
            target_value=float(target),
            actual_value=float(actual),
            breach_percentage=float(breach_percentage),
            occurred_at=datetime.now(),
            detected_at=datetime.now(),
            clawback_amount_zar=0.0,  # Calculated separately
        )

    def calculate_clawback(
        self,
        breach: SLABreachEvent,
        penalty_type: PenaltyType,
        penalty_amount: Decimal,
        contract_value: Decimal,
    ) -> Decimal:
        """
        Calculate penalty amount based on breach and penalty type.

        Args:
            breach: Breach event
            penalty_type: Type of penalty (fixed, percentage, tiered)
            penalty_amount: Penalty amount or percentage
            contract_value: Monthly contract value for percentage calculations

        Returns:
            Penalty amount in ZAR
        """
        if penalty_type == PenaltyType.FIXED:
            return Decimal(str(penalty_amount))

        elif penalty_type == PenaltyType.PERCENTAGE:
            # Apply percentage to contract value
            return contract_value * (Decimal(str(penalty_amount)) / Decimal("100"))

        elif penalty_type == PenaltyType.TIERED:
            # Tiered penalties based on breach severity
            return self._calculate_tiered_penalty(breach, penalty_amount)

        else:
            logger.warning(f"Unknown penalty type: {penalty_type}")
            return Decimal("0")

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_sla_term(self, sla_term_id: str) -> Optional[SLATerm]:
        """Get SLA term from repository."""
        try:
            sla_repo = self.get_sla_repository()
            return sla_repo.get_sla_term(sla_term_id)
        except Exception as e:
            logger.error(f"Failed to get SLA term {sla_term_id}: {e}")
            return None

    def _map_sla_type_to_metric(self, sla_type: str) -> SLAMetricType:
        """Map SLA type string to SLAMetricType enum."""
        mapping = {
            "response_time": SLAMetricType.RESPONSE_TIME,
            "resolution_time": SLAMetricType.RESOLUTION_TIME,
            "uptime": SLAMetricType.UPTIME_PERCENTAGE,
            "ppm_completion": SLAMetricType.PREVENTIVE_MAINTENANCE,
            "first_fix_rate": SLAMetricType.MEAN_TIME_TO_REPAIR,  # Closest match
        }
        return mapping.get(sla_type, SLAMetricType.RESPONSE_TIME)

    def _calculate_actual_value(
        self,
        contract_id: str,
        sla_term: SLATerm,
        period_start: date,
        period_end: date,
    ) -> Decimal:
        """
        Calculate actual performance value for the period.

        For demo purposes, generates realistic values.
        In production, would query work order repository.
        """
        # Demo implementation - return realistic values
        if sla_term.sla_type == "uptime":
            # Uptime: 92-99%
            return Decimal("96.5")

        elif sla_term.sla_type == "response_time":
            # Response time: 2-8 hours
            return Decimal("4.5")

        elif sla_term.sla_type == "resolution_time":
            # Resolution time: 8-48 hours
            return Decimal("24.0")

        elif sla_term.sla_type == "ppm_completion":
            # PPM completion: 85-100%
            return Decimal("94.0")

        elif sla_term.sla_type == "first_fix_rate":
            # First fix rate: 70-95%
            return Decimal("82.0")

        else:
            logger.warning(f"Unknown SLA type: {sla_term.sla_type}")
            return Decimal("0")

    def _calculate_compliance_percentage(
        self,
        target_value: Decimal,
        actual_value: Decimal,
        metric_type: SLAMetricType,
    ) -> Decimal:
        """
        Calculate compliance percentage (actual/target * 100).

        Handles inverse metrics (where lower is better, e.g., response time).
        """
        if metric_type in [
            SLAMetricType.RESPONSE_TIME,
            SLAMetricType.RESOLUTION_TIME,
            SLAMetricType.MEAN_TIME_TO_REPAIR,
        ]:
            # For time-based metrics: lower is better
            # Compliance = target / actual * 100
            if actual_value == 0:
                return Decimal("100")
            return (target_value / actual_value) * Decimal("100")
        else:
            # For percentage-based metrics: higher is better
            # Compliance = actual / target * 100
            if target_value == 0:
                return Decimal("0")
            return (actual_value / target_value) * Decimal("100")

    def _determine_compliance_status(
        self,
        compliance_percentage: Decimal,
    ) -> SLAComplianceStatus:
        """Determine compliance status from percentage."""
        if compliance_percentage >= Decimal("90"):
            return SLAComplianceStatus.COMPLIANT
        elif compliance_percentage >= Decimal("80"):
            return SLAComplianceStatus.WARNING
        else:
            return SLAComplianceStatus.BREACH

    def _is_breach(
        self,
        metric_type: SLAMetricType,
        target: Decimal,
        actual: Decimal,
    ) -> bool:
        """Determine if actual value breaches target."""
        compliance_pct = self._calculate_compliance_percentage(target, actual, metric_type)
        return compliance_pct < Decimal("90")  # <90% is a breach

    def _calculate_breach_percentage(
        self,
        metric_type: SLAMetricType,
        target: Decimal,
        actual: Decimal,
    ) -> Decimal:
        """
        Calculate breach percentage.

        How much actual exceeded target (or fell below for percentage metrics).
        """
        compliance_pct = self._calculate_compliance_percentage(target, actual, metric_type)

        if compliance_pct >= Decimal("100"):
            return Decimal("0")

        # Breach % = (100 - compliance %)
        return Decimal("100") - compliance_pct

    def _determine_severity(self, breach_percentage: float) -> SLABreachSeverity:
        """
        Determine breach severity from breach percentage.

        - minor: <10% breach (not worth tracking)
        - major: 10-50% breach (action required)
        - critical: >50% breach or safety-critical failure
        """
        if breach_percentage < 10:
            return SLABreachSeverity.MINOR
        elif breach_percentage <= 50:
            return SLABreachSeverity.MAJOR
        else:
            return SLABreachSeverity.CRITICAL

    def _detect_breaches(
        self,
        contract_id: str,
        sla_term_id: str,
        metric_type: SLAMetricType,
        target_value: Decimal,
        actual_value: Decimal,
        period_start: date,
        period_end: date,
    ) -> List[SLABreachEvent]:
        """
        Detect all breaches for a period.

        For demo, returns 0-2 breaches based on compliance status.
        In production, would analyze individual incidents/work orders.
        """
        breaches = []

        # Check if overall performance breached
        if self._is_breach(metric_type, target_value, actual_value):
            breach_pct = self._calculate_breach_percentage(metric_type, target_value, actual_value)
            severity = self._determine_severity(float(breach_pct))

            # Create breach event for mid-period
            mid_period = period_start + (period_end - period_start) / 2

            breach = SLABreachEvent(
                id=f"breach-{contract_id}-{sla_term_id}-{mid_period.isoformat()}",
                contract_id=contract_id,
                sla_term_id=sla_term_id,
                work_order_id=f"WO-{contract_id}-{mid_period.strftime('%Y%m')}",
                metric_type=metric_type,
                breach_severity=severity,
                target_value=float(target_value),
                actual_value=float(actual_value),
                breach_percentage=float(breach_pct),
                occurred_at=datetime.combine(mid_period, datetime.min.time()),
                detected_at=datetime.now(),
                clawback_amount_zar=0.0,  # Calculated separately
            )
            breaches.append(breach)

        return breaches

    def _calculate_tiered_penalty(
        self,
        breach: SLABreachEvent,
        base_amount: Decimal,
    ) -> Decimal:
        """
        Calculate tiered penalty based on breach severity.

        - minor: 1x base amount
        - major: 2x base amount
        - critical: 5x base amount
        """
        multipliers = {
            SLABreachSeverity.MINOR: Decimal("1"),
            SLABreachSeverity.MAJOR: Decimal("2"),
            SLABreachSeverity.CRITICAL: Decimal("5"),
        }

        multiplier = multipliers.get(breach.breach_severity, Decimal("1"))
        return Decimal(str(base_amount)) * multiplier

    def _serialize_breach(self, breach: SLABreachEvent) -> Dict[str, Any]:
        """Convert breach event to dictionary for JSON storage."""
        return {
            "id": breach.id,
            "severity": breach.breach_severity.value,
            "metric_type": breach.metric_type.value,
            "target_value": breach.target_value,
            "actual_value": breach.actual_value,
            "breach_percentage": breach.breach_percentage,
            "occurred_at": breach.occurred_at.isoformat(),
            "detected_at": breach.detected_at.isoformat(),
            "clawback_amount_zar": breach.clawback_amount_zar,
            "work_order_id": breach.work_order_id,
        }

    def _map_compliance_to_performance_status(
        self,
        compliance_status: SLAComplianceStatus,
    ) -> str:
        """Map compliance status to SLAPerformanceStatus enum value."""

        mapping = {
            SLAComplianceStatus.COMPLIANT: "calculated",
            SLAComplianceStatus.WARNING: "calculated",
            SLAComplianceStatus.BREACH: "calculated",
        }
        return mapping.get(compliance_status, "pending")


# ============================================================================
# Singleton Factory
# ============================================================================

_sla_compliance_service_instance: Optional[SLAComplianceService] = None


def get_sla_compliance_service() -> SLAComplianceService:
    """Get singleton SLA compliance service instance."""
    global _sla_compliance_service_instance
    if _sla_compliance_service_instance is None:
        _sla_compliance_service_instance = SLAComplianceService()
    return _sla_compliance_service_instance


# ============================================================================
# Background Job
# ============================================================================


async def scan_sla_compliance():
    """
    Background job to scan all contracts for SLA breaches.

    Runs periodically (e.g., daily) to calculate compliance and detect breaches.
    Creates alerts for breaches that require attention.
    """
    service = get_sla_compliance_service()

    try:
        # Get all contracts with active SLA terms
        sla_repo = service.get_sla_repository()
        contracts = sla_repo.get_contracts_with_sla()

        current_month_start = date.today().replace(day=1)
        current_month_end = (
            current_month_start.replace(month=current_month_start.month % 12 + 1) - timedelta(days=1)
            if current_month_start.month < 12
            else current_month_start.replace(year=current_month_start.year + 1, month=1) - timedelta(days=1)
        )

        breach_count = 0

        for contract in contracts:
            for sla_term in contract.sla_terms:
                try:
                    performance = service.calculate_period_performance(
                        contract_id=contract.id,
                        sla_term_id=sla_term.id,
                        period_start=current_month_start,
                        period_end=current_month_end,
                    )

                    # Check for breach
                    if performance.compliance_status == SLAComplianceStatus.BREACH:
                        breach_count += 1
                        logger.warning(
                            f"SLA breach detected: Contract {contract.id}, "
                            f"SLA {sla_term.id}, "
                            f"Compliance: {performance.compliance_percentage:.1f}%"
                        )

                        # TODO: Create alert via alert notification service
                        # await create_sla_breach_alert(performance)

                except Exception as e:
                    logger.error(
                        f"Failed to calculate SLA performance for contract {contract.id}, SLA {sla_term.id}: {e}"
                    )

        logger.info(f"SLA compliance scan complete: {len(contracts)} contracts, {breach_count} breaches detected")

    except Exception as e:
        logger.error(f"SLA compliance scan failed: {e}")
