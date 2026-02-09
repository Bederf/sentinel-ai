"""
SLA Repository (Phase 50)

Data access layer for SLA performance tracking, breach events, and compliance summaries.
Supports dual-write pattern (Supabase primary, JSON fallback) following existing repository patterns.

Key capabilities:
- Performance record CRUD operations
- Breach event tracking and storage
- Historical performance data retrieval
- Compliance summary aggregation
- Clawback amount updates
"""

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.contract import (
    SLABreachEvent,
    SLABreachSeverity,
    SLAComplianceStatus,
    SLAMetricType,
    SLAPerformanceWithCompliance,
    SLATerm,
)

logger = logging.getLogger(__name__)


class SLARepository:
    """
    Repository for SLA performance data and breach events.

    Singleton pattern - use get_sla_repository() factory.
    """

    def __init__(self):
        """Initialize SLA repository with JSON fallback storage."""
        self._json_path = Path(__file__).parent.parent.parent / "data" / "sla_performance.json"
        self._ensure_json_storage()

    # ========================================================================
    # Performance Record Management
    # ========================================================================

    def create_performance_record(
        self,
        perf: SLAPerformanceWithCompliance,
    ) -> SLAPerformanceWithCompliance:
        """
        Create SLA performance record.

        Args:
            perf: Performance record with compliance metrics

        Returns:
            Created performance record with ID
        """
        try:
            # Try Supabase first
            record = self._create_performance_supabase(perf)
            if record:
                return record
        except Exception as e:
            logger.warning(f"Supabase create failed, using JSON fallback: {e}")

        # Fallback to JSON storage
        return self._create_performance_json(perf)

    def get_performance_history(
        self,
        contract_id: str,
        months: int = 12,
    ) -> List[SLAPerformanceWithCompliance]:
        """
        Get historical performance data for a contract.

        Args:
            contract_id: Contract identifier
            months: Number of months to retrieve (default 12)

        Returns:
            List of performance records, most recent first
        """
        try:
            # Try Supabase first
            records = self._get_performance_supabase(contract_id, months)
            if records:
                return records
        except Exception as e:
            logger.warning(f"Supabase query failed, using JSON fallback: {e}")

        # Fallback to JSON storage
        return self._get_performance_json(contract_id, months)

    def update_clawback_amount(
        self,
        performance_id: str,
        amount: Decimal,
    ) -> bool:
        """
        Update clawback amount for a performance record.

        Args:
            performance_id: Performance record identifier
            amount: New clawback amount in ZAR

        Returns:
            True if updated successfully
        """
        try:
            # Try Supabase first
            if self._update_clawback_supabase(performance_id, amount):
                return True
        except Exception as e:
            logger.warning(f"Supabase update failed, using JSON fallback: {e}")

        # Fallback to JSON storage
        return self._update_clawback_json(performance_id, amount)

    # ========================================================================
    # Breach Event Management
    # ========================================================================

    def get_breach_events(
        self,
        contract_id: str,
        severity: Optional[SLABreachSeverity] = None,
    ) -> List[SLABreachEvent]:
        """
        Get breach events for a contract.

        Args:
            contract_id: Contract identifier
            severity: Optional severity filter

        Returns:
            List of breach events, most recent first
        """
        try:
            # Try Supabase first
            events = self._get_breaches_supabase(contract_id, severity)
            if events:
                return events
        except Exception as e:
            logger.warning(f"Supabase query failed, using JSON fallback: {e}")

        # Fallback to JSON storage
        return self._get_breaches_json(contract_id, severity)

    def create_breach_event(
        self,
        breach: SLABreachEvent,
    ) -> SLABreachEvent:
        """
        Create breach event record.

        Args:
            breach: Breach event to create

        Returns:
            Created breach event with ID
        """
        try:
            # Try Supabase first
            event = self._create_breach_supabase(breach)
            if event:
                return event
        except Exception as e:
            logger.warning(f"Supabase create failed, using JSON fallback: {e}")

        # Fallback to JSON storage
        return self._create_breach_json(breach)

    # ========================================================================
    # Compliance Summary
    # ========================================================================

    def get_compliance_summary(self, contract_id: str) -> Dict[str, Any]:
        """
        Get overall compliance summary for a contract.

        Returns aggregated metrics:
        - Overall compliance percentage
        - Total breaches (by severity)
        - Total clawback amount
        - SLA term breakdown

        Args:
            contract_id: Contract identifier

        Returns:
            Compliance summary dictionary
        """
        try:
            # Try Supabase first
            summary = self._get_summary_supabase(contract_id)
            if summary:
                return summary
        except Exception as e:
            logger.warning(f"Supabase query failed, using JSON fallback: {e}")

        # Fallback to JSON storage
        return self._get_summary_json(contract_id)

    def get_contracts_with_sla(self) -> List[Any]:
        """
        Get all contracts with active SLA terms.

        Returns list of contract objects with sla_terms populated.
        For demo purposes, returns mock data.

        Returns:
            List of contracts with SLA terms
        """
        # Demo implementation
        from app.models.contract import SLAType, MeasurementPeriod

        mock_contracts = [
            {
                "id": "con-001",
                "code": "CON-SITE-002-2026-001",
                "sla_terms": [
                    {
                        "id": "sla-001",
                        "sla_type": SLAType.UPTIME,
                        "target_value": 95.0,
                        "target_unit": "percent",
                        "measurement_period": MeasurementPeriod.MONTHLY,
                        "penalty_type": "percentage",
                        "penalty_value": 5.0,
                        "is_active": True,
                    },
                    {
                        "id": "sla-002",
                        "sla_type": SLAType.RESPONSE_TIME,
                        "target_value": 4.0,
                        "target_unit": "hours",
                        "measurement_period": MeasurementPeriod.MONTHLY,
                        "penalty_type": "fixed",
                        "penalty_value": 5000.0,
                        "is_active": True,
                    },
                ],
            }
        ]

        return mock_contracts

    def get_sla_term(self, sla_term_id: str) -> Optional[SLATerm]:
        """
        Get SLA term by ID.

        Args:
            sla_term_id: SLA term identifier

        Returns:
            SLATerm or None if not found
        """
        # Demo implementation
        from app.models.contract import SLAType, MeasurementPeriod

        if sla_term_id == "sla-001":
            return SLATerm(
                id="sla-001",
                contract_id="con-001",
                sla_type=SLAType.UPTIME,
                target_value=95.0,
                target_unit="percent",
                measurement_period=MeasurementPeriod.MONTHLY,
                penalty_type="percentage",
                penalty_value=5.0,
                is_active=True,
            )
        elif sla_term_id == "sla-002":
            return SLATerm(
                id="sla-002",
                contract_id="con-001",
                sla_type=SLAType.RESPONSE_TIME,
                target_value=4.0,
                target_unit="hours",
                measurement_period=MeasurementPeriod.MONTHLY,
                penalty_type="fixed",
                penalty_value=5000.0,
                is_active=True,
            )

        return None

    # ========================================================================
    # Private Helper Methods - Supabase
    # ========================================================================

    def _create_performance_supabase(
        self,
        perf: SLAPerformanceWithCompliance,
    ) -> Optional[SLAPerformanceWithCompliance]:
        """Create performance record in Supabase."""
        try:

            # Check if Supabase is configured
            if not self._is_supabase_configured():
                return None

            client = self._get_supabase_client()

            # Map to sla_performance table structure
            data = {
                "contract_id": perf.contract_id,
                "sla_term_id": perf.sla_term_id,
                "period_start": perf.period_start.isoformat(),
                "period_end": perf.period_end.isoformat(),
                "target_value": perf.target_value,
                "actual_value": perf.actual_value,
                "penalty_applied": perf.clawback_amount_zar > 0,
                "penalty_amount_zar": perf.clawback_amount_zar,
                "incidents_count": perf.breach_count,
                "details": {
                    "metric_type": perf.metric_type.value,
                    "compliance_percentage": perf.compliance_percentage,
                    "compliance_status": perf.compliance_status.value,
                    "breach_details": perf.breach_details,
                },
            }

            result = client.table("sla_performance").insert(data).execute()

            if result.data:
                # Update with returned ID
                perf.id = result.data[0]["id"]
                return perf

        except Exception as e:
            logger.error(f"Supabase create performance failed: {e}")

        return None

    def _get_performance_supabase(
        self,
        contract_id: str,
        months: int,
    ) -> Optional[List[SLAPerformanceWithCompliance]]:
        """Get performance history from Supabase."""
        try:
            if not self._is_supabase_configured():
                return None

            client = self._get_supabase_client()

            # Calculate date cutoff
            cutoff_date = date.today()
            for _ in range(months):
                # Move back one month
                if cutoff_date.month == 1:
                    cutoff_date = cutoff_date.replace(year=cutoff_date.year - 1, month=12)
                else:
                    cutoff_date = cutoff_date.replace(month=cutoff_date.month - 1)

            result = (
                client.table("sla_performance")
                .select("*")
                .eq("contract_id", contract_id)
                .gte("period_start", cutoff_date.isoformat())
                .order("period_start", desc=True)
                .execute()
            )

            if result.data:
                return [self._map_performance_row(row) for row in result.data]

        except Exception as e:
            logger.error(f"Supabase get performance failed: {e}")

        return None

    def _update_clawback_supabase(
        self,
        performance_id: str,
        amount: Decimal,
    ) -> bool:
        """Update clawback amount in Supabase."""
        try:
            if not self._is_supabase_configured():
                return False

            client = self._get_supabase_client()

            result = (
                client.table("sla_performance")
                .update(
                    {
                        "penalty_applied": True,
                        "penalty_amount_zar": float(amount),
                    }
                )
                .eq("id", performance_id)
                .execute()
            )

            return len(result.data) > 0

        except Exception as e:
            logger.error(f"Supabase update clawback failed: {e}")

        return False

    def _get_breaches_supabase(
        self,
        contract_id: str,
        severity: Optional[SLABreachSeverity],
    ) -> Optional[List[SLABreachEvent]]:
        """Get breach events from Supabase."""
        # For demo, return None to use JSON fallback
        return None

    def _create_breach_supabase(
        self,
        breach: SLABreachEvent,
    ) -> Optional[SLABreachEvent]:
        """Create breach event in Supabase."""
        # For demo, return None to use JSON fallback
        return None

    def _get_summary_supabase(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Get compliance summary from Supabase."""
        # For demo, return None to use JSON fallback
        return None

    # ========================================================================
    # Private Helper Methods - JSON Fallback
    # ========================================================================

    def _ensure_json_storage(self):
        """Ensure JSON storage file exists."""
        if not self._json_path.exists():
            self._json_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_json_data({"performance": [], "breaches": []})

    def _read_json_data(self) -> Dict[str, Any]:
        """Read data from JSON file."""
        try:
            with open(self._json_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read JSON data: {e}")
            return {"performance": [], "breaches": []}

    def _write_json_data(self, data: Dict[str, Any]):
        """Write data to JSON file."""
        try:
            with open(self._json_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to write JSON data: {e}")

    def _create_performance_json(
        self,
        perf: SLAPerformanceWithCompliance,
    ) -> SLAPerformanceWithCompliance:
        """Create performance record in JSON storage."""
        data = self._read_json_data()

        # Generate ID if not present
        if not perf.id or perf.id.startswith("perf-"):
            import uuid
            perf.id = f"perf-{uuid.uuid4().hex[:8]}"

        # Serialize to dict
        perf_dict = {
            "id": perf.id,
            "contract_id": perf.contract_id,
            "sla_term_id": perf.sla_term_id,
            "period_start": perf.period_start.isoformat(),
            "period_end": perf.period_end.isoformat(),
            "target_value": perf.target_value,
            "actual_value": perf.actual_value,
            "met_target": perf.met_target,
            "penalty_applied": perf.clawback_amount_zar > 0,
            "penalty_amount_zar": perf.clawback_amount_zar,
            "incidents_count": perf.breach_count,
            "details": {
                "metric_type": perf.metric_type.value,
                "compliance_percentage": perf.compliance_percentage,
                "compliance_status": perf.compliance_status.value,
                "breach_details": perf.breach_details,
            },
            "status": perf.status,
            "created_at": perf.created_at.isoformat() if perf.created_at else None,
            "updated_at": perf.updated_at.isoformat() if perf.updated_at else None,
        }

        data["performance"].append(perf_dict)
        self._write_json_data(data)

        return perf

    def _get_performance_json(
        self,
        contract_id: str,
        months: int,
    ) -> List[SLAPerformanceWithCompliance]:
        """Get performance history from JSON storage."""
        data = self._read_json_data()

        # Filter by contract_id
        filtered = [
            p
            for p in data["performance"]
            if p["contract_id"] == contract_id
        ]

        # Sort by period_start descending
        filtered.sort(key=lambda x: x["period_start"], reverse=True)

        # Limit to requested months
        filtered = filtered[:months]

        return [self._map_performance_dict(p) for p in filtered]

    def _update_clawback_json(
        self,
        performance_id: str,
        amount: Decimal,
    ) -> bool:
        """Update clawback amount in JSON storage."""
        data = self._read_json_data()

        for perf in data["performance"]:
            if perf["id"] == performance_id:
                perf["penalty_applied"] = True
                perf["penalty_amount_zar"] = float(amount)
                perf["updated_at"] = datetime.now().isoformat()
                self._write_json_data(data)
                return True

        return False

    def _get_breaches_json(
        self,
        contract_id: str,
        severity: Optional[SLABreachSeverity],
    ) -> List[SLABreachEvent]:
        """Get breach events from JSON storage."""
        # Demo implementation - return empty list
        return []

    def _create_breach_json(
        self,
        breach: SLABreachEvent,
    ) -> SLABreachEvent:
        """Create breach event in JSON storage."""
        # Generate ID if not present
        if not breach.id:
            import uuid
            breach.id = f"breach-{uuid.uuid4().hex[:8]}"

        # TODO: Store in JSON file
        return breach

    def _get_summary_json(self, contract_id: str) -> Dict[str, Any]:
        """Get compliance summary from JSON storage."""
        data = self._read_json_data()

        # Filter by contract_id
        performance = [
            p
            for p in data["performance"]
            if p["contract_id"] == contract_id
        ]

        if not performance:
            return {
                "contract_id": contract_id,
                "total_records": 0,
                "overall_compliance_pct": 100.0,
                "total_breaches": 0,
                "total_clawback_zar": 0.0,
                "by_severity": {},
                "by_metric": {},
            }

        # Calculate aggregates
        total_breaches = sum(p.get("incidents_count", 0) for p in performance)
        total_clawback = sum(p.get("penalty_amount_zar", 0.0) for p in performance)
        avg_compliance = sum(
            p.get("details", {}).get("compliance_percentage", 100.0)
            for p in performance
        ) / len(performance)

        # Count by severity
        by_severity = {"minor": 0, "major": 0, "critical": 0}
        for p in performance:
            for breach_detail in p.get("details", {}).get("breach_details", []):
                severity = breach_detail.get("severity", "minor")
                by_severity[severity] = by_severity.get(severity, 0) + 1

        return {
            "contract_id": contract_id,
            "total_records": len(performance),
            "overall_compliance_pct": round(avg_compliance, 1),
            "total_breaches": total_breaches,
            "total_clawback_zar": round(total_clawback, 2),
            "by_severity": by_severity,
            "by_metric": {},  # TODO: Implement metric breakdown
        }

    # ========================================================================
    # Mapping Helpers
    # ========================================================================

    def _map_performance_row(self, row: Dict[str, Any]) -> SLAPerformanceWithCompliance:
        """Map database row to SLAPerformanceWithCompliance."""
        details = row.get("details", {})

        return SLAPerformanceWithCompliance(
            id=row["id"],
            contract_id=row["contract_id"],
            sla_term_id=row["sla_term_id"],
            period_start=date.fromisoformat(row["period_start"]),
            period_end=date.fromisoformat(row["period_end"]),
            target_value=row["target_value"],
            actual_value=row["actual_value"],
            met_target=row.get("met_target"),
            penalty_applied=row.get("penalty_applied", False),
            penalty_amount_zar=row.get("penalty_amount_zar"),
            penalty_waived=row.get("penalty_waived", False),
            waiver_reason=row.get("waiver_reason"),
            incidents_count=row.get("incidents_count", 0),
            total_downtime_hours=row.get("total_downtime_hours"),
            details=details,
            status=row.get("status", "pending"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else None,
            metric_type=SLAMetricType(details.get("metric_type", "response_time")),
            compliance_percentage=details.get("compliance_percentage", 100.0),
            compliance_status=SLAComplianceStatus(details.get("compliance_status", "compliant")),
            breach_count=row.get("incidents_count", 0),
            breach_details=details.get("breach_details", []),
            clawback_amount_zar=row.get("penalty_amount_zar", 0.0),
        )

    def _map_performance_dict(self, p: Dict[str, Any]) -> SLAPerformanceWithCompliance:
        """Map dict to SLAPerformanceWithCompliance."""
        details = p.get("details", {})

        return SLAPerformanceWithCompliance(
            id=p["id"],
            contract_id=p["contract_id"],
            sla_term_id=p["sla_term_id"],
            period_start=date.fromisoformat(p["period_start"]),
            period_end=date.fromisoformat(p["period_end"]),
            target_value=p["target_value"],
            actual_value=p["actual_value"],
            met_target=p.get("met_target"),
            penalty_applied=p.get("penalty_applied", False),
            penalty_amount_zar=p.get("penalty_amount_zar"),
            penalty_waived=p.get("penalty_waived", False),
            waiver_reason=p.get("waiver_reason"),
            incidents_count=p.get("incidents_count", 0),
            total_downtime_hours=p.get("total_downtime_hours"),
            details=details,
            status=p.get("status", "pending"),
            created_at=datetime.fromisoformat(p["created_at"]) if p.get("created_at") else None,
            updated_at=datetime.fromisoformat(p["updated_at"]) if p.get("updated_at") else None,
            metric_type=SLAMetricType(details.get("metric_type", "response_time")),
            compliance_percentage=details.get("compliance_percentage", 100.0),
            compliance_status=SLAComplianceStatus(details.get("compliance_status", "compliant")),
            breach_count=p.get("incidents_count", 0),
            breach_details=details.get("breach_details", []),
            clawback_amount_zar=p.get("penalty_amount_zar", 0.0),
        )

    # ========================================================================
    # Supabase Configuration
    # ========================================================================

    def _is_supabase_configured(self) -> bool:
        """Check if Supabase is configured."""
        import os
        return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))

    def _get_supabase_client(self):
        """Get Supabase client."""
        from supabase import create_client
        import os

        return create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )


# ============================================================================
# Singleton Factory
# ============================================================================

_sla_repository_instance: Optional[SLARepository] = None


def get_sla_repository() -> SLARepository:
    """Get singleton SLA repository instance."""
    global _sla_repository_instance
    if _sla_repository_instance is None:
        _sla_repository_instance = SLARepository()
    return _sla_repository_instance
