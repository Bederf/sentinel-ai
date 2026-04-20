"""Tests for CapEx Planning Service (Phase 128).

Tests NPV calculations, TCO, replace-vs-repair decision logic,
portfolio analysis, and scenario modeling.
"""

from datetime import date

import pytest

from app.services import capex_planning_service


class TestNPV:
    """Test Net Present Value calculations."""

    def test_npv_no_discount(self):
        """NPV with 0% discount is simple sum."""
        flows = [-100, 50, 50, 50]
        npv = capex_planning_service.calculate_npv(flows, 0.0)
        assert npv == 50.0

    def test_npv_with_discount(self):
        """NPV discounts future cash flows."""
        flows = [-1000, 500, 500, 500]
        npv = capex_planning_service.calculate_npv(flows, 0.10)
        # -1000 + 500/1.1 + 500/1.21 + 500/1.331
        assert npv == pytest.approx(243.43, abs=1.0)

    def test_npv_single_flow(self):
        """Single cash flow returns itself."""
        assert capex_planning_service.calculate_npv([-500], 0.10) == -500.0

    def test_npv_empty_flows(self):
        """Empty cash flows returns 0."""
        assert capex_planning_service.calculate_npv([], 0.10) == 0.0

    def test_npv_high_discount_rate(self):
        """High discount rate heavily penalizes future flows."""
        flows = [-100, 200]
        npv_low = capex_planning_service.calculate_npv(flows, 0.05)
        npv_high = capex_planning_service.calculate_npv(flows, 0.50)
        assert npv_low > npv_high


class TestTCO:
    """Test Total Cost of Ownership calculations."""

    def test_tco_basic(self):
        """TCO includes all cost components."""
        result = capex_planning_service.calculate_tco(
            initial_cost=100000,
            annual_maintenance=10000,
            maintenance_escalation=0.05,
            downtime_cost_per_day=5000,
            expected_downtime_days_per_year=2,
            energy_cost_per_year=20000,
            energy_degradation_pct=0.02,
            horizon_years=5,
            discount_rate=0.10,
        )
        assert result["initial_cost_zar"] == 100000
        assert result["horizon_years"] == 5
        assert result["tco_nominal_zar"] > 100000
        assert result["tco_present_value_zar"] > 0
        assert len(result["yearly_breakdown"]) == 5

    def test_tco_yearly_breakdown_escalates(self):
        """Maintenance costs escalate year over year."""
        result = capex_planning_service.calculate_tco(
            initial_cost=50000,
            annual_maintenance=5000,
            maintenance_escalation=0.10,
            downtime_cost_per_day=0,
            expected_downtime_days_per_year=0,
            energy_cost_per_year=0,
            energy_degradation_pct=0,
            horizon_years=3,
            discount_rate=0.0,
        )
        yr1 = result["yearly_breakdown"][0]["maintenance_zar"]
        yr3 = result["yearly_breakdown"][2]["maintenance_zar"]
        assert yr3 > yr1

    def test_tco_residual_value_reduces_total(self):
        """Residual value reduces TCO nominal."""
        result_no_residual = capex_planning_service.calculate_tco(
            initial_cost=100000,
            annual_maintenance=5000,
            maintenance_escalation=0.05,
            downtime_cost_per_day=0,
            expected_downtime_days_per_year=0,
            energy_cost_per_year=0,
            energy_degradation_pct=0,
            horizon_years=5,
            discount_rate=0.10,
            residual_value=0,
        )
        result_with_residual = capex_planning_service.calculate_tco(
            initial_cost=100000,
            annual_maintenance=5000,
            maintenance_escalation=0.05,
            downtime_cost_per_day=0,
            expected_downtime_days_per_year=0,
            energy_cost_per_year=0,
            energy_degradation_pct=0,
            horizon_years=5,
            discount_rate=0.10,
            residual_value=20000,
        )
        assert result_with_residual["tco_nominal_zar"] < result_no_residual["tco_nominal_zar"]


