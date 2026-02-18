"""
Profitability Aggregation Service
==================================
Service layer for calculating portfolio and contract-level profitability metrics.

Phase 51: Profitability Dashboards & Analytics
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from app.models.contract import (
    ContractProfitabilityDetail,
    LossLeaderAnalysis,
    PortfolioMetrics,
    ProfitabilityTrend,
)
from app.database.repositories.contract_repository import ContractRepository
from app.database.repositories.budget_repository import BudgetRepository
from app.database.repositories.sla_repository import get_sla_repository

logger = logging.getLogger(__name__)


# ============================================================================
# Singleton Factory
# ============================================================================


_profitability_service_instance = None


def get_profitability_service() -> "ProfitabilityService":
    """Get or create singleton ProfitabilityService instance."""
    global _profitability_service_instance
    if _profitability_service_instance is None:
        _profitability_service_instance = ProfitabilityService()
    return _profitability_service_instance


# ============================================================================
# Profitability Service
# ============================================================================


class ProfitabilityService:
    """
    Service for calculating profitability metrics across contracts and portfolio.

    Aggregates data from contracts, budgets, SLA performance, and work orders
    to provide comprehensive profitability analysis.
    """

    def __init__(self):
        self.contract_repo = ContractRepository()
        self.budget_repo = BudgetRepository()
        self.sla_repo = get_sla_repository()

    def calculate_portfolio_metrics(
        self,
        period_start: date,
        period_end: date
    ) -> PortfolioMetrics:
        """
        Calculate portfolio-wide profitability metrics for a period.

        Args:
            period_start: Period start date
            period_end: Period end date

        Returns:
            PortfolioMetrics with aggregated metrics
        """
        contracts = self.contract_repo.get_all(status="active")

        if not contracts:
            return PortfolioMetrics(
                total_contracts=0,
                total_revenue_zar=0.0,
                total_cost_zar=0.0,
                gross_margin_zar=0.0,
                gross_margin_percentage=0.0,
                profit_contracts=0,
                loss_contracts=0,
                avg_margin_percentage=0.0,
                period_start=period_start,
                period_end=period_end
            )

        total_revenue = 0.0
        total_cost = 0.0
        profit_count = 0
        margins = []

        for contract in contracts:
            profitability = self.calculate_contract_profitability(
                contract["id"], period_start, period_end
            )
            total_revenue += profitability.net_revenue_zar
            total_cost += profitability.total_cost_zar
            margins.append(profitability.gross_margin_percentage)

            if profitability.status == "profitable":
                profit_count += 1

        gross_margin = total_revenue - total_cost
        margin_pct = round(
            (gross_margin / total_revenue * 100) if total_revenue > 0 else 0.0, 2
        )
        avg_margin = round(sum(margins) / len(margins), 2) if margins else 0.0

        return PortfolioMetrics(
            total_contracts=len(contracts),
            total_revenue_zar=round(total_revenue, 2),
            total_cost_zar=round(total_cost, 2),
            gross_margin_zar=round(gross_margin, 2),
            gross_margin_percentage=margin_pct,
            profit_contracts=profit_count,
            loss_contracts=len(contracts) - profit_count,
            avg_margin_percentage=avg_margin,
            period_start=period_start,
            period_end=period_end
        )

    def calculate_contract_profitability(
        self,
        contract_id: str,
        period_start: date,
        period_end: date
    ) -> ContractProfitabilityDetail:
        """
        Calculate detailed profitability for a single contract.

        Args:
            contract_id: Contract UUID
            period_start: Period start date
            period_end: Period end date

        Returns:
            ContractProfitabilityDetail with full breakdown
        """
        contract = self.contract_repo.get_by_id(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        # Revenue components
        monthly_revenue = contract.get("monthly_fee_zar", 0.0) or 0.0
        clawbacks = self._get_clawbacks_for_period(contract_id, period_start, period_end)
        net_revenue = monthly_revenue - clawbacks

        # Cost components from budgets
        costs = self._get_contract_costs(contract_id, period_start, period_end)
        total_cost = sum(costs.values())

        # Profitability metrics
        gross_margin = net_revenue - total_cost
        margin_pct = round(
            (gross_margin / net_revenue * 100) if net_revenue > 0 else 0.0, 2
        )

        if gross_margin > 0:
            status = "profitable"
        elif gross_margin < 0:
            status = "loss"
        else:
            status = "break_even"

        # Assets
        assets = self.contract_repo.get_contract_assets(contract_id)
        asset_count = len(assets) if assets else 0
        cost_per_asset = round(total_cost / asset_count, 2) if asset_count > 0 else 0.0

        # Month-over-month change
        mom_change = self._calculate_mom_change(
            contract_id, period_start, period_end
        )

        return ContractProfitabilityDetail(
            contract_id=contract["id"],
            contract_name=contract.get("code", "Unknown"),
            building_id=contract.get("building_id", ""),
            building_name=contract.get("buildings", {}).get("name") if contract.get("buildings") else None,
            monthly_revenue_zar=round(monthly_revenue, 2),
            clawbacks_zar=round(clawbacks, 2),
            net_revenue_zar=round(net_revenue, 2),
            labor_cost_zar=round(costs.get("labor", 0.0), 2),
            parts_cost_zar=round(costs.get("parts", 0.0), 2),
            subcontractor_cost_zar=round(costs.get("subcontractor", 0.0), 2),
            callout_cost_zar=round(costs.get("callout", 0.0), 2),
            consumables_cost_zar=round(costs.get("consumables", 0.0), 2),
            total_cost_zar=round(total_cost, 2),
            gross_margin_zar=round(gross_margin, 2),
            gross_margin_percentage=margin_pct,
            status=status,
            mom_change_pct=mom_change,
            asset_count=asset_count,
            cost_per_asset_zar=cost_per_asset
        )

    def identify_loss_leaders(
        self,
        period_start: date,
        period_end: date
    ) -> List[LossLeaderAnalysis]:
        """
        Identify contracts with negative margins and analyze root causes.

        Args:
            period_start: Period start date
            period_end: Period end date

        Returns:
            List of LossLeaderAnalysis sorted by loss amount (descending)
        """
        contracts = self.contract_repo.get_all(status="active")
        loss_leaders = []

        for contract in contracts:
            try:
                profitability = self.calculate_contract_profitability(
                    contract["id"], period_start, period_end
                )

                if profitability.status == "loss":
                    root_causes = self._analyze_loss_causes(profitability)
                    recommendation = self._generate_recommendation(root_causes)

                    # Check for ongoing losses
                    months_in_loss = self._count_consecutive_loss_months(
                        contract["id"], period_end
                    )
                    cumulative_loss = self._calculate_cumulative_loss(
                        contract["id"], months_in_loss
                    )

                    loss_leaders.append(LossLeaderAnalysis(
                        contract_id=contract["id"],
                        contract_name=contract.get("code", "Unknown"),
                        loss_amount_zar=abs(profitability.gross_margin_zar),
                        loss_percentage=abs(profitability.gross_margin_percentage),
                        root_causes=root_causes,
                        recommendation=recommendation,
                        months_in_loss=months_in_loss,
                        cumulative_loss_zar=cumulative_loss
                    ))
            except Exception as e:
                logger.warning(f"Error analyzing contract {contract['id']}: {e}")
                continue

        # Sort by loss amount descending
        return sorted(loss_leaders, key=lambda x: x.loss_amount_zar, reverse=True)

    def calculate_profitability_trends(
        self,
        contract_id: str,
        months: int = 12
    ) -> List[ProfitabilityTrend]:
        """
        Calculate monthly profitability trends for a contract.

        Args:
            contract_id: Contract UUID
            months: Number of months to analyze (default 12)

        Returns:
            List of ProfitabilityTrend data points
        """
        trends = []
        today = date.today()

        for i in range(months):
            # Calculate period bounds for month i
            from datetime import timedelta
            period_end_month = today.replace(day=1) - timedelta(days=i*28)
            period_start = period_end_month.replace(day=1)
            period_end = self._get_month_end(period_start)

            period_str = period_start.strftime("%Y-%m")

            try:
                profitability = self.calculate_contract_profitability(
                    contract_id, period_start, period_end
                )

                # Determine trend direction
                if i > 0 and len(trends) > 0:
                    prev_margin = trends[0].margin_pct
                    curr_margin = profitability.gross_margin_percentage
                    if curr_margin > prev_margin + 2.0:
                        trend = "improving"
                    elif curr_margin < prev_margin - 2.0:
                        trend = "declining"
                    else:
                        trend = "stable"
                else:
                    trend = "stable"

                trends.insert(0, ProfitabilityTrend(
                    contract_id=contract_id,
                    period=period_str,
                    revenue_zar=profitability.net_revenue_zar,
                    cost_zar=profitability.total_cost_zar,
                    margin_zar=profitability.gross_margin_zar,
                    margin_pct=profitability.gross_margin_percentage,
                    trend=trend
                ))
            except Exception as e:
                logger.warning(f"Error calculating trend for {period_str}: {e}")
                continue

        return trends

    def calculate_asset_roi(
        self,
        contract_id: str,
        equipment_id: str,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Calculate ROI for a specific asset within a contract.

        Args:
            contract_id: Contract UUID
            equipment_id: Equipment code/ID

        Returns:
            Dict with ROI metrics (revenue, costs, margin, roi_percentage)
        """
        # Get contract
        contract = self.contract_repo.get_by_id(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        # Get asset contract allocation
        assets = self.contract_repo.get_contract_assets(contract_id)
        asset_contract = None
        for asset in assets:
            if asset.get("equipment_id") == equipment_id:
                asset_contract = asset
                break

        if not asset_contract:
            raise ValueError(f"Equipment {equipment_id} not found in contract")

        # Revenue allocation
        allocated_revenue = asset_contract.get("allocated_fee_zar", 0.0) or 0.0
        fee_pct = asset_contract.get("fee_allocation_pct", 0.0) or 0.0
        if fee_pct > 0 and allocated_revenue == 0:
            allocated_revenue = contract.get("monthly_fee_zar", 0.0) * (fee_pct / 100)

        # Cost allocation (simplified - assumes even distribution)
        all_assets = self.contract_repo.get_contract_assets(contract_id)
        total_asset_count = len(all_assets) if all_assets else 1

        if period_start is None or period_end is None:
            today = date.today()
            period_start = today.replace(day=1)
            period_end = self._get_month_end(period_start)

        total_costs = self._get_contract_costs(contract_id, period_start, period_end)
        total_contract_cost = sum(total_costs.values())

        allocated_cost = total_contract_cost / total_asset_count

        # Calculate ROI
        margin = allocated_revenue - allocated_cost
        roi_pct = round((margin / allocated_cost * 100) if allocated_cost > 0 else 0.0, 2)

        return {
            "equipment_id": equipment_id,
            "contract_id": contract_id,
            "allocated_revenue_zar": round(allocated_revenue, 2),
            "allocated_cost_zar": round(allocated_cost, 2),
            "margin_zar": round(margin, 2),
            "roi_percentage": roi_pct,
            "coverage_type": asset_contract.get("coverage_type", "full")
        }

    def calculate_contract_asset_roi_list(
        self,
        contract_id: str,
        period_start: date,
        period_end: date,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Calculate ROI for all assets in a contract.

        Returns:
            List of asset ROI dicts (optionally limited)
        """
        contract = self.contract_repo.get_by_id(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        assets = self.contract_repo.get_contract_assets(contract_id)
        if not assets:
            return []

        monthly_fee = contract.get("monthly_fee_zar", 0.0) or 0.0
        total_costs = self._get_contract_costs(contract_id, period_start, period_end)
        total_contract_cost = sum(total_costs.values())
        total_asset_count = len(assets) if assets else 1

        results = []
        for asset in assets:
            equipment_id = asset.get("equipment_id")
            allocated_revenue = asset.get("allocated_fee_zar", 0.0) or 0.0
            fee_pct = asset.get("fee_allocation_pct", 0.0) or 0.0

            if fee_pct > 0 and allocated_revenue == 0:
                allocated_revenue = monthly_fee * (fee_pct / 100)
            if allocated_revenue == 0 and total_asset_count > 0:
                allocated_revenue = monthly_fee / total_asset_count

            allocated_cost = total_contract_cost / total_asset_count if total_asset_count > 0 else 0.0
            margin = allocated_revenue - allocated_cost
            roi_pct = round((margin / allocated_cost * 100) if allocated_cost > 0 else 0.0, 2)

            results.append({
                "equipment_id": equipment_id,
                "equipment_code": asset.get("equipment", {}).get("code") if asset.get("equipment") else None,
                "equipment_name": asset.get("equipment", {}).get("name") if asset.get("equipment") else None,
                "equipment_type": asset.get("equipment", {}).get("type") if asset.get("equipment") else None,
                "contract_id": contract_id,
                "allocated_revenue_zar": round(allocated_revenue, 2),
                "allocated_cost_zar": round(allocated_cost, 2),
                "margin_zar": round(margin, 2),
                "roi_percentage": roi_pct,
                "coverage_type": asset.get("coverage_type", "full"),
            })

        results.sort(key=lambda r: r["roi_percentage"], reverse=True)
        if limit is not None:
            return results[:limit]
        return results

    def generate_contract_report(
        self,
        contract_id: str,
        period_start: date,
        period_end: date,
        asset_limit: int = 15
    ) -> Dict[str, Any]:
        """
        Generate a profitability report for a contract.

        Includes profitability breakdown, trends, asset ROI list, and data-quality flags.
        """
        contract = self.contract_repo.get_by_id(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        profitability = self.calculate_contract_profitability(
            contract_id, period_start, period_end
        )
        trends = self.calculate_profitability_trends(contract_id, months=12)
        assets = self.calculate_contract_asset_roi_list(
            contract_id, period_start, period_end, limit=asset_limit
        )

        data_quality_flags = []
        if profitability.total_cost_zar == 0:
            data_quality_flags.append("missing_cost_actuals")
        if profitability.asset_count == 0:
            data_quality_flags.append("missing_asset_assignments")
        if profitability.net_revenue_zar == 0:
            data_quality_flags.append("missing_revenue")

        return {
            "contract": {
                "id": contract.get("id"),
                "code": contract.get("code"),
                "status": contract.get("status"),
                "organization_name": contract.get("organizations", {}).get("name") if contract.get("organizations") else None,
                "building_name": contract.get("buildings", {}).get("name") if contract.get("buildings") else None,
            },
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "profitability": profitability.model_dump(),
            "trends": [trend.model_dump() for trend in trends],
            "assets": assets,
            "data_quality_flags": data_quality_flags,
            "assumptions": [
                "Asset cost allocation uses even distribution when no fee allocation is provided.",
                "Actual costs are sourced from budget actuals for the period.",
            ],
        }

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_clawbacks_for_period(
        self,
        contract_id: str,
        period_start: date,
        period_end: date
    ) -> float:
        """
        Get total SLA clawbacks for a contract in a period.

        Uses SLA performance records if available, otherwise returns 0.0.
        """
        try:
            performance = self.sla_repo.get_performance_history(contract_id, months=12)
            total = 0.0
            for perf in performance:
                start = perf.period_start
                end = perf.period_end
                if not start or not end:
                    continue
                if start <= period_end and end >= period_start:
                    total += float(getattr(perf, "clawback_amount_zar", 0.0) or 0.0)
            return round(total, 2)
        except Exception as e:
            logger.warning(f"Error getting clawbacks for contract {contract_id}: {e}")
            return 0.0

    def _get_contract_costs(
        self,
        contract_id: str,
        period_start: date,
        period_end: date
    ) -> Dict[str, float]:
        """
        Get cost breakdown for a contract in a period.

        Returns dict with labor, parts, subcontractor, callout, consumables costs.
        """
        costs = {
            "labor": 0.0,
            "parts": 0.0,
            "subcontractor": 0.0,
            "callout": 0.0,
            "consumables": 0.0
        }

        try:
            # Get budgets for the period
            year = period_start.year
            month = period_start.month
            budgets = self.budget_repo.get_by_contract(contract_id, year)

            # Filter by month and sum actuals
            for budget in budgets:
                if budget.get("budget_month") == month:
                    costs["labor"] += budget.get("labor_actual_zar", 0.0) or 0.0
                    costs["parts"] += budget.get("parts_actual_zar", 0.0) or 0.0
                    costs["subcontractor"] += budget.get("subcontractor_actual_zar", 0.0) or 0.0
                    costs["callout"] += budget.get("callout_actual_zar", 0.0) or 0.0
                    costs["consumables"] += budget.get("consumables_actual_zar", 0.0) or 0.0
        except Exception as e:
            logger.warning(f"Error getting costs for contract {contract_id}: {e}")

        return costs

    def _calculate_mom_change(
        self,
        contract_id: str,
        current_start: date,
        current_end: date
    ) -> Optional[float]:
        """Calculate month-over-month margin percentage change."""
        try:
            contract = self.contract_repo.get_by_id(contract_id)
            if not contract:
                return None

            from datetime import timedelta
            prev_month_end = current_start - timedelta(days=1)
            prev_month_start = prev_month_end.replace(day=1)

            current_net = (contract.get("monthly_fee_zar", 0.0) or 0.0) - self._get_clawbacks_for_period(
                contract_id, current_start, current_end
            )
            prev_net = (contract.get("monthly_fee_zar", 0.0) or 0.0) - self._get_clawbacks_for_period(
                contract_id, prev_month_start, prev_month_end
            )

            current_cost = sum(self._get_contract_costs(contract_id, current_start, current_end).values())
            prev_cost = sum(self._get_contract_costs(contract_id, prev_month_start, prev_month_end).values())

            current_margin_pct = (current_net - current_cost) / current_net * 100 if current_net > 0 else 0.0
            prev_margin_pct = (prev_net - prev_cost) / prev_net * 100 if prev_net > 0 else 0.0

            if prev_margin_pct != 0:
                change = ((current_margin_pct - prev_margin_pct) / abs(prev_margin_pct)) * 100
                return round(change, 2)
            return None
        except Exception:
            return None

    def _analyze_loss_causes(
        self,
        profitability: ContractProfitabilityDetail
    ) -> List[str]:
        """Analyze root causes of contract losses."""
        causes = []

        # Check for high labor costs (>50% of total)
        if profitability.labor_cost_zar > profitability.total_cost_zar * 0.5:
            causes.append("high_labor_costs")

        # Check for high parts costs
        if profitability.parts_cost_zar > profitability.total_cost_zar * 0.3:
            causes.append("excessive_parts_costs")

        # Check for high subcontractor costs
        if profitability.subcontractor_cost_zar > profitability.total_cost_zar * 0.2:
            causes.append("subcontractor_over_reliance")

        # Check for low revenue per asset
        if profitability.asset_count > 0:
            revenue_per_asset = profitability.net_revenue_zar / profitability.asset_count
            if revenue_per_asset < 1000:  # Less than R1000 per asset
                causes.append("underpriced_contract")

        # Check if margin is severely negative
        if profitability.gross_margin_percentage < -20:
            causes.append("severe_underpricing")

        if not causes:
            causes.append("general_inefficiency")

        return causes

    def _generate_recommendation(self, root_causes: List[str]) -> str:
        """Generate actionable recommendation based on root causes."""
        recommendations = {
            "high_labor_costs": "Review technician allocation efficiency. Consider scheduling optimization or training to improve first-time fix rates.",
            "excessive_parts_costs": "Implement preventive maintenance program to reduce emergency parts purchases. Negotiate bulk discounts with suppliers.",
            "subcontractor_over_reliance": "Evaluate bringing specialized work in-house. Review subcontractor margins and performance.",
            "underpriced_contract": "Initiate contract renegotiation. Document cost overruns to support rate adjustment request.",
            "severe_underpricing": "URGENT: Immediate contract review required. Consider exit strategy if client refuses rate adjustment.",
            "general_inefficiency": "Conduct operational audit. Review work order patterns and technician utilization."
        }

        # Generate combined recommendation
        recommendations_list = [recommendations.get(cause, "Review operational efficiency") for cause in root_causes]
        return " | ".join(recommendations_list)

    def _count_consecutive_loss_months(
        self,
        contract_id: str,
        as_of_date: date
    ) -> int:
        """Count consecutive months with losses for a contract."""
        loss_months = 0
        check_date = as_of_date

        for _ in range(12):  # Check up to 12 months back
            period_start = check_date.replace(day=1)
            period_end = self._get_month_end(period_start)

            try:
                profitability = self.calculate_contract_profitability(
                    contract_id, period_start, period_end
                )

                if profitability.status == "loss":
                    loss_months += 1
                    # Move to previous month
                    from datetime import timedelta
                    check_date = period_start - timedelta(days=1)
                else:
                    break
            except Exception:
                break

        return loss_months

    def _calculate_cumulative_loss(
        self,
        contract_id: str,
        months: int
    ) -> float:
        """Calculate cumulative loss over N consecutive months."""
        cumulative = 0.0
        today = date.today()

        for i in range(months):
            from datetime import timedelta
            period_end_month = today.replace(day=1) - timedelta(days=i*28)
            period_start = period_end_month.replace(day=1)
            period_end = self._get_month_end(period_start)

            try:
                profitability = self.calculate_contract_profitability(
                    contract_id, period_start, period_end
                )

                if profitability.status == "loss":
                    cumulative += abs(profitability.gross_margin_zar)
                else:
                    break
            except Exception:
                continue

        return round(cumulative, 2)

    def _get_month_end(self, month_start: date) -> date:
        """Get the last day of a month given the start date."""
        from datetime import timedelta
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1, day=1)
        return next_month - timedelta(days=1)

    def _is_profitable(
        self,
        contract_id: str,
        period_start: date,
        period_end: date
    ) -> bool:
        """Check if a contract is profitable in a period."""
        try:
            profitability = self.calculate_contract_profitability(
                contract_id, period_start, period_end
            )
            return profitability.status == "profitable"
        except Exception:
            return False

    def _calculate_contract_cost(
        self,
        contract_id: str,
        period_start: date,
        period_end: date
    ) -> float:
        """Calculate total cost for a contract in a period."""
        costs = self._get_contract_costs(contract_id, period_start, period_end)
        return sum(costs.values())

    def _get_period_offset(self, months_ago: int) -> str:
        """Get period string (YYYY-MM) for N months ago."""
        from datetime import timedelta
        today = date.today()
        target = today.replace(day=1) - timedelta(days=months_ago*28)
        return target.strftime("%Y-%m")

    def _get_period_bounds(self, period_str: str) -> tuple[date, date]:
        """Get start and end dates for a period string (YYYY-MM)."""
        year, month = map(int, period_str.split("-"))
        period_start = date(year, month, 1)
        period_end = self._get_month_end(period_start)
        return period_start, period_end

    def _get_previous_period(self, current_start: date) -> date:
        """Get the start of the previous period."""
        from datetime import timedelta
        return (current_start.replace(day=1) - timedelta(days=1)).replace(day=1)
