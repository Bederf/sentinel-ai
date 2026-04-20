"""
Budget Alert Repository - Variance alert operations.

Phase 49-09: Variance analysis and alerts.
"""

import logging
from typing import Any

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class BudgetAlertRepository:
    """Repository for budget variance alerts."""

    def __init__(self):
        self.client = get_supabase_client()

    def create_or_update(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Upsert a budget alert by contract/year/month/severity."""
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            result = (
                self.client.table("budget_alerts")
                .upsert(data, on_conflict="contract_id,period_year,period_month,severity,equipment_type")
                .execute()
            )

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error upserting budget alert: {e}")
            return None

    def list_by_contract(
        self,
        contract_id: str,
        year: int | None = None,
        month: int | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        """List alerts for a contract with optional filters."""
        if not self.client:
            return []

        try:
            query = (
                self.client.table("budget_alerts")
                .select("*")
                .eq("contract_id", contract_id)
                .order("created_at", desc=True)
            )

            if year:
                query = query.eq("period_year", year)
            if month:
                query = query.eq("period_month", month)
            if status:
                query = query.eq("status", status)
            if severity:
                query = query.eq("severity", severity)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error listing budget alerts: {e}")
            return []

    def update_status(self, alert_id: str, status: str) -> dict[str, Any] | None:
        """Update alert status (open, acknowledged, resolved)."""
        if not self.client:
            return None

        try:
            result = self.client.table("budget_alerts").update({"status": status}).eq("id", alert_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error updating budget alert {alert_id}: {e}")
            return None


_repository: BudgetAlertRepository | None = None


def get_budget_alert_repository() -> BudgetAlertRepository:
    global _repository
    if _repository is None:
        _repository = BudgetAlertRepository()
    return _repository