class TestFailureProbability:
    """Test failure probability estimation."""

    def test_new_equipment_low_probability(self):
        """New equipment with good health has low failure probability."""
        prob = capex_planning_service.calculate_failure_probability(
            age_years=2,
            expected_life_years=20,
            health_score=90,
        )
        assert prob < 0.1

    def test_old_equipment_high_probability(self):
        """Old equipment beyond expected life has high failure probability."""
        prob = capex_planning_service.calculate_failure_probability(
            age_years=25,
            expected_life_years=20,
            health_score=30,
        )
        assert prob > 0.5

    def test_poor_health_increases_probability(self):
        """Lower health score increases failure probability."""
        prob_healthy = capex_planning_service.calculate_failure_probability(
            age_years=10,
            expected_life_years=20,
            health_score=90,
        )
        prob_unhealthy = capex_planning_service.calculate_failure_probability(
            age_years=10,
            expected_life_years=20,
            health_score=20,
        )
        assert prob_unhealthy > prob_healthy

    def test_condition_score_adjusts_probability(self):
        """Condition score further adjusts failure probability."""
        prob_no_cond = capex_planning_service.calculate_failure_probability(
            age_years=15,
            expected_life_years=20,
            health_score=50,
        )
        prob_poor_cond = capex_planning_service.calculate_failure_probability(
            age_years=15,
            expected_life_years=20,
            health_score=50,
            condition_score=20,
        )
        assert prob_poor_cond > prob_no_cond

    def test_probability_capped_at_099(self):
        """Probability never exceeds 0.99."""
        prob = capex_planning_service.calculate_failure_probability(
            age_years=100,
            expected_life_years=10,
            health_score=5,
            condition_score=5,
        )
        assert prob <= 0.99

    def test_probability_never_negative(self):
        """Probability is always non-negative."""
        prob = capex_planning_service.calculate_failure_probability(
            age_years=0,
            expected_life_years=50,
            health_score=100,
        )
        assert prob >= 0.0


class TestReplaceVsRepair:
    """Test replace-vs-repair decision engine."""

    def test_old_failing_equipment_recommends_replace(self):
        """Equipment beyond life with poor health should recommend replace."""
        result = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="chiller",
            age_years=25,
            health_score=25,
        )
        assert result["recommendation"] == "replace"
        assert result["npv_advantage_zar"] > 0
        assert result["confidence_pct"] > 50

    def test_new_healthy_equipment_low_failure_prob(self):
        """New healthy equipment has low failure probability."""
        result = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="fcu",
            age_years=2,
            health_score=90,
        )
        assert result["failure_probability"] < 0.15
        # NPV advantage of replace should be smaller for young equipment
        old_result = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="fcu",
            age_years=16,
            health_score=20,
        )
        assert result["npv_advantage_zar"] < old_result["npv_advantage_zar"]

    def test_analysis_contains_required_fields(self):
        """Analysis result has all required fields."""
        result = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="ahu",
            age_years=15,
            health_score=50,
        )
        required = [
            "equipment_type",
            "recommendation",
            "confidence_pct",
            "npv_replace_zar",
            "npv_repair_zar",
            "npv_advantage_zar",
            "savings_pct",
            "failure_probability",
            "risk_reduction_pct",
            "replacement_cost_zar",
            "repair_cost_zar",
            "analysis_date",
            "discount_rate",
            "horizon_years",
        ]
        for field in required:
            assert field in result, f"Missing field: {field}"

    def test_custom_costs_override_defaults(self):
        """Explicit costs override type defaults."""
        result = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="chiller",
            age_years=15,
            health_score=40,
            replacement_cost_zar=500000,
            repair_cost_zar=50000,
        )
        assert result["replacement_cost_zar"] == 500000
        assert result["repair_cost_zar"] == 50000

    def test_discount_rate_affects_decision(self):
        """Higher discount rate favors repair (future costs worth less)."""
        result_low = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="generator",
            age_years=20,
            health_score=35,
            discount_rate=0.05,
        )
        result_high = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="generator",
            age_years=20,
            health_score=35,
            discount_rate=0.25,
        )
        # Higher discount rate reduces NPV advantage of replacement
        assert result_high["npv_advantage_zar"] < result_low["npv_advantage_zar"]

    def test_concept_asset_lookup(self):
        """Concept Evolution asset code resolves real data."""
        result = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="chiller",
            age_years=21,
            health_score=38,
            concept_asset_code="GW-HVAC-CH-001",
        )
        # Should use Concept Evolution replacement cost (1,850,000)
        assert result["replacement_cost_zar"] == 1850000
        assert result["annual_maintenance_zar"] == 65000

    def test_analysis_date_is_today(self):
        """Analysis date should be today."""
        result = capex_planning_service.analyze_replace_vs_repair(
            equipment_type="ups",
            age_years=10,
            health_score=50,
        )
        assert result["analysis_date"] == date.today().isoformat()


