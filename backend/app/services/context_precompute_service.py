"""Context Pre-Computation Service — Phase 1b.

Pre-computes waste opportunities before AI model analysis.
Runs deterministic rules — no LLM needed.

Rules:
  1. FCU post-occupancy waste (from FCUStateTracker)
  2. AHU overcapacity (occupancy < 20%, AHU > 70%)
  3. Free cooling opportunity (outdoor < indoor - 3°C)
  4. BESS idle during peak tariff

Integration: ContextPreComputeService is instantiated inside AIOptimizerService.
"""

from dataclasses import dataclass
from datetime import datetime

from app.services.fcu_state_tracker import FCUStateTracker, WasteOpportunity

logger = __import__("logging").getLogger(__name__)


@dataclass
class PreComputedContext:
    """Output of pre-computation — waste opportunities + metadata."""

    opportunities: list["WasteOpportunity"]
    computed_at: datetime
    active_profile: str


class ContextPreComputeService:
    """Pre-computes waste opportunities using deterministic rules.

    No LLM required — pure rule evaluation over current conditions.
    Designed to be swapped in as a dependency of AIOptimizerService.
    """

    def __init__(self, fcu_state_tracker: "FCUStateTracker") -> None:
        self.fcu_state_tracker = fcu_state_tracker

    async def compute(
        self,
        site_id: str,
        current_conditions: dict,
        active_profile: str,
        outdoor_temp: float | None,
        peak_tariff: float,
    ) -> PreComputedContext:
        """Run all waste detection rules against current conditions.

        Args:
            site_id: Site identifier (e.g. "site-002")
            current_conditions: Dict with keys:
                - ahu_states: list[dict] with items having 'equipment_id', 'capacity_pct'
                - building_occupancy_pct: float
                - bess_soc: float (0-100)
                - bess_dispatching: bool
                - indoor_avg_temp: float
            active_profile: Active optimization profile name
            outdoor_temp: Current outdoor temperature in °C
            peak_tariff: Peak energy tariff in R/kWh
        """
        opportunities: list[WasteOpportunity] = []

        # Rule 1: FCU post-occupancy waste
        opportunities.extend(self.fcu_state_tracker.get_waste_candidates())

        # Rule 2: AHU overcapacity
        ahu_waste = self._check_ahu_overcapacity(current_conditions)
        opportunities.extend(ahu_waste)

        # Rule 3: Free cooling opportunity
        if outdoor_temp is not None:
            free_cooling = self._check_free_cooling(current_conditions, outdoor_temp)
            opportunities.extend(free_cooling)

        # Rule 4: BESS idle during peak
        bess_waste = self._check_bess_dispatch(current_conditions, peak_tariff)
        opportunities.extend(bess_waste)

        return PreComputedContext(
            opportunities=opportunities,
            computed_at=datetime.utcnow(),
            active_profile=active_profile,
        )

    def _check_ahu_overcapacity(self, current_conditions: dict) -> list["WasteOpportunity"]:
        """AHU running >70% when building occupancy < 20%."""
        opportunities: list[WasteOpportunity] = []
        occupancy = current_conditions.get("building_occupancy_pct", 100)
        if occupancy > 20:
            return opportunities

        ahu_states = current_conditions.get("ahu_states", [])
        for ahu in ahu_states:
            capacity = ahu.get("capacity_pct", 0)
            if capacity <= 70:
                continue
            equipment_id = ahu.get("equipment_id", "UNKNOWN")
            # Rough estimate: excess capacity above 40% × 0.5kW per percent × 60 min
            excess_kw = (capacity - 40) * 0.5 * 0.01 * 60
            opportunities.append(
                WasteOpportunity(
                    equipment_id=equipment_id,
                    zone_id="",
                    opportunity_type="overcapacity",
                    minutes_elapsed=0,
                    confidence=0.90,
                    description=(f"Building {occupancy:.0f}% occupied, {equipment_id} at {capacity:.0f}% capacity"),
                    estimated_saving_kwh=round(excess_kw, 3),
                )
            )
        return opportunities

    def _check_free_cooling(self, current_conditions: dict, outdoor_temp: float) -> list["WasteOpportunity"]:
        """Outdoor temp < indoor avg - 3°C → free cooling available via economiser."""
        opportunities: list[WasteOpportunity] = []
        indoor = current_conditions.get("indoor_avg_temp")
        if indoor is None:
            return opportunities

        if outdoor_temp < indoor - 3.0:
            delta = indoor - outdoor_temp
            opportunities.append(
                WasteOpportunity(
                    equipment_id="AHU-1",
                    zone_id="building",
                    opportunity_type="free_cooling",
                    minutes_elapsed=0,
                    confidence=0.85,
                    description=(
                        f"Outdoor {outdoor_temp:.1f}°C, indoor avg {indoor:.1f}°C "
                        f"({delta:.1f}°C differential) — "
                        f"free cooling available via economiser"
                    ),
                )
            )
        return opportunities

    def _check_bess_dispatch(self, current_conditions: dict, peak_tariff: float) -> list["WasteOpportunity"]:
        """BESS idle during peak tariff with SOC > 20%."""
        opportunities: list[WasteOpportunity] = []
        bess_soc = current_conditions.get("bess_soc", 0)
        bess_dispatching = current_conditions.get("bess_dispatching", False)

        if bess_soc > 20 and not bess_dispatching:
            opportunities.append(
                WasteOpportunity(
                    equipment_id="BESS-1",
                    zone_id="site",
                    opportunity_type="bess_idle_peak",
                    minutes_elapsed=0,
                    confidence=0.95,
                    description=(
                        f"BESS idle during peak tariff (R{peak_tariff:.2f}/kWh), "
                        f"SOC {bess_soc:.0f}% — dispatch opportunity"
                    ),
                )
            )
        return opportunities

    def format_for_prompt(self, context: PreComputedContext) -> str:
        """Format waste opportunities as a text block for Layer 2 of the optimization prompt.

        Example output:
        WASTE OPPORTUNITIES DETECTED:
        ⚠️  S002-FCU-201: Zone-201 empty 18 min, FCU still running
            → Cost saving: switch off now (profile threshold: 5 min)
        ⚠️  AHU-1: Building 8% occupied, AHU at 80% capacity
            → Reduce to 40% — maintain comfort with lower energy draw
        """
        if not context.opportunities:
            return ""

        lines = ["WASTE OPPORTUNITIES DETECTED:"]
        for opp in context.opportunities:
            icon = "⚠️"
            lines.append(f"{icon}  {opp.equipment_id}: {opp.description}")
            if opp.estimated_saving_kwh is not None:
                lines.append(f"    → ~{opp.estimated_saving_kwh:.1f} kWh opportunity")
        return "\n".join(lines)
