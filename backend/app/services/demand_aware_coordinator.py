"""
Demand-Aware Coordinator - Cross-Module Peak Demand Management

Master orchestrator that coordinates active modules for peak demand shaving.
Runs independently every 5 minutes to:
1. Monitor current demand vs NMD limit
2. Query module registry to discover active modules at each site
3. Collect optimization options from each active module
4. Intelligently coordinate actions (NMD breach prevention > TOU arbitrage > comfort)
5. Route coordinated recommendations to approval workflow

Priority Hierarchy:
- CRITICAL: NMD breach prevention (expensive penalties)
- HIGH: TOU arbitrage (cost optimization, if solar active)
- MEDIUM: Comfort optimization (within comfort bounds)
"""

import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
import uuid

from app.services.module_registry_service import module_registry
from app.services.solar_demand_service import get_solar_demand_service
from app.services.solar_arbitrage_engine import get_solar_arbitrage_engine
from app.services.bess_dispatch_engine import get_bess_dispatch_engine
from app.services.ai_optimizer import get_ai_optimizer
from app.services.approval_service import get_approval_service
from app.models.module_registry import (
    ModuleType, RecommendationType, RecommendationPriority, AIRecommendation
)
from app.database.repositories.equipment_repository import get_equipment_repository
from app.database.repositories.alert_repository import get_alert_repository

logger = logging.getLogger(__name__)


