"""
Baseline Calculator — deterministic health baseline from service history.

For equipment with only commissioning_date available (no service records,
no runtime hours), uses age-only calculation.

Health = 100 - age_penalty
Age penalty tiers:
  0-2 years:   1.5%/year  (new equipment, minimal wear)
  2-5 years:   2.5%/year  (normal)
  5-10 years:  4%/year    (aging)
  10+ years:   5%/year    (old, higher risk)
Cap penalty at 40% (floor = 60)
"""

from datetime import datetime, date
from typing import Tuple


def _age_years(commissioning_date: date, reference_date: date | None = None) -> float:
    """Calculate age in years from commissioning_date to reference_date (default: now)."""
    ref = reference_date or datetime.utcnow().date()
    return max(0.0, (ref - commissioning_date).days / 365.25)


def _age_penalty_tier(age_years: float) -> float:
    """Calculate age penalty based on graduated tiers."""
    penalty = 0.0
    remaining = age_years

    # 0-2 years: 1.5%/year
    tier = min(remaining, 2.0)
    penalty += tier * 1.5
    remaining -= tier

    if remaining <= 0:
        return penalty

    # 2-5 years: 2.5%/year
    tier = min(remaining, 3.0)
    penalty += tier * 2.5
    remaining -= tier

    if remaining <= 0:
        return penalty

    # 5-10 years: 4%/year
    tier = min(remaining, 5.0)
    penalty += tier * 4.0
    remaining -= tier

    if remaining <= 0:
        return penalty

    # 10+ years: 5%/year
    penalty += remaining * 5.0

    return min(penalty, 40.0)


def _confidence_score(age_years: float) -> float:
    """Confidence in age-only baseline."""
    base = 0.35
    if age_years < 2:
        return base + 0.15   # new equipment = more predictable
    elif age_years < 5:
        return base + 0.05   # normal range
    elif age_years < 10:
        return base          # moderate variance
    else:
        return base - 0.05   # high variance in older equipment
    

def calculate_baseline_health(
    commissioning_date: date | str,
    equipment_type: str | None = None,
) -> tuple[float, float, str]:
    """
    Calculate baseline health from commissioning date alone.

    Args:
        commissioning_date: Date of installation/commissioning
        equipment_type: Equipment type (for logging, not currently weighted)

    Returns:
        Tuple of (health_score, confidence, age_description)
    """
    if isinstance(commissioning_date, str):
        commissioning_date = datetime.fromisoformat(commissioning_date).date()

    age = _age_years(commissioning_date)
    penalty = _age_penalty_tier(age)
    health_score = round(max(60.0, 100.0 - penalty), 1)
    confidence = round(_confidence_score(age), 2)

    if age < 1:
        desc = f"<1 year old"
    elif age < 2:
        desc = f"{age:.1f} years old"
    else:
        desc = f"{int(age)} years old"

    return health_score, confidence, desc
