"""
Budget Reporting Service
========================
Phase 49-10: Cost reporting and export.
"""

from __future__ import annotations

from typing import Dict, Any, Optional

from app.database.repositories.budget_repository import BudgetRepository
from app.services.budget_variance_service import get_budget_variance_service


class BudgetReportingService:
    """Build budget vs actual reports with monthly breakdowns."""

    def __init__(self, budget_repo: Optional[BudgetRepository] = None):
        self.budget_repo = budget_repo or BudgetRepository()

    def build_report(self, contract_id: str, year: int, month: Optional[int] = None) -> Dict[str, Any]:
        budgets = self.budget_repo.get_by_contract(contract_id, year=year)
        monthly = []
        equipment_type_totals: Dict[str, Dict[str, float]] = {}

        for month in range(1, 13):
            entries = [b for b in budgets if b.get("budget_month") == month and b.get("equipment_type") is None]
            if not entries:
                monthly.append(
                    {
                        "month": month,
                        "total_budget_zar": 0.0,
                        "total_actual_zar": 0.0,
                        "variance_zar": 0.0,
                        "spend_percentage": 0.0,
                    }
                )
                continue

            entry = entries[0]
            total_budget = float(entry.get("total_budget_zar") or 0.0)
            total_actual = float(entry.get("total_actual_zar") or 0.0)
            variance = float(entry.get("variance_zar") or (total_budget - total_actual))
            spend_pct = round((total_actual / total_budget * 100), 2) if total_budget > 0 else 0.0

            monthly.append(
                {
                    "month": month,
                    "total_budget_zar": total_budget,
                    "total_actual_zar": total_actual,
                    "variance_zar": variance,
                    "spend_percentage": spend_pct,
                }
            )

        # Equipment-type breakdown (annual totals)
        for budget in budgets:
            equipment_type = budget.get("equipment_type")
            if not equipment_type:
                continue
            entry = equipment_type_totals.setdefault(
                equipment_type,
                {
                    "equipment_type": equipment_type,
                    "total_budget_zar": 0.0,
                    "total_actual_zar": 0.0,
                    "variance_zar": 0.0,
                    "spend_percentage": 0.0,
                },
            )
            if month is None or budget.get("budget_month") == month:
                entry["total_budget_zar"] += float(budget.get("total_budget_zar") or 0.0)
                entry["total_actual_zar"] += float(budget.get("total_actual_zar") or 0.0)

        for entry in equipment_type_totals.values():
            entry["variance_zar"] = entry["total_budget_zar"] - entry["total_actual_zar"]
            entry["spend_percentage"] = (
                round((entry["total_actual_zar"] / entry["total_budget_zar"] * 100), 2)
                if entry["total_budget_zar"] > 0
                else 0.0
            )

        filtered_monthly = monthly if month is None else [m for m in monthly if m["month"] == month]
        total_budget_ytd = sum(m["total_budget_zar"] for m in filtered_monthly)
        total_actual_ytd = sum(m["total_actual_zar"] for m in filtered_monthly)
        variance_ytd = total_budget_ytd - total_actual_ytd
        spend_pct_ytd = round((total_actual_ytd / total_budget_ytd * 100), 2) if total_budget_ytd > 0 else 0.0

        alerts = get_budget_variance_service().list_alerts(contract_id, year=year, month=month)
        alert_summary = {
            "warning": len([a for a in alerts if a.get("severity") == "warning"]),
            "critical": len([a for a in alerts if a.get("severity") == "critical"]),
            "open": len([a for a in alerts if a.get("status") == "open"]),
            "acknowledged": len([a for a in alerts if a.get("status") == "acknowledged"]),
            "resolved": len([a for a in alerts if a.get("status") == "resolved"]),
            "equipment_type": len([a for a in alerts if a.get("equipment_type")]),
        }

        return {
            "contract_id": contract_id,
            "year": year,
            "totals": {
                "total_budget_zar": round(total_budget_ytd, 2),
                "total_actual_zar": round(total_actual_ytd, 2),
                "variance_zar": round(variance_ytd, 2),
                "spend_percentage": spend_pct_ytd,
            },
            "month": month,
            "monthly": filtered_monthly,
            "equipment_type_breakdown": list(equipment_type_totals.values()),
            "alerts": alerts,
            "alert_summary": alert_summary,
        }


_service: Optional[BudgetReportingService] = None


def get_budget_reporting_service() -> BudgetReportingService:
    global _service
    if _service is None:
        _service = BudgetReportingService()
    return _service