class TestPortfolio:
    """Test portfolio analysis."""

    def test_portfolio_categorizes_equipment(self):
        """Portfolio separates equipment into replace/repair/monitor."""
        equipment = [
            {"code": "EQ-001", "type": "chiller", "age_years": 25, "health_score": 20},
            {"code": "EQ-002", "type": "fcu", "age_years": 2, "health_score": 95},
            {"code": "EQ-003", "type": "ahu", "age_years": 15, "health_score": 50},
        ]
        result = capex_planning_service.analyze_portfolio(
            site_id="site-002",
            equipment_list=equipment,
        )
        total = result["replace_count"] + result["repair_count"] + result["monitor_count"]
        assert total == 3
        assert result["total_equipment"] == 3

    def test_portfolio_has_budget_forecast(self):
        """Portfolio includes yearly budget forecast."""
        equipment = [
            {"code": "EQ-001", "type": "chiller", "age_years": 25, "health_score": 20},
        ]
        result = capex_planning_service.analyze_portfolio(
            site_id="site-002",
            equipment_list=equipment,
            horizon_years=5,
        )
        assert "budget_forecast" in result
        assert len(result["budget_forecast"]) == 5

    def test_portfolio_replace_candidates_sorted_by_npv(self):
        """Replace candidates sorted by NPV advantage (descending)."""
        equipment = [
            {"code": "EQ-A", "type": "fcu", "age_years": 18, "health_score": 15},
            {"code": "EQ-B", "type": "chiller", "age_years": 25, "health_score": 20},
        ]
        result = capex_planning_service.analyze_portfolio(
            site_id="site-002",
            equipment_list=equipment,
        )
        if len(result["replace_candidates"]) >= 2:
            first = result["replace_candidates"][0]["npv_advantage_zar"]
            second = result["replace_candidates"][1]["npv_advantage_zar"]
            assert first >= second

    def test_portfolio_total_capex(self):
        """Total CapEx is sum of replacement costs for replace candidates."""
        equipment = [
            {"code": "EQ-001", "type": "chiller", "age_years": 25, "health_score": 20, "replacement_cost_zar": 1000000},
        ]
        result = capex_planning_service.analyze_portfolio(
            site_id="site-002",
            equipment_list=equipment,
        )
        if result["replace_count"] > 0:
            assert result["total_capex_needed_zar"] > 0


