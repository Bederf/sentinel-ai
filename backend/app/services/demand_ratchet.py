"""
Demand Ratchet Service — Rolling multi-month demand billing calculator.

City Power bills the higher of:
  (a) actual measured demand in the current month, or
  (b) highest demand recorded in the previous 11 months (the "ratchet")

This means a single demand spike can inflate the billing demand for up to 12 months.
BESS peak shaving targets should defend below the ratchet threshold to avoid resetting it.

Exposes: billing_demand_kva, spike_cost, shaving_target_kva, ratchet_history.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from app.services.solar_config_service import get_site_solar_config

logger = logging.getLogger(__name__)

# Number of months the ratchet looks back (standard SA municipal billing)
RATCHET_WINDOW_MONTHS = 12


@dataclass
class MonthlyDemandRecord:
    """Single month's peak demand record."""

    year: int
    month: int
    peak_demand_kva: float
    timestamp: Optional[str] = None


@dataclass
class RatchetResult:
    """Result of demand ratchet calculation."""

    site_id: str
    current_month_peak_kva: float
    ratchet_demand_kva: float  # highest of trailing 11 months
    billing_demand_kva: float  # max(current, ratchet)
    ratchet_active: bool  # True if billing > current (ratchet is lifting the bill)
    demand_charge_r_kva: float
    monthly_demand_cost_r: float  # billing_demand_kva × demand_charge
    spike_cost_r: float  # additional cost above defended threshold
    shaving_target_kva: float  # target to stay under ratchet
    headroom_kva: float  # how far current peak is from shaving target
    ratchet_history: List[MonthlyDemandRecord] = field(default_factory=list)
    ratchet_expires: Optional[str] = None  # when the highest ratchet month drops off