class DemandAwareCoordinator:
    """
    Cross-module orchestrator for peak demand management.

    Module-agnostic: works with any combination of active modules.
    Discovers modules at runtime via module_registry.
    """

    def __init__(self):
        """Initialize coordinator."""
        self.demand_service = get_solar_demand_service()
        self.arbitrage_engine = get_solar_arbitrage_engine()
        self.bess_engine = get_bess_dispatch_engine()
        self.ai_optimizer = get_ai_optimizer()
        self.approval_service = get_approval_service()
        self.equipment_repo = get_equipment_repository()
        self.alert_repo = get_alert_repository()

    async def evaluate_current_state(self, site_id: str) -> Optional[Dict[str, Any]]:
        """
        Evaluate demand and module state, decide coordinator actions.

        Runs every 5 minutes to assess:
        1. Current demand vs NMD limit
        2. Which modules are active
        3. Available optimization options per module
        4. Urgency level (normal, warning, critical)

        Returns coordinated recommendation or None if no action needed.
        """
        try:
            # 1. Get current demand state (always available, module-agnostic)
            demand_status = self.demand_service.get_current_demand(site_id)
            if not demand_status:
                logger.debug(f"No demand data available for site {site_id}")
                return None

            current_demand_kw = demand_status.get("current_demand_kw", 0)
            nmd_limit_kva = demand_status.get("nmd_limit_kva", 6000)
            headroom_kw = nmd_limit_kva - current_demand_kw
            headroom_percent = (headroom_kw / nmd_limit_kva * 100) if nmd_limit_kva > 0 else 100
            demand_trend = demand_status.get("demand_trend", "stable")

            logger.info(
                f"Site {site_id}: Demand {current_demand_kw:.0f}kW, NMD {nmd_limit_kva:.0f}kVA, "
                f"Headroom {headroom_percent:.1f}%, Trend {demand_trend}"
            )

            # 2. Determine urgency level
            if headroom_percent < 5:
                urgency = "critical"
                priority = RecommendationPriority.CRITICAL
            elif headroom_percent < 15:
                urgency = "warning"
                priority = RecommendationPriority.HIGH
            elif headroom_percent < 25:
                urgency = "caution"
                priority = RecommendationPriority.MEDIUM
            else:
                urgency = "normal"
                priority = RecommendationPriority.LOW

            # 3. Get active modules at this site
            active_modules = module_registry.get_active_modules(site_id)
            active_module_types = [m.module_type for m in active_modules]

            logger.debug(f"Site {site_id}: Active modules: {[m.value for m in active_module_types]}")

            # 4. If only normal urgency and no solar/demand management, no action needed
            if urgency == "normal" and ModuleType.SOLAR not in active_module_types:
                logger.debug(f"Site {site_id}: Urgency {urgency}, no solar module - no coordinator action")
                return None

            # 5. Generate multi-module recommendation based on urgency
            if urgency == "critical" or urgency == "warning":
                return await self._generate_emergency_shaving(
                    site_id=site_id,
                    current_demand_kw=current_demand_kw,
                    nmd_limit_kva=nmd_limit_kva,
                    headroom_percent=headroom_percent,
                    active_module_types=active_module_types,
                    priority=priority
                )
            elif urgency == "caution":
                return await self._generate_preventive_shaving(
                    site_id=site_id,
                    current_demand_kw=current_demand_kw,
                    nmd_limit_kva=nmd_limit_kva,
                    headroom_percent=headroom_percent,
                    active_module_types=active_module_types,
                    priority=priority
                )
            else:
                # Normal mode: only TOU if solar active
                if ModuleType.SOLAR in active_module_types:
                    return await self._generate_tou_guidance(
                        site_id=site_id,
                        active_module_types=active_module_types
                    )

            return None

        except Exception as e:
            logger.error(f"Error in demand coordinator for site {site_id}: {e}", exc_info=True)
            return None

    async def _generate_emergency_shaving(
        self,
        site_id: str,
        current_demand_kw: float,
        nmd_limit_kva: float,
        headroom_percent: float,
        active_module_types: List[ModuleType],
        priority: RecommendationPriority
    ) -> Dict[str, Any]:
        """Generate emergency peak shaving recommendation."""
        logger.info(f"Site {site_id}: Generating EMERGENCY shaving (headroom {headroom_percent:.1f}%)")

        # Determine target reduction
        # Target: restore headroom to 20% = 1,200 kW
        target_headroom_percent = 20
        target_headroom_kw = nmd_limit_kva * (target_headroom_percent / 100)
        required_reduction_kw = current_demand_kw - target_headroom_kw

        logger.info(f"Site {site_id}: Required reduction {required_reduction_kw:.0f}kW")

        # Build context for AI optimizer
        ai_context = {
            "site_id": site_id,
            "current_demand_kw": current_demand_kw,
            "nmd_limit_kva": nmd_limit_kva,
            "nmd_headroom_percent": headroom_percent,
            "required_reduction_kw": required_reduction_kw,
            "urgency": "critical" if headroom_percent < 5 else "warning",
            "active_modules": [m.value for m in active_module_types],
            "available_actions": await self._get_available_actions(site_id, active_module_types)
        }

        # Call AI optimizer with demand context
        try:
            recommendations = await self.ai_optimizer.generate_recommendations(
                site_id=site_id,
                context=ai_context
            )
        except Exception as e:
            logger.warning(f"AI optimizer failed for {site_id}: {e}, using rule-based fallback")
            recommendations = self._generate_ruleb_ased_shaving(
                site_id=site_id,
                active_module_types=active_module_types,
                required_reduction_kw=required_reduction_kw
            )

        if not recommendations:
            logger.warning(f"No recommendations generated for site {site_id}")
            return None

        # Extract module actions from recommendations
        module_actions = recommendations.get("module_actions", [])
        total_reduction_kw = recommendations.get("total_reduction_kw", 0)
        total_savings_r = recommendations.get("total_savings_r", 0)

        # Create multi-module recommendation
        recommendation_id = f"coord-{uuid.uuid4().hex[:8]}"

        recommendation = {
            "recommendation_id": recommendation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "source_module": "coordinator",
            "type": "multi_system_shaving",
            "urgency": "critical" if headroom_percent < 5 else "warning",
            "priority": priority.value,
            "modules_involved": [a.get("module") for a in module_actions],
            "module_actions": module_actions,
            "estimated_reduction_kw": total_reduction_kw,
            "estimated_savings_r": total_savings_r,
            "reasoning": f"NMD headroom at {headroom_percent:.1f}% - emergency shaving required",
            "requires_approval": True
        }

        logger.info(
            f"Site {site_id}: Emergency shaving - "
            f"Modules: {recommendation['modules_involved']}, "
            f"Reduction: {total_reduction_kw:.0f}kW, "
            f"Savings: R{total_savings_r:.0f}"
        )

        return recommendation

    async def _generate_preventive_shaving(
        self,
        site_id: str,
        current_demand_kw: float,
        nmd_limit_kva: float,
        headroom_percent: float,
        active_module_types: List[ModuleType],
        priority: RecommendationPriority
    ) -> Dict[str, Any]:
        """Generate preventive peak shaving recommendation."""
        logger.info(f"Site {site_id}: Generating PREVENTIVE shaving (headroom {headroom_percent:.1f}%)")

        # Less aggressive: restore headroom to 25%
        target_headroom_percent = 25
        target_headroom_kw = nmd_limit_kva * (target_headroom_percent / 100)
        required_reduction_kw = current_demand_kw - target_headroom_kw

        ai_context = {
            "site_id": site_id,
            "current_demand_kw": current_demand_kw,
            "nmd_limit_kva": nmd_limit_kva,
            "nmd_headroom_percent": headroom_percent,
            "required_reduction_kw": required_reduction_kw,
            "urgency": "warning",
            "active_modules": [m.value for m in active_module_types],
            "available_actions": await self._get_available_actions(site_id, active_module_types)
        }

        try:
            recommendations = await self.ai_optimizer.generate_recommendations(
                site_id=site_id,
                context=ai_context
            )
        except Exception as e:
            logger.warning(f"AI optimizer failed for {site_id}: {e}, using rule-based fallback")
            recommendations = self._generate_ruleb_ased_shaving(
                site_id=site_id,
                active_module_types=active_module_types,
                required_reduction_kw=required_reduction_kw
            )

        if not recommendations:
            return None

        module_actions = recommendations.get("module_actions", [])
        total_reduction_kw = recommendations.get("total_reduction_kw", 0)
        total_savings_r = recommendations.get("total_savings_r", 0)

        recommendation_id = f"coord-{uuid.uuid4().hex[:8]}"

        recommendation = {
            "recommendation_id": recommendation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "source_module": "coordinator",
            "type": "multi_system_shaving",
            "urgency": "warning",
            "priority": priority.value,
            "modules_involved": [a.get("module") for a in module_actions],
            "module_actions": module_actions,
            "estimated_reduction_kw": total_reduction_kw,
            "estimated_savings_r": total_savings_r,
            "reasoning": f"NMD headroom at {headroom_percent:.1f}% - preventive shaving recommended",
            "requires_approval": True
        }

        logger.info(
            f"Site {site_id}: Preventive shaving - "
            f"Modules: {recommendation['modules_involved']}, "
            f"Reduction: {total_reduction_kw:.0f}kW"
        )

        return recommendation

    async def _generate_tou_guidance(
        self,
        site_id: str,
        active_module_types: List[ModuleType]
    ) -> Optional[Dict[str, Any]]:
        """Generate TOU arbitrage guidance (normal mode, only if solar active)."""
        if ModuleType.SOLAR not in active_module_types:
            return None

        logger.debug(f"Site {site_id}: Normal mode - generating TOU guidance")

        try:
            schedule = self.arbitrage_engine.generate_dispatch_schedule(site_id)
            if not schedule:
                return None

            return {
                "recommendation_id": f"tou-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.utcnow().isoformat(),
                "source_module": "coordinator",
                "type": "tou_guidance",
                "priority": RecommendationPriority.LOW.value,
                "module_actions": [
                    {
                        "module": "solar",
                        "action": "follow_tou_schedule",
                        "schedule": schedule.to_dict()
                    }
                ],
                "reasoning": "TOU tariff optimization"
            }
        except Exception as e:
            logger.debug(f"TOU guidance failed for {site_id}: {e}")
            return None

    async def _get_available_actions(
        self,
        site_id: str,
        active_module_types: List[ModuleType]
    ) -> Dict[str, List[str]]:
        """Get available optimization actions per module."""
        available = {}

        # Solar module
        if ModuleType.SOLAR in active_module_types:
            try:
                available["solar"] = [
                    "bess_discharge_100kw",
                    "bess_discharge_150kw",
                    "bess_discharge_200kw",
                    "bess_discharge_250kw"
                ]
            except Exception as e:
                logger.warning(f"Error getting solar actions for {site_id}: {e}")

        # HVAC module
        if ModuleType.HVAC in active_module_types:
            available["hvac"] = [
                "increase_setpoint_1c",
                "increase_setpoint_2c",
                "increase_setpoint_3c",
                "increase_chiller_supply_temp"
            ]

        # Energy module
        if ModuleType.ENERGY in active_module_types:
            available["energy"] = [
                "defer_pump_30min",
                "reduce_lift_30min",
                "reduce_compressor_50pct"
            ]

        # Lighting module
        if ModuleType.LIGHTING in active_module_types:
            available["lighting"] = [
                "dim_to_80pct",
                "dim_to_60pct",
                "reduce_outdoor_lighting_50pct"
            ]

        return available

    def _generate_ruleb_ased_shaving(
        self,
        site_id: str,
        active_module_types: List[ModuleType],
        required_reduction_kw: float
    ) -> Dict[str, Any]:
        """Generate rule-based shaving when AI is unavailable."""
        logger.info(f"Using rule-based shaving for {site_id} (required: {required_reduction_kw:.0f}kW)")

        module_actions = []
        total_reduction_kw = 0

        # Priority 1: BESS discharge (immediate, most reliable)
        if ModuleType.SOLAR in active_module_types and required_reduction_kw > total_reduction_kw:
            remaining = required_reduction_kw - total_reduction_kw
            discharge_kw = min(200, max(100, remaining))  # 100-200kW range
            module_actions.append({
                "module": "solar",
                "action": f"bess_discharge_{int(discharge_kw)}kw",
                "duration_min": 60,
                "reduction_kw": discharge_kw
            })
            total_reduction_kw += discharge_kw

        # Priority 2: HVAC setpoint (comfort tolerance 2-3°C)
        if ModuleType.HVAC in active_module_types and required_reduction_kw > total_reduction_kw:
            remaining = required_reduction_kw - total_reduction_kw
            setpoint_increase = 2 if remaining > 50 else 1
            module_actions.append({
                "module": "hvac",
                "action": f"increase_setpoint_{setpoint_increase}c",
                "reduction_kw": 30 * setpoint_increase  # ~30kW per °C
            })
            total_reduction_kw += 30 * setpoint_increase

        # Priority 3: Load deferral (non-critical equipment)
        if ModuleType.ENERGY in active_module_types and required_reduction_kw > total_reduction_kw:
            remaining = required_reduction_kw - total_reduction_kw
            if remaining > 30:
                module_actions.append({
                    "module": "energy",
                    "action": "defer_pump_30min",
                    "reduction_kw": 25
                })
                total_reduction_kw += 25

        return {
            "module_actions": module_actions,
            "total_reduction_kw": total_reduction_kw,
            "total_savings_r": 0  # Rule-based, no financial context
        }


# Singleton instance
_demand_aware_coordinator: Optional[DemandAwareCoordinator] = None


def get_demand_aware_coordinator() -> DemandAwareCoordinator:
    """Get or create singleton coordinator."""
    global _demand_aware_coordinator
    if _demand_aware_coordinator is None:
        _demand_aware_coordinator = DemandAwareCoordinator()
    return _demand_aware_coordinator
