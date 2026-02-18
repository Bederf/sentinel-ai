"""
Cost Capture Service
====================
Phase 49-08: Actual cost capture from work orders and service records.

Aggregates completed work order costs into monthly contract budgets
so profitability and variance analytics have real actuals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Any, Optional

from app.database.repositories.budget_repository import BudgetRepository
from app.database.repositories.contract_repository import ContractRepository
from app.database.repositories.work_order_repository import WorkOrderRepository
from app.services.budget_variance_service import get_budget_variance_service

logger = logging.getLogger(__name__)


@dataclass
class CostCaptureSummary:
    contract_id: str
    period_year: int
    period_month: int
    work_orders_count: int
    labor_actual_zar: float
    parts_actual_zar: float
    subcontractor_actual_zar: float
    callout_actual_zar: float
    consumables_actual_zar: float
    total_actual_zar: float
    budget_id: Optional[str]


class CostCaptureService:
    """
    Aggregate completed work order costs into budget actuals.
    """

    def __init__(
        self,
        budget_repo: Optional[BudgetRepository] = None,
        contract_repo: Optional[ContractRepository] = None,
        work_order_repo: Optional[WorkOrderRepository] = None,
    ):
        self.budget_repo = budget_repo or BudgetRepository()
        self.contract_repo = contract_repo or ContractRepository()
        self.work_order_repo = work_order_repo or WorkOrderRepository()

    async def capture_actuals_for_contract(
        self,
        contract_id: str,
        year: int,
        month: int
    ) -> CostCaptureSummary:
        """
        Capture work order costs for a contract in a given month.

        Uses completed work orders linked to contract assets. If a work order
        is missing contract_id, it is inferred via asset_contracts and updated.
        """
        period_start = date(year, month, 1)
        period_end = self._get_month_end(period_start)

        contract = self.contract_repo.get_by_id(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        assets = self.contract_repo.get_contract_assets(contract_id)
        equipment_ids = [a.get("equipment_id") for a in assets if a.get("equipment_id")]

        work_orders = []
        if equipment_ids:
            work_orders = await self.work_order_repo.get_work_orders_for_equipment_list(
                equipment_ids=equipment_ids,
                start_date=period_start,
                end_date=period_end,
                status="completed"
            )

        labor_total = 0.0
        parts_total = 0.0
        subcontractor_total = 0.0
        callout_total = 0.0
        consumables_total = 0.0

        for wo in work_orders:
            labor = float(wo.get("labor_cost_zar") or 0.0)
            parts = float(wo.get("parts_cost_zar") or 0.0)
            total = float(wo.get("total_cost_zar") or 0.0)

            # If total exists but labor/parts missing, allocate to labor
            if total > 0 and labor == 0 and parts == 0:
                labor = total

            labor_total += labor
            parts_total += parts

            # Attach contract_id if missing (best effort)
            if not wo.get("contract_id"):
                try:
                    await self.work_order_repo.update_work_order(
                        wo["id"], {"contract_id": contract_id}
                    )
                except Exception:
                    pass

        total_actual = labor_total + parts_total + subcontractor_total + callout_total + consumables_total

        budget = self._get_or_create_budget(
            contract_id=contract_id,
            contract_code=contract.get("code", "CONTRACT"),
            year=year,
            month=month
        )

        budget_id = budget.get("id") if budget else None

        if budget_id:
            self.budget_repo.update(budget_id, {
                "labor_actual_zar": labor_total,
                "parts_actual_zar": parts_total,
                "subcontractor_actual_zar": subcontractor_total,
                "callout_actual_zar": callout_total,
                "consumables_actual_zar": consumables_total,
            })

            # Evaluate variance and create alerts if thresholds breached
            variance_service = get_budget_variance_service()
            variance_service.evaluate_budget(contract_id, year, month)
            variance_service.evaluate_equipment_type_budgets(contract_id, year, month)

        return CostCaptureSummary(
            contract_id=contract_id,
            period_year=year,
            period_month=month,
            work_orders_count=len(work_orders),
            labor_actual_zar=round(labor_total, 2),
            parts_actual_zar=round(parts_total, 2),
            subcontractor_actual_zar=round(subcontractor_total, 2),
            callout_actual_zar=round(callout_total, 2),
            consumables_actual_zar=round(consumables_total, 2),
            total_actual_zar=round(total_actual, 2),
            budget_id=budget_id
        )

    def _get_or_create_budget(
        self,
        contract_id: str,
        contract_code: str,
        year: int,
        month: int
    ) -> Optional[Dict[str, Any]]:
        budgets = self.budget_repo.get_by_contract(contract_id, year=year)
        for budget in budgets:
            if budget.get("budget_month") == month and budget.get("equipment_type") is None:
                return budget

        # Create a minimal monthly budget entry to hold actuals
        code = f"BUD-{contract_code}-{year}-{month:02d}"
        payload = {
            "code": code,
            "contract_id": contract_id,
            "budget_year": year,
            "budget_month": month,
            "labor_budget_zar": 0,
            "parts_budget_zar": 0,
            "consumables_budget_zar": 0,
            "subcontractor_budget_zar": 0,
            "callout_budget_zar": 0,
            "status": "draft",
            "notes": "Auto-created for actual cost capture"
        }
        return self.budget_repo.create(payload)

    def _get_month_end(self, month_start: date) -> date:
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1, day=1)
        return next_month - timedelta(days=1)


_service: Optional[CostCaptureService] = None


def get_cost_capture_service() -> CostCaptureService:
    global _service
    if _service is None:
        _service = CostCaptureService()
    return _service
