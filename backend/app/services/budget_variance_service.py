"""
Budget Variance Service
=======================
Phase 49-09: Variance analysis and alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.database.repositories.budget_alert_repository import BudgetAlertRepository
from app.database.repositories.budget_repository import BudgetRepository


@dataclass
class BudgetVarianceResult:
    contract_id: str
    budget_id: str | None
    period_year: int
    period_month: int
    total_budget_zar: float
    total_actual_zar: float
    variance_zar: float
    spend_percentage: float
    severity: str | None
    message: str | None


class BudgetVarianceService:
    """Compute variance and create alerts."""

    def __init__(
        self, budget_repo: BudgetRepository | None = None, alert_repo: BudgetAlertRepository | None = None
    ):
        self.budget_repo = budget_repo or BudgetRepository()
        self.alert_repo = alert_repo or BudgetAlertRepository()

    def evaluate_budget(self, contract_id: str, year: int, month: int) -> BudgetVarianceResult:
        budgets = self.budget_repo.get_by_contract(contract_id, year=year)
        budget = next((b for b in budgets if b.get("budget_month") == month and b.get("equipment_type") is None), None)
        if not budget:
            return BudgetVarianceResult(
                contract_id=contract_id,
                budget_id=None,
                period_year=year,
                period_month=month,
                total_budget_zar=0.0,
                total_actual_zar=0.0,
                variance_zar=0.0,
                spend_percentage=0.0,
                severity=None,
                message=None,
            )

        total_budget = float(budget.get("total_budget_zar") or 0.0)
        total_actual = float(budget.get("total_actual_zar") or 0.0)
        variance = float(budget.get("variance_zar") or (total_budget - total_actual))
        spend_pct = round((total_actual / total_budget * 100), 2) if total_budget > 0 else 0.0

        warning_threshold = float(budget.get("warning_threshold_pct") or 80.0)
        critical_threshold = float(budget.get("critical_threshold_pct") or 100.0)

        severity = None
        message = None
        if spend_pct >= critical_threshold:
            severity = "critical"
            message = f"Critical budget overrun: {spend_pct:.1f}% of budget used."
        elif spend_pct >= warning_threshold:
            severity = "warning"
            message = f"Budget warning: {spend_pct:.1f}% of budget used."

        if severity:
            self.alert_repo.create_or_update(
                {
                    "contract_id": contract_id,
                    "budget_id": budget.get("id"),
                    "period_year": year,
                    "period_month": month,
                    "spend_percentage": spend_pct,
                    "total_budget_zar": total_budget,
                    "total_actual_zar": total_actual,
                    "variance_zar": variance,
                    "severity": severity,
                    "message": message,
                    "status": "open",
                }
            )

        return BudgetVarianceResult(
            contract_id=contract_id,
            budget_id=budget.get("id"),
            period_year=year,
            period_month=month,
            total_budget_zar=total_budget,
            total_actual_zar=total_actual,
            variance_zar=variance,
            spend_percentage=spend_pct,
            severity=severity,
            message=message,
        )

    def evaluate_equipment_type_budgets(self, contract_id: str, year: int, month: int) -> list[dict[str, Any]]:
        budgets = self.budget_repo.get_by_contract(contract_id, year=year)
        results: list[dict[str, Any]] = []

        for budget in budgets:
            equipment_type = budget.get("equipment_type")
            if not equipment_type or budget.get("budget_month") != month:
                continue

            total_budget = float(budget.get("total_budget_zar") or 0.0)
            total_actual = float(budget.get("total_actual_zar") or 0.0)
            variance = float(budget.get("variance_zar") or (total_budget - total_actual))
            spend_pct = round((total_actual / total_budget * 100), 2) if total_budget > 0 else 0.0

            warning_threshold = float(budget.get("warning_threshold_pct") or 80.0)
            critical_threshold = float(budget.get("critical_threshold_pct") or 100.0)

            severity = None
            message = None
            if spend_pct >= critical_threshold:
                severity = "critical"
                message = f"{equipment_type} budget critical: {spend_pct:.1f}% used."
            elif spend_pct >= warning_threshold:
                severity = "warning"
                message = f"{equipment_type} budget warning: {spend_pct:.1f}% used."

            if severity:
                self.alert_repo.create_or_update(
                    {
                        "contract_id": contract_id,
                        "budget_id": budget.get("id"),
                        "period_year": year,
                        "period_month": month,
                        "spend_percentage": spend_pct,
                        "total_budget_zar": total_budget,
                        "total_actual_zar": total_actual,
                        "variance_zar": variance,
                        "severity": severity,
                        "message": message,
                        "equipment_type": equipment_type,
                        "status": "open",
                    }
                )

            results.append(
                {
                    "equipment_type": equipment_type,
                    "budget_id": budget.get("id"),
                    "total_budget_zar": total_budget,
                    "total_actual_zar": total_actual,
                    "variance_zar": variance,
                    "spend_percentage": spend_pct,
                    "severity": severity,
                    "message": message,
                }
            )

        return results

    def list_alerts(
        self,
        contract_id: str,
        year: int | None = None,
        month: int | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.alert_repo.list_by_contract(
            contract_id=contract_id, year=year, month=month, status=status, severity=severity
        )


_service: BudgetVarianceService | None = None


def get_budget_variance_service() -> BudgetVarianceService:
    global _service
    if _service is None:
        _service = BudgetVarianceService()
    return _service
