from decimal import Decimal

from app.models.pricing import QuoteRequest, SLATier
from app.services.pricing_engine import PricingEngine


class StubBudgetRepo:
    def get_budget_templates(self):
        return {
            "chiller": {
                "typical_monthly_breakdown": {
                    "labor": 1000,
                    "parts": 500,
                }
            }
        }


class StubConditionRepo:
    def get_latest_assessment(self, equipment_code):
        return {"overall_score": 2}


class StubContractRepo:
    def get_equipment(self, equipment_code):
        return {"installed_date": "2010-01-01"}

    def find_similar_contracts(self, equipment_types, sla_tier):
        return [
            {"monthly_fee_zar": Decimal("15000")},
            {"monthly_fee_zar": Decimal("17000")},
        ]


def test_pricing_engine_calculates_fee_with_adjustments():
    engine = PricingEngine(
        budget_repo=StubBudgetRepo(),
        condition_repo=StubConditionRepo(),
        contract_repo=StubContractRepo(),
    )

    request = QuoteRequest(
        building_id="site-002",
        equipment_codes=["S002-CHILLER-B1-001"],
        sla_tier=SLATier.standard,
    )

    response = engine.calculate_price(request)

    assert response.recommended_fee_zar > 0
    assert response.fee_range_zar["min"] < response.fee_range_zar["target"]
    assert response.fee_range_zar["max"] > response.fee_range_zar["target"]

    # Base cost: 1500; condition adj (score 2 => 1.75x) = 1125
    # Age adj (>15y => 1.3x) = 450; risk buffer (10%) = 75
    # SLA standard (1.15x) = 225; total cost = 3375
    # Margin 25% = 843.75; recommended = 4218.75
    assert response.cost_breakdown["base_cost"] == Decimal("1500")
    assert response.cost_breakdown["condition_adjustment"] == Decimal("1125")
    assert response.cost_breakdown["age_adjustment"] == Decimal("450")
    assert response.cost_breakdown["risk_buffer"] == Decimal("75")
    assert response.cost_breakdown["sla_adjustment"] == Decimal("225")
    assert response.cost_breakdown["margin"] == Decimal("843.75")
    assert response.recommended_fee_zar == Decimal("4218.75")
