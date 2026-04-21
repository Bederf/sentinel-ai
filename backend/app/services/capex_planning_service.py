"""CapEx Planning Service — replace-vs-repair decision engine (Phase 128).

Provides NPV, TCO, and replace-vs-repair analysis for equipment,
integrating health scores, RUL predictions, and maintenance cost history.
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Financial Defaults
# --------------------------------------------------------------------------- #
_FINANCIALS_PATH = Path(__file__).parent.parent / "data" / "equipment_type_financials.json"
_CONCEPT_CSV_PATH = Path(__file__).parent.parent / "data" / "concept_assets.csv"

_type_financials: dict[str, Any] = {}
_concept_assets: list[dict[str, Any]] = []


def _load_type_financials() -> dict[str, Any]:
    """Load equipment type financial defaults (cached after first call)."""
    global _type_financials
    if _type_financials:
        return _type_financials
    try:
        with open(_FINANCIALS_PATH) as f:
            _type_financials = json.load(f)
    except Exception:
        logger.warning("equipment_type_financials.json not found, using empty defaults")
        _type_financials = {
            "_defaults": {
                "discount_rate": 0.10,
                "inflation_rate": 0.06,
                "analysis_horizon_years": 10,
                "currency": "ZAR",
            }
        }
    return _type_financials


def _load_concept_assets() -> list[dict[str, Any]]:
    """Load Concept Evolution asset data from CSV."""
    global _concept_assets
    if _concept_assets:
        return _concept_assets
    import csv

    try:
        with open(_CONCEPT_CSV_PATH) as f:
            reader = csv.DictReader(f)
            _concept_assets = list(reader)
    except Exception:
        logger.warning("concept_assets.csv not found")
        _concept_assets = []
    return _concept_assets


def get_defaults() -> dict[str, Any]:
    """Return financial analysis defaults."""
    financials = _load_type_financials()
    return financials.get("_defaults", {})


def get_type_financials(equipment_type: str) -> dict[str, Any] | None:
    """Return financial profile for an equipment type (case-insensitive)."""
    financials = _load_type_financials()
    key = equipment_type.lower().replace(" ", "_")
    return financials.get(key)


def get_concept_asset(asset_code: str) -> dict[str, Any] | None:
    """Look up a Concept Evolution asset by code."""
    assets = _load_concept_assets()
    for a in assets:
        if a.get("AssetCode") == asset_code:
            return a
    return None


# --------------------------------------------------------------------------- #
# Core Financial Calculations
# --------------------------------------------------------------------------- #


def calculate_npv(
    cash_flows: list[float],
    discount_rate: float,
) -> float:
    """Calculate Net Present Value of a series of cash flows.

    Args:
        cash_flows: Year-indexed cash flows. Index 0 = today (not discounted).
        discount_rate: Annual discount rate (e.g. 0.10 for 10%).

    Returns:
        NPV in ZAR.
    """
    npv = 0.0
    for t, cf in enumerate(cash_flows):
        npv += cf / (1 + discount_rate) ** t
    return round(npv, 2)


def calculate_tco(
    initial_cost: float,
    annual_maintenance: float,
    maintenance_escalation: float,
    downtime_cost_per_day: float,
    expected_downtime_days_per_year: float,
    energy_cost_per_year: float,
    energy_degradation_pct: float,
    horizon_years: int,
    discount_rate: float,
    residual_value: float = 0.0,
) -> dict[str, Any]:
    """Calculate Total Cost of Ownership over a time horizon.

    Returns:
        Dict with tco_total, tco_present_value, yearly_breakdown.
    """
    yearly = []
    total_nominal = initial_cost
    cash_flows = [-initial_cost]

    for year in range(1, horizon_years + 1):
        maint = annual_maintenance * (1 + maintenance_escalation) ** (year - 1)
        downtime = downtime_cost_per_day * expected_downtime_days_per_year * (1.0 + 0.05 * (year - 1))
        energy = energy_cost_per_year * (1 + energy_degradation_pct) ** (year - 1)
        annual_total = maint + downtime + energy
        total_nominal += annual_total
        cash_flows.append(-annual_total)

        yearly.append(
            {
                "year": year,
                "maintenance_zar": round(maint, 2),
                "downtime_zar": round(downtime, 2),
                "energy_zar": round(energy, 2),
                "total_zar": round(annual_total, 2),
            }
        )

    # Residual value at end (positive cash flow)
    if residual_value > 0:
        cash_flows.append(residual_value)
        total_nominal -= residual_value

    pv = calculate_npv(cash_flows, discount_rate)

    return {
        "tco_nominal_zar": round(total_nominal, 2),
        "tco_present_value_zar": round(abs(pv), 2),
        "initial_cost_zar": round(initial_cost, 2),
        "residual_value_zar": round(residual_value, 2),
        "horizon_years": horizon_years,
        "yearly_breakdown": yearly,
    }


def calculate_failure_probability(
    age_years: float,
    expected_life_years: float,
    health_score: float,
    condition_score: float | None = None,
) -> float:
    """Estimate probability of failure in next year.

    Uses a Weibull-inspired curve adjusted by health/condition.

    Args:
        age_years: Current equipment age.
        expected_life_years: Design life.
        health_score: 0-100 health score (higher = healthier).
        condition_score: 0-100 condition score (optional, from inspections).

    Returns:
        Probability of failure in next year (0.0 to 1.0).
    """
    # Age ratio drives base probability (Weibull shape ~2.5)
    age_ratio = age_years / max(expected_life_years, 1)
    shape = 2.5
    base_prob = 1.0 - (2.718 ** (-(age_ratio**shape)))

    # Health adjustment: poor health increases probability
    health_factor = 1.0 + (1.0 - health_score / 100.0) * 0.5

    # Condition adjustment if available
    condition_factor = 1.0 + (1.0 - condition_score / 100.0) * 0.3 if condition_score is not None else 1.0

    prob = base_prob * health_factor * condition_factor
    return round(min(max(prob, 0.0), 0.99), 4)


# --------------------------------------------------------------------------- #
# Replace vs Repair Analysis
# --------------------------------------------------------------------------- #


def analyze_replace_vs_repair(
    equipment_type: str,
    age_years: float,
    health_score: float,
    replacement_cost_zar: float | None = None,
    repair_cost_zar: float | None = None,
    annual_maintenance_zar: float | None = None,
    condition_score: float | None = None,
    discount_rate: float | None = None,
    horizon_years: int | None = None,
    maintenance_escalation: float | None = None,
    concept_asset_code: str | None = None,
) -> dict[str, Any]:
    """Analyze replace-vs-repair decision for equipment.

    Calculates NPV for both options, recommends action with confidence.

    Args:
        equipment_type: Type (e.g. "chiller", "ahu").
        age_years: Current age in years.
        health_score: Current health score (0-100).
        replacement_cost_zar: Override replacement cost.
        repair_cost_zar: Override repair cost.
        annual_maintenance_zar: Override current annual maintenance.
        condition_score: Optional condition score from inspections.
        discount_rate: Override discount rate.
        horizon_years: Override analysis horizon.
        maintenance_escalation: Override maintenance cost escalation.
        concept_asset_code: Concept Evolution asset code for real data.

    Returns:
        Analysis result with recommendation, NPV comparison, confidence.
    """
    defaults = get_defaults()
    type_fin = get_type_financials(equipment_type) or {}

    # Resolve Concept Evolution data if available
    concept = get_concept_asset(concept_asset_code) if concept_asset_code else None

    # Resolve parameters with priority: explicit > concept > type defaults
    repl_cost = (
        replacement_cost_zar
        or _float(concept, "ReplacementCost")
        or type_fin.get("typical_replacement_cost_zar", 100000)
    )
    repr_cost = repair_cost_zar or type_fin.get("typical_repair_cost_zar", 20000)
    annual_maint = (
        annual_maintenance_zar
        or _float(concept, "AnnualMaintCost")
        or type_fin.get("annual_maintenance_new_zar", 10000)
    )
    expected_life = type_fin.get("expected_life_years", 15)
    residual_pct = type_fin.get("residual_value_pct", 0.10)
    maint_esc = maintenance_escalation or type_fin.get(
        "maintenance_escalation_pct", defaults.get("inflation_rate", 0.06)
    )
    disc_rate = discount_rate or defaults.get("discount_rate", 0.10)
    horizon = horizon_years or defaults.get("analysis_horizon_years", 10)
    new_maint = type_fin.get("annual_maintenance_new_zar", annual_maint * 0.4)
    downtime_per_day = type_fin.get("downtime_cost_per_day_zar", 10000)

    # Failure probability
    p_failure = calculate_failure_probability(age_years, expected_life, health_score, condition_score)

    # --- NPV(Replace) ---
    # Year 0: pay replacement cost
    # Years 1-N: new equipment maintenance (lower, starts fresh)
    # Year N: residual value
    residual_val = repl_cost * residual_pct
    replace_flows = [-repl_cost]
    for yr in range(1, horizon + 1):
        yr_maint = new_maint * (1 + maint_esc) ** (yr - 1)
        replace_flows.append(-yr_maint)
    replace_flows[-1] += residual_val  # Add residual to last year

    npv_replace = calculate_npv(replace_flows, disc_rate)

    # --- NPV(Repair) ---
    # Year 0: pay repair cost
    # Years 1-N: escalating old maintenance + risk of catastrophic failure
    repair_flows = [-repr_cost]

    for yr in range(1, horizon + 1):
        yr_maint = annual_maint * (1 + maint_esc) ** yr
        # Increasing failure risk adds expected catastrophic cost
        yr_age = age_years + yr
        degraded_health = max(health_score - yr * 3, 10)
        yr_p_fail = calculate_failure_probability(yr_age, expected_life, degraded_health, condition_score)
        expected_failure_cost = yr_p_fail * (repl_cost + downtime_per_day * 5)
        repair_flows.append(-(yr_maint + expected_failure_cost))

    npv_repair = calculate_npv(repair_flows, disc_rate)

    # --- Decision ---
    npv_advantage = npv_replace - npv_repair  # Positive = replace is better
    savings_pct = abs(npv_advantage) / max(abs(npv_repair), 1) * 100

    if npv_advantage > 0:
        recommendation = "replace"
    elif savings_pct < 5:
        recommendation = "monitor"
    else:
        recommendation = "repair"

    # Payback period (years until replace breaks even vs repair)
    payback_months = None
    if recommendation == "replace":
        cumulative_savings = 0.0
        for yr in range(1, horizon + 1):
            yr_repair_cost = abs(repair_flows[yr]) if yr < len(repair_flows) else 0
            yr_replace_cost = abs(replace_flows[yr]) if yr < len(replace_flows) else 0
            cumulative_savings += yr_repair_cost - yr_replace_cost
            if cumulative_savings >= (repl_cost - repr_cost):
                payback_months = yr * 12
                break

    # Confidence scoring
    confidence = _calculate_confidence(
        has_concept_data=concept is not None,
        has_explicit_costs=replacement_cost_zar is not None,
        has_condition_score=condition_score is not None,
        health_score=health_score,
        age_ratio=age_years / expected_life,
        savings_pct=savings_pct,
    )

    # Risk reduction if replaced
    risk_current = p_failure * (repl_cost + downtime_per_day * 5)
    risk_new = 0.02 * (repl_cost * 0.1)  # New equipment has ~2% failure probability, lower impact
    risk_reduction_pct = round((1 - risk_new / max(risk_current, 1)) * 100, 1)

    return {
        "equipment_type": equipment_type,
        "age_years": age_years,
        "health_score": health_score,
        "condition_score": condition_score,
        "recommendation": recommendation,
        "confidence_pct": confidence,
        "npv_replace_zar": round(npv_replace, 2),
        "npv_repair_zar": round(npv_repair, 2),
        "npv_advantage_zar": round(npv_advantage, 2),
        "savings_pct": round(savings_pct, 1),
        "payback_months": payback_months,
        "failure_probability": p_failure,
        "risk_reduction_pct": risk_reduction_pct,
        "replacement_cost_zar": round(repl_cost, 2),
        "repair_cost_zar": round(repr_cost, 2),
        "annual_maintenance_zar": round(annual_maint, 2),
        "discount_rate": disc_rate,
        "horizon_years": horizon,
        "analysis_date": date.today().isoformat(),
    }


def analyze_portfolio(
    site_id: str,
    equipment_list: list[dict[str, Any]],
    discount_rate: float | None = None,
    horizon_years: int | None = None,
) -> dict[str, Any]:
    """Analyze all equipment for a site, return prioritized CapEx plan.

    Args:
        site_id: Site identifier.
        equipment_list: List of equipment dicts with keys:
            code, type, age_years, health_score, condition_score (optional),
            replacement_cost_zar (optional), repair_cost_zar (optional),
            annual_maintenance_zar (optional).
        discount_rate: Override discount rate.
        horizon_years: Override analysis horizon.

    Returns:
        Portfolio analysis with prioritized replacement list and budget forecast.
    """
    analyses = []
    for eq in equipment_list:
        eq_type = (eq.get("type") or "unknown").lower()
        age = eq.get("age_years", 0)
        health = eq.get("health_score", 50)

        result = analyze_replace_vs_repair(
            equipment_type=eq_type,
            age_years=age,
            health_score=health,
            replacement_cost_zar=eq.get("replacement_cost_zar"),
            repair_cost_zar=eq.get("repair_cost_zar"),
            annual_maintenance_zar=eq.get("annual_maintenance_zar"),
            condition_score=eq.get("condition_score"),
            discount_rate=discount_rate,
            horizon_years=horizon_years,
            concept_asset_code=eq.get("concept_asset_code"),
        )
        result["equipment_code"] = eq.get("code", "unknown")
        result["equipment_name"] = eq.get("name", eq.get("code", "unknown"))
        analyses.append(result)

    # Sort by NPV advantage (biggest benefit first)
    replace_candidates = [a for a in analyses if a["recommendation"] == "replace"]
    replace_candidates.sort(key=lambda x: x["npv_advantage_zar"], reverse=True)

    monitor_candidates = [a for a in analyses if a["recommendation"] == "monitor"]
    repair_candidates = [a for a in analyses if a["recommendation"] == "repair"]

    # Budget forecast by year
    budget_forecast = _build_budget_forecast(replace_candidates, horizon_years or 10)

    total_capex_needed = sum(a["replacement_cost_zar"] for a in replace_candidates)
    total_npv_savings = sum(a["npv_advantage_zar"] for a in replace_candidates)

    return {
        "site_id": site_id,
        "analysis_date": date.today().isoformat(),
        "total_equipment": len(analyses),
        "replace_count": len(replace_candidates),
        "repair_count": len(repair_candidates),
        "monitor_count": len(monitor_candidates),
        "total_capex_needed_zar": round(total_capex_needed, 2),
        "total_npv_savings_zar": round(total_npv_savings, 2),
        "replace_candidates": replace_candidates,
        "repair_candidates": repair_candidates,
        "monitor_candidates": monitor_candidates,
        "budget_forecast": budget_forecast,
    }


def run_scenario(
    equipment_type: str,
    age_years: float,
    health_score: float,
    scenarios: list[dict[str, Any]],
    base_replacement_cost_zar: float | None = None,
    base_repair_cost_zar: float | None = None,
    base_annual_maintenance_zar: float | None = None,
    condition_score: float | None = None,
) -> dict[str, Any]:
    """Run what-if scenario analysis with multiple parameter sets.

    Args:
        equipment_type: Equipment type.
        age_years: Current age.
        health_score: Current health score.
        scenarios: List of scenario parameter overrides, each a dict with
            optional keys: name, discount_rate, horizon_years, maintenance_escalation,
            replacement_cost_zar, repair_cost_zar.
        base_*: Base cost parameters.
        condition_score: Optional condition score.

    Returns:
        Scenario comparison results.
    """
    results = []
    for scenario in scenarios:
        name = scenario.get("name", f"Scenario {len(results) + 1}")
        analysis = analyze_replace_vs_repair(
            equipment_type=equipment_type,
            age_years=age_years,
            health_score=health_score,
            replacement_cost_zar=scenario.get("replacement_cost_zar", base_replacement_cost_zar),
            repair_cost_zar=scenario.get("repair_cost_zar", base_repair_cost_zar),
            annual_maintenance_zar=scenario.get("annual_maintenance_zar", base_annual_maintenance_zar),
            condition_score=condition_score,
            discount_rate=scenario.get("discount_rate"),
            horizon_years=scenario.get("horizon_years"),
            maintenance_escalation=scenario.get("maintenance_escalation"),
        )
        analysis["scenario_name"] = name
        results.append(analysis)

    # Sensitivity summary
    recommendations = [r["recommendation"] for r in results]
    consistent = len(set(recommendations)) == 1

    return {
        "equipment_type": equipment_type,
        "age_years": age_years,
        "health_score": health_score,
        "scenario_count": len(results),
        "recommendation_consistent": consistent,
        "dominant_recommendation": max(set(recommendations), key=recommendations.count),
        "scenarios": results,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _float(record: dict | None, key: str) -> float | None:
    """Safely extract a float from a dict."""
    if not record:
        return None
    val = record.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _calculate_confidence(
    has_concept_data: bool,
    has_explicit_costs: bool,
    has_condition_score: bool,
    health_score: float,
    age_ratio: float,
    savings_pct: float,
) -> float:
    """Calculate confidence in the recommendation (0-100)."""
    confidence = 50.0  # Base

    # Data quality bonuses
    if has_concept_data:
        confidence += 15
    if has_explicit_costs:
        confidence += 10
    if has_condition_score:
        confidence += 5

    # Health score quality (extreme values are more certain)
    if health_score < 30 or health_score > 80:
        confidence += 10
    elif health_score < 40 or health_score > 70:
        confidence += 5

    # Age ratio (clear cases boost confidence)
    if age_ratio > 1.0:
        confidence += 10  # Beyond expected life
    elif age_ratio < 0.3:
        confidence += 5  # Clearly young

    # Decision margin (bigger gap = more confident)
    if savings_pct > 30:
        confidence += 10
    elif savings_pct > 15:
        confidence += 5
    elif savings_pct < 5:
        confidence -= 15  # Too close to call

    return round(min(max(confidence, 10), 99), 1)


def _build_budget_forecast(
    replace_candidates: list[dict[str, Any]],
    horizon_years: int,
) -> list[dict[str, Any]]:
    """Build year-by-year CapEx budget forecast based on urgency.

    Prioritizes by failure probability and NPV advantage.
    """
    forecast = []
    remaining = list(replace_candidates)

    for year in range(1, horizon_years + 1):
        year_items = []
        year_total = 0.0

        # Allocate equipment to years based on failure probability
        still_remaining = []
        for item in remaining:
            p_fail = item.get("failure_probability", 0)
            # High failure probability items go in year 1-2
            # Others spread across the horizon
            if p_fail > 0.5:
                urgency_year = 1
            elif p_fail > 0.3:
                urgency_year = 2
            else:
                spread = int(3 + (1 - p_fail) * (horizon_years - 3))
                urgency_year = min(spread, horizon_years)

            if urgency_year <= year:
                year_items.append(
                    {
                        "equipment_code": item["equipment_code"],
                        "replacement_cost_zar": item["replacement_cost_zar"],
                        "failure_probability": p_fail,
                    }
                )
                year_total += item["replacement_cost_zar"]
            else:
                still_remaining.append(item)

        remaining = still_remaining

        forecast.append(
            {
                "year": year,
                "capex_zar": round(year_total, 2),
                "equipment_count": len(year_items),
                "items": year_items,
            }
        )

    return forecast