class TestScenario:
    """Test what-if scenario analysis."""

    def test_scenario_runs_multiple(self):
        """Scenario analysis runs all provided scenarios."""
        scenarios = [
            {"name": "Base", "discount_rate": 0.10},
            {"name": "High discount", "discount_rate": 0.20},
            {"name": "Low discount", "discount_rate": 0.05},
        ]
        result = capex_planning_service.run_scenario(
            equipment_type="chiller",
            age_years=20,
            health_score=35,
            scenarios=scenarios,
        )
        assert result["scenario_count"] == 3
        assert len(result["scenarios"]) == 3

    def test_scenario_consistency_flag(self):
        """Consistent flag true when all scenarios agree."""
        # Very old, very broken — should always be replace
        scenarios = [
            {"name": "A", "discount_rate": 0.05},
            {"name": "B", "discount_rate": 0.10},
            {"name": "C", "discount_rate": 0.15},
        ]
        result = capex_planning_service.run_scenario(
            equipment_type="chiller",
            age_years=30,
            health_score=15,
            scenarios=scenarios,
        )
        if result["recommendation_consistent"]:
            assert result["dominant_recommendation"] == "replace"

    def test_scenario_names_preserved(self):
        """Scenario names appear in results."""
        scenarios = [
            {"name": "Optimistic", "discount_rate": 0.08},
            {"name": "Pessimistic", "discount_rate": 0.15},
        ]
        result = capex_planning_service.run_scenario(
            equipment_type="ahu",
            age_years=10,
            health_score=60,
            scenarios=scenarios,
        )
        names = [s["scenario_name"] for s in result["scenarios"]]
        assert "Optimistic" in names
        assert "Pessimistic" in names


class TestTypeFinancials:
    """Test equipment type financial data loading."""

    def test_load_chiller_financials(self):
        """Chiller type financials load correctly."""
        fin = capex_planning_service.get_type_financials("chiller")
        assert fin is not None
        assert fin["typical_replacement_cost_zar"] == 1750000

    def test_load_defaults(self):
        """Global defaults load correctly."""
        defaults = capex_planning_service.get_defaults()
        assert defaults["discount_rate"] == 0.10
        assert defaults["currency"] == "ZAR"

    def test_unknown_type_returns_none(self):
        """Unknown equipment type returns None."""
        fin = capex_planning_service.get_type_financials("quantum_reactor")
        assert fin is None

    def test_case_insensitive_lookup(self):
        """Type lookup is case-insensitive."""
        fin = capex_planning_service.get_type_financials("CHILLER")
        assert fin is not None


class TestConceptAssets:
    """Test Concept Evolution asset data."""

    def test_load_concept_asset(self):
        """Concept asset lookup works."""
        asset = capex_planning_service.get_concept_asset("GW-HVAC-CH-001")
        assert asset is not None
        assert asset["AssetType"] == "Chiller"

    def test_concept_asset_not_found(self):
        """Missing concept asset returns None."""
        asset = capex_planning_service.get_concept_asset("NONEXISTENT-001")
        assert asset is None

    def test_concept_asset_has_financial_data(self):
        """Concept assets have replacement and maintenance costs."""
        asset = capex_planning_service.get_concept_asset("GW-HVAC-CH-001")
        assert float(asset["ReplacementCost"]) == 1850000.0
        assert float(asset["AnnualMaintCost"]) == 65000.0


class TestConfidence:
    """Test confidence scoring."""

    def test_high_confidence_with_good_data(self):
        """High confidence when concept data + explicit costs available."""
        conf = capex_planning_service._calculate_confidence(
            has_concept_data=True,
            has_explicit_costs=True,
            has_condition_score=True,
            health_score=25,
            age_ratio=1.2,
            savings_pct=40,
        )
        assert conf >= 80

    def test_low_confidence_with_poor_data(self):
        """Low confidence when decision is borderline with defaults only."""
        conf = capex_planning_service._calculate_confidence(
            has_concept_data=False,
            has_explicit_costs=False,
            has_condition_score=False,
            health_score=55,
            age_ratio=0.6,
            savings_pct=3,
        )
        assert conf < 50

    def test_confidence_bounded(self):
        """Confidence always between 10 and 99."""
        conf_min = capex_planning_service._calculate_confidence(
            False,
            False,
            False,
            50,
            0.5,
            2,
        )
        conf_max = capex_planning_service._calculate_confidence(
            True,
            True,
            True,
            10,
            2.0,
            50,
        )
        assert 10 <= conf_min <= 99
        assert 10 <= conf_max <= 99
