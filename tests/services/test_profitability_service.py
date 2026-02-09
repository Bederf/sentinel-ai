from datetime import date

from app.services.profitability_service import ProfitabilityService


class StubContractRepo:
    def __init__(self, contracts, assets_map):
        self._contracts = {contract["id"]: contract for contract in contracts}
        self._assets_map = assets_map

    def get_all(self, status=None):
        return list(self._contracts.values())

    def get_by_id(self, contract_id):
        return self._contracts.get(contract_id)

    def get_contract_assets(self, contract_id):
        return self._assets_map.get(contract_id, [])


class StubBudgetRepo:
    def __init__(self, budgets_map):
        self._budgets_map = budgets_map

    def get_by_contract(self, contract_id, year):
        return self._budgets_map.get((contract_id, year), [])


def test_calculate_contract_profitability():
    contracts = [
        {
            "id": "contract-1",
            "code": "CON-001",
            "monthly_fee_zar": 1000.0,
            "building_id": "building-1",
            "buildings": {"name": "Building One"},
        }
    ]
    assets_map = {"contract-1": [{"equipment_id": "EQ-1"}, {"equipment_id": "EQ-2"}]}
    budgets_map = {
        ("contract-1", 2026): [
            {
                "budget_month": 2,
                "labor_actual_zar": 200.0,
                "parts_actual_zar": 100.0,
                "subcontractor_actual_zar": 50.0,
                "callout_actual_zar": 25.0,
                "consumables_actual_zar": 25.0,
            }
        ]
    }

    service = ProfitabilityService.__new__(ProfitabilityService)
    service.contract_repo = StubContractRepo(contracts, assets_map)
    service.budget_repo = StubBudgetRepo(budgets_map)

    period_start = date(2026, 2, 1)
    period_end = date(2026, 2, 28)

    result = service.calculate_contract_profitability("contract-1", period_start, period_end)

    assert result.net_revenue_zar == 1000.0
    assert result.total_cost_zar == 400.0
    assert result.gross_margin_zar == 600.0
    assert result.gross_margin_percentage == 60.0
    assert result.status == "profitable"
    assert result.asset_count == 2


def test_calculate_portfolio_metrics():
    contracts = [
        {
            "id": "contract-1",
            "code": "CON-001",
            "monthly_fee_zar": 1000.0,
            "building_id": "building-1",
            "buildings": {"name": "Building One"},
        },
        {
            "id": "contract-2",
            "code": "CON-002",
            "monthly_fee_zar": 500.0,
            "building_id": "building-2",
            "buildings": {"name": "Building Two"},
        },
    ]
    assets_map = {
        "contract-1": [{"equipment_id": "EQ-1"}],
        "contract-2": [{"equipment_id": "EQ-2"}],
    }
    budgets_map = {
        ("contract-1", 2026): [
            {
                "budget_month": 2,
                "labor_actual_zar": 200.0,
                "parts_actual_zar": 100.0,
                "subcontractor_actual_zar": 50.0,
                "callout_actual_zar": 25.0,
                "consumables_actual_zar": 25.0,
            }
        ],
        ("contract-2", 2026): [
            {
                "budget_month": 2,
                "labor_actual_zar": 300.0,
                "parts_actual_zar": 150.0,
                "subcontractor_actual_zar": 150.0,
                "callout_actual_zar": 50.0,
                "consumables_actual_zar": 50.0,
            }
        ],
    }

    service = ProfitabilityService.__new__(ProfitabilityService)
    service.contract_repo = StubContractRepo(contracts, assets_map)
    service.budget_repo = StubBudgetRepo(budgets_map)

    period_start = date(2026, 2, 1)
    period_end = date(2026, 2, 28)

    metrics = service.calculate_portfolio_metrics(period_start, period_end)

    assert metrics.total_contracts == 2
    assert metrics.total_revenue_zar == 1500.0
    assert metrics.total_cost_zar == 1100.0
    assert metrics.gross_margin_zar == 400.0
    assert metrics.profit_contracts == 1
    assert metrics.loss_contracts == 1