class DemandRatchetService:
    """Calculates billing demand with ratchet and recommends shaving targets."""

    def __init__(self):
        self._demand_history: Dict[str, List[MonthlyDemandRecord]] = {}

    def _get_demo_history(self, site_id: str) -> List[MonthlyDemandRecord]:
        """Generate realistic demo demand history for site-002."""
        # Realistic monthly peaks for a Sandton office tower (kVA)
        # Summer months higher (cooling load), winter months moderate
        records = []
        monthly_peaks = [
            (2025, 3, 1620),  # Mar — late summer
            (2025, 4, 1540),  # Apr — autumn
            (2025, 5, 1480),  # May — cool
            (2025, 6, 1510),  # Jun — winter peak (heating)
            (2025, 7, 1560),  # Jul — mid-winter
            (2025, 8, 1530),  # Aug — late winter
            (2025, 9, 1580),  # Sep — spring
            (2025, 10, 1650),  # Oct — warming up
            (2025, 11, 1720),  # Nov — early summer
            (2025, 12, 1780),  # Dec — peak summer
            (2026, 1, 1850),  # Jan — peak summer (highest)
            (2026, 2, 1760),  # Feb — late summer
        ]
        for year, month, peak in monthly_peaks:
            records.append(
                MonthlyDemandRecord(
                    year=year,
                    month=month,
                    peak_demand_kva=float(peak),
                    timestamp=f"{year}-{month:02d}-15T14:30:00Z",
                )
            )
        return records

    def get_demand_history(self, site_id: str) -> List[MonthlyDemandRecord]:
        """Get demand history for a site. Falls back to demo data."""
        if site_id not in self._demand_history:
            # In production, this would query Supabase billing_demand table
            self._demand_history[site_id] = self._get_demo_history(site_id)
        return self._demand_history[site_id]

    def calculate_ratchet(
        self,
        site_id: str,
        current_month_peak_kva: Optional[float] = None,
    ) -> RatchetResult:
        """
        Calculate billing demand with ratchet for current month.

        Args:
            site_id: Site identifier
            current_month_peak_kva: Override current month peak (for simulation).
                                    If None, uses latest from history.
        """
        cfg = get_site_solar_config(site_id)
        demand_charge = cfg.tariff.demand_charge_r_kva()

        history = self.get_demand_history(site_id)
        if not history:
            # No history — use current or NMD as baseline
            current = current_month_peak_kva or cfg.grid.nmd_limit_kva * 0.85
            return RatchetResult(
                site_id=site_id,
                current_month_peak_kva=current,
                ratchet_demand_kva=0.0,
                billing_demand_kva=current,
                ratchet_active=False,
                demand_charge_r_kva=demand_charge,
                monthly_demand_cost_r=round(current * demand_charge, 2),
                spike_cost_r=0.0,
                shaving_target_kva=current,
                headroom_kva=0.0,
            )

        now = datetime.now()
        current_year, current_month = now.year, now.month

        # Split history: current month vs trailing months
        trailing = []
        latest_current = 0.0
        for rec in history:
            if rec.year == current_year and rec.month == current_month:
                latest_current = max(latest_current, rec.peak_demand_kva)
            else:
                trailing.append(rec)

        if current_month_peak_kva is not None:
            latest_current = max(latest_current, current_month_peak_kva)

        # Take only last 11 months of trailing data
        trailing.sort(key=lambda r: (r.year, r.month), reverse=True)
        trailing = trailing[: RATCHET_WINDOW_MONTHS - 1]

        # Ratchet = max of trailing months
        ratchet_kva = max((r.peak_demand_kva for r in trailing), default=0.0)

        # Billing demand = max(current, ratchet)
        billing_kva = max(latest_current, ratchet_kva)

        # Find when the ratchet-setting month expires
        ratchet_expires = None
        if trailing and ratchet_kva > 0:
            ratchet_month = max(
                (r for r in trailing if r.peak_demand_kva == ratchet_kva),
                key=lambda r: (r.year, r.month),
            )
            # Expires 12 months after the ratchet-setting month
            exp_month = ratchet_month.month + 12
            exp_year = ratchet_month.year + (exp_month - 1) // 12
            exp_month = ((exp_month - 1) % 12) + 1
            ratchet_expires = f"{exp_year}-{exp_month:02d}"

        # Shaving target: stay at or below ratchet to avoid resetting it higher
        # If no ratchet, target 85% of NMD
        shaving_target = ratchet_kva if ratchet_kva > 0 else cfg.grid.nmd_limit_kva * 0.85
        headroom = shaving_target - latest_current

        # Spike cost: additional demand charge from exceeding the shaving target
        spike_cost = 0.0
        if latest_current > shaving_target:
            spike_cost = (latest_current - shaving_target) * demand_charge

        monthly_cost = round(billing_kva * demand_charge, 2)

        return RatchetResult(
            site_id=site_id,
            current_month_peak_kva=round(latest_current, 1),
            ratchet_demand_kva=round(ratchet_kva, 1),
            billing_demand_kva=round(billing_kva, 1),
            ratchet_active=ratchet_kva > latest_current,
            demand_charge_r_kva=demand_charge,
            monthly_demand_cost_r=monthly_cost,
            spike_cost_r=round(spike_cost, 2),
            shaving_target_kva=round(shaving_target, 1),
            headroom_kva=round(headroom, 1),
            ratchet_history=list(reversed(trailing)),
            ratchet_expires=ratchet_expires,
        )

    def update_current_peak(self, site_id: str, peak_kva: float):
        """Update current month's peak (called from real-time metering)."""
        now = datetime.now()
        history = self.get_demand_history(site_id)

        # Find or create current month record
        for rec in history:
            if rec.year == now.year and rec.month == now.month:
                if peak_kva > rec.peak_demand_kva:
                    rec.peak_demand_kva = peak_kva
                    rec.timestamp = now.isoformat()
                return

        # New month — add record
        history.append(
            MonthlyDemandRecord(
                year=now.year,
                month=now.month,
                peak_demand_kva=peak_kva,
                timestamp=now.isoformat(),
            )
        )


# Singleton
_demand_ratchet_service: Optional[DemandRatchetService] = None


def get_demand_ratchet_service() -> DemandRatchetService:
    """Get or create the demand ratchet service singleton."""
    global _demand_ratchet_service
    if _demand_ratchet_service is None:
        _demand_ratchet_service = DemandRatchetService()
    return _demand_ratchet_service
