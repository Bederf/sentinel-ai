"""AI Optimizer Service for building-wide optimization.

Uses Claude AI to analyze building telemetry, weather forecasts, and energy
pricing to generate optimal setpoint recommendations for ALL equipment types:
- HVAC (chillers, AHUs, FCUs, VAVs)
- Lighting (DALI-2 luminaires, zone control)
- Power (generators, UPS, ATS, meters)
- Solar PV (inverters, generation monitoring)
- BESS (battery dispatch, SOC management)
- Security (access control integration)
- Fire Safety (monitoring only)

Equipment inventory is site-specific - different buildings have different
equipment combinations.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


from app.models.optimization import (
    OptimizationRecommendation,
    SiteOptimizationStatus,
)
from app.models.device import Device, DeviceType, DevicePoint, ZoneType, ExposureDirection
from app.services.claude_service import claude_service
from app.services.device_abstraction import device_manager
from app.services.safety_interlocks import safety_engine
from app.services.dali_service import get_dali_service

logger = logging.getLogger(__name__)

# Data directory for sites
DATA_DIR = Path(__file__).parent.parent / "data"


async def ensure_device_manager_initialized() -> None:
    """Ensure device manager is initialized with mock + building devices if not already."""
    if not device_manager._initialized:
        logger.info("Device manager not initialized, loading devices...")
        try:
            # Load mock devices
            devices_data = []
            mock_devices_path = DATA_DIR / "mock_devices.json"
            if mock_devices_path.exists():
                with open(mock_devices_path) as f:
                    devices_data = json.load(f)
            mock_count = len(devices_data)

            # Load all building equipment (including monitoring-only solar/meters)
            from app.api.devices import load_equipment_from_buildings

            building_devices = await load_equipment_from_buildings()

            # Merge building devices with mock devices (dedup by ID)
            existing_ids = {d["id"] for d in devices_data}
            added_count = 0
            for device in building_devices:
                if device["id"] not in existing_ids:
                    devices_data.append(device)
                    existing_ids.add(device["id"])
                    added_count += 1

            await device_manager.initialize(devices_data)
            logger.info(
                f"Device manager initialized with {mock_count} mock + "
                f"{added_count} building = {len(devices_data)} total devices"
            )
        except Exception as e:
            logger.error(f"Failed to initialize device manager: {e}")
            await device_manager.initialize([])


def load_sites() -> List[Dict[str, Any]]:
    """Load sites data from Supabase, with fallback to JSON file."""
    from app.config.settings import settings

    # Try Supabase first
    if not settings.use_json_storage:
        try:
            from app.database.repositories.building_repository import BuildingRepository

            repo = BuildingRepository()
            buildings = repo.get_all()
            if buildings:
                sites = []
                for b in buildings:
                    site = {
                        "id": b.get("code") or b.get("id"),
                        "name": b.get("name"),
                        "type": b.get("type", "commercial"),
                        "sqm": b.get("sqm", 5000),
                        "floors": b.get("floors", 1),
                        "region": b.get("region", "Unknown"),
                        "operating_hours": b.get("operating_hours", {"start": "08:00", "end": "18:00"}),
                        "occupancy_pattern": b.get("occupancy_pattern", "office"),
                        "optimization_enabled": b.get("optimization_enabled", False),
                        "optimization_status": b.get("optimization_status", "unknown"),
                        "optimization_settings": b.get("optimization_settings"),
                        "last_recommendation": b.get("last_recommendation"),
                        "last_optimization": b.get("last_optimization"),
                        "optimization_history": b.get("optimization_history", []),
                        "error_message": b.get("error_message"),
                        "_uuid": b.get("id"),
                    }
                    sites.append(site)
                return sites
        except Exception as e:
            logger.warning(f"Failed to load sites from Supabase: {e}")

    # Fallback to JSON file
    filepath = DATA_DIR / "sites.json"
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


class AIOptimizerService:
    """Service for AI-powered building optimization."""

    def __init__(self):
        """Initialize AI optimizer service."""
        self._claude_service = claude_service
        self._sites = None
        self._optimization_status_cache: Dict[str, SiteOptimizationStatus] = {}

    @property
    def sites(self) -> List[Dict[str, Any]]:
        """Lazy load sites data."""
        if self._sites is None:
            self._sites = load_sites()
        return self._sites

    def find_site(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Find a site by ID."""
        for site in self.sites:
            if site["id"] == site_id:
                return site
        return None

    async def analyze_building(
        self,
        site_id: str,
        current_conditions: Optional[Dict[str, Any]] = None,
        weather_forecast: Optional[Dict[str, Any]] = None,
        energy_prices: Optional[Dict[str, Any]] = None,
    ) -> OptimizationRecommendation:
        """
        Analyze building conditions and generate optimization recommendations.

        Args:
            site_id: Site to analyze
            current_conditions: Current building conditions (will fetch if not provided)
            weather_forecast: Weather forecast for next 4 hours (will mock if not provided)
            energy_prices: Energy pricing (time-of-use rates) (will mock if not provided)

        Returns:
            OptimizationRecommendation with setpoints and projected savings
        """
        site = self.find_site(site_id)
        if not site:
            raise ValueError(f"Site {site_id} not found")

        # Ensure device manager is initialized
        await ensure_device_manager_initialized()

        # Gather current conditions if not provided
        if not current_conditions:
            current_conditions = await self._gather_current_conditions(site_id)

        # Generate mock weather forecast if not provided
        if not weather_forecast:
            weather_forecast = self._generate_mock_weather_forecast()

        # Generate mock energy prices if not provided
        if not energy_prices:
            energy_prices = self._generate_mock_energy_prices()

        # Get ALL site devices - equipment inventory varies by building
        all_devices = await device_manager.list_devices_by_site(site_id)

        # Categorize equipment by type - this is site-specific
        equipment_inventory = self._categorize_equipment(all_devices)

        logger.info(f"Site {site_id} equipment inventory: {self._summarize_inventory(equipment_inventory)}")

        # Fetch DALI lighting zone data
        dali_service = get_dali_service()
        dali_zones = self._gather_dali_zone_data(dali_service, site_id)

        # Load active profile for this site
        profile = None
        try:
            from app.services.profile_service import get_profile_service

            profile_service = get_profile_service()
            profile = profile_service.get_site_profile(site_id)
            if profile:
                logger.info(f"Using optimization profile: {profile.get('name', 'Unknown')} for site {site_id}")
            else:
                logger.warning(f"No optimization profile found for site {site_id}, using defaults")
        except Exception as e:
            logger.warning(f"Failed to load profile for site {site_id}: {e}")

        # Build optimization prompt for Claude with ALL available equipment
        prompt = self._build_optimization_prompt(
            site, current_conditions, weather_forecast, energy_prices, equipment_inventory, dali_zones, profile=profile
        )

        try:
            # Try to use Claude for analysis
            if self._claude_service.is_configured():
                recommendation = await self._analyze_with_claude(
                    site_id, prompt, current_conditions, equipment_inventory, dali_zones, profile
                )
            else:
                # Fall back to rule-based optimization
                recommendation = self._analyze_with_rules(
                    site_id,
                    current_conditions,
                    weather_forecast,
                    energy_prices,
                    equipment_inventory,
                    dali_zones,
                    profile,
                )

            # Apply recommendation scoring and ranking with profile weights
            if profile:
                recommendation = self._score_and_rank_recommendations(recommendation, profile)

            # Phase 109: Apply quality gate evaluation to recommendations
            recommendation = await self._apply_quality_gate(site_id, recommendation)

            # Phase 109B-03: Enrich recommendations with health features (ADDITIVE)
            recommendation = await self._enrich_with_health_features(recommendation)

            return recommendation

        except Exception as e:
            logger.error(f"Error analyzing building {site_id}: {e}")
            # Fall back to rule-based optimization
            rec = self._analyze_with_rules(
                site_id, current_conditions, weather_forecast, energy_prices, equipment_inventory, dali_zones, profile
            )
            # Apply scoring to fallback recommendations too
            if profile:
                rec = self._score_and_rank_recommendations(rec, profile)
            # Phase 109: Apply quality gate to fallback recommendations too
            rec = await self._apply_quality_gate(site_id, rec)
            # Phase 109B-03: Enrich fallback recommendations with health features too
            rec = await self._enrich_with_health_features(rec)
            return rec

    async def _apply_quality_gate(
        self, site_id: str, recommendation: "OptimizationRecommendation"
    ) -> "OptimizationRecommendation":
        """Apply quality gate evaluation to an OptimizationRecommendation.

        Evaluates all 14 quality metrics and applies enforcement actions
        to each recommendation dict in the response.

        Args:
            site_id: Site identifier
            recommendation: OptimizationRecommendation to evaluate

        Returns:
            Modified OptimizationRecommendation with gate metadata
        """
        try:
            from app.services.quality_gate_evaluator import QualityGateEvaluator
            from app.config.settings import settings as app_settings

            evaluator = QualityGateEvaluator()
            mode = app_settings.resolved_ingestion_mode.value
            metrics = await evaluator.collect_metrics(site_id)
            result = evaluator.evaluate(mode, metrics)

            # Apply enforcement to each recommendation dict
            for rec_dict in recommendation.recommendations:
                evaluator.apply_enforcement(result, rec_dict)

            # Set top-level quality gate metadata
            recommendation.quality_gate_status = result.overall.value
            recommendation.quality_gate_enforcement = result.enforcement.value
            recommendation.quality_gate_reason_codes = [rc.value for rc in result.reason_codes]

            logger.info(
                f"Quality gate for {site_id}: status={result.overall.value}, "
                f"enforcement={result.enforcement.value}, "
                f"failed={result.failed_rules}"
            )
        except Exception as e:
            logger.warning(f"Quality gate evaluation failed for {site_id}, proceeding without gate: {e}")

        return recommendation

    async def _enrich_with_health_features(
        self, recommendation: "OptimizationRecommendation"
    ) -> "OptimizationRecommendation":
        """Enrich recommendations with health feature payloads.

        Phase 109B-03: For each recommendation that has an equipment_id,
        retrieves the health feature payload and attaches it as a SEPARATE
        dict — never merged into risk/confidence fields.

        HARD RULES:
          - health_features is ADDITIVE — does not modify existing fields
          - health_features dict NEVER contains risk probabilities
          - health_severity_signal is derived from health_score, not risk
          - Existing confidence (risk-based) is preserved as-is

        Args:
            recommendation: OptimizationRecommendation to enrich.

        Returns:
            Modified OptimizationRecommendation with health features added.
        """
        try:
            from app.services.health_feature_provider import HealthFeatureProvider

            provider = HealthFeatureProvider()

            for rec_dict in recommendation.recommendations:
                equipment_id = rec_dict.get("equipment_id") or rec_dict.get("device_id")
                if not equipment_id:
                    continue

                try:
                    payload = await provider.get_health_features(equipment_id)

                    # Add health features as a SEPARATE dict (never merged with risk)
                    rec_dict["health_features"] = payload.model_dump()

                    # Add health severity signal for ranking (0 = healthy, 1 = critical)
                    rec_dict["health_severity_signal"] = round(1 - (payload.health_score_current / 100), 4)

                except Exception as e:
                    logger.debug(f"Could not get health features for {equipment_id}: {e}")

        except Exception as e:
            logger.warning(f"Health feature enrichment failed, proceeding without: {e}")

        return recommendation

    async def _gather_current_conditions(self, site_id: str) -> Dict[str, Any]:
        """Gather current building conditions from devices and DALI sensors."""
        try:
            devices = await device_manager.list_devices_by_site(site_id)

            conditions = {
                "indoor_temp": 22.0,
                "outdoor_temp": 28.0,
                "humidity": 55.0,
                "occupancy": "high",
                "equipment_status": "normal",
                "timestamp": datetime.now().isoformat(),
                "zone_occupancy": {},  # Real occupancy from DALI
                # Track which readings are defaults vs live sensor data
                "_data_sources": {
                    "indoor_temp": "default",
                    "outdoor_temp": "default",
                    "humidity": "default",
                    "occupancy": "default",
                    "solar": "unavailable",
                    "bess": "unavailable",
                    "dali": "unavailable",
                },
            }

            # Try to get actual readings from HVAC devices
            found_indoor_temp = False
            found_outdoor_temp = False
            found_humidity = False

            for device in devices:
                if device.device_type != DeviceType.HVAC:
                    continue

                for point_name in device.points:
                    point_name_lower = point_name.lower()

                    # Ignore writable targets; we only want sensor values.
                    if "setpoint" in point_name_lower or point_name_lower.endswith("_sp"):
                        continue

                    target_key: Optional[str] = None

                    if not found_humidity and (
                        "humidity" in point_name_lower or point_name_lower.endswith("_rh") or point_name_lower == "rh"
                    ):
                        target_key = "humidity"
                    elif not found_outdoor_temp and any(
                        token in point_name_lower
                        for token in (
                            "outdoor_temp",
                            "outside_temp",
                            "ambient_temp",
                            "outside_air_temp",
                            "outdoor_air_temp",
                            "oa_temp",
                        )
                    ):
                        target_key = "outdoor_temp"
                    elif not found_indoor_temp and "temp" in point_name_lower:
                        if any(
                            token in point_name_lower
                            for token in (
                                "outdoor",
                                "outside",
                                "ambient",
                                "supply",
                                "chw",
                                "coil",
                                "leaving",
                                "entering",
                            )
                        ):
                            continue
                        target_key = "indoor_temp"

                    if not target_key:
                        continue

                    try:
                        value = await device_manager.read_device_value(device.id, point_name)
                        if value and isinstance(value.value, (int, float)):
                            conditions[target_key] = float(value.value)
                            conditions["_data_sources"][target_key] = "live"

                            if target_key == "indoor_temp":
                                found_indoor_temp = True
                            elif target_key == "outdoor_temp":
                                found_outdoor_temp = True
                            elif target_key == "humidity":
                                found_humidity = True
                    except Exception:
                        pass

                    if found_indoor_temp and found_outdoor_temp and found_humidity:
                        break

                if found_indoor_temp and found_outdoor_temp and found_humidity:
                    break

            # Get real occupancy data from DALI service
            try:
                dali_service = get_dali_service()
                zones = dali_service.get_all_zones()

                total_occupied = 0
                total_zones = 0

                for zone in zones:
                    zone_id = zone.get("zone_id")
                    if not zone_id:
                        continue

                    occupancy = dali_service.get_zone_occupancy(zone_id)
                    if occupancy:
                        total_zones += 1
                        occ_pct = occupancy.occupancy_percent

                        conditions["zone_occupancy"][zone_id] = {
                            "occupancy_percent": occ_pct,
                            "avg_lux": occupancy.avg_lux_level,
                            "is_occupied": occ_pct > 10,
                            "zone_name": occupancy.zone_name,
                        }

                        if occ_pct > 10:
                            total_occupied += 1

                # Calculate overall occupancy level from zone data
                if total_zones > 0:
                    conditions["_data_sources"]["occupancy"] = "live"
                    conditions["_data_sources"]["dali"] = "live"
                    occupancy_ratio = total_occupied / total_zones
                    if occupancy_ratio > 0.7:
                        conditions["occupancy"] = "high"
                    elif occupancy_ratio > 0.4:
                        conditions["occupancy"] = "medium"
                    elif occupancy_ratio > 0.1:
                        conditions["occupancy"] = "low"
                    else:
                        conditions["occupancy"] = "minimal"

            except Exception as e:
                logger.warning(f"Failed to get DALI occupancy data: {e}")

            # Gather solar PV telemetry (inverters + meter)
            try:
                solar_total_kw = 0.0
                solar_efficiencies = []
                grid_solar_kw = None

                for device in devices:
                    if device.device_type == DeviceType.SOLAR:
                        # Read inverter AC power
                        for point_name in ["ac_power", "power", "active_power"]:
                            if point_name in device.points:
                                try:
                                    value = await device_manager.read_device_value(device.id, point_name)
                                    if value.value is not None:
                                        solar_total_kw += float(value.value)
                                except Exception:
                                    pass
                                break

                        # Read inverter efficiency
                        for point_name in ["efficiency", "performance_ratio"]:
                            if point_name in device.points:
                                try:
                                    value = await device_manager.read_device_value(device.id, point_name)
                                    if value.value is not None:
                                        solar_efficiencies.append(float(value.value))
                                except Exception:
                                    pass
                                break

                    elif device.device_type == DeviceType.METER:
                        # Read solar meter (grid-side)
                        if "solar" in device.id.lower() or "solar" in device.name.lower():
                            for point_name in ["active_power", "power", "total_power"]:
                                if point_name in device.points:
                                    try:
                                        value = await device_manager.read_device_value(device.id, point_name)
                                        if value.value is not None:
                                            grid_solar_kw = float(value.value)
                                    except Exception:
                                        pass
                                    break

                if solar_total_kw > 0 or grid_solar_kw is not None:
                    conditions["solar_generation_kw"] = round(solar_total_kw, 1)
                    conditions["_data_sources"]["solar"] = "live"
                    if solar_efficiencies:
                        conditions["solar_avg_efficiency_pct"] = round(
                            sum(solar_efficiencies) / len(solar_efficiencies), 1
                        )
                    if grid_solar_kw is not None:
                        conditions["grid_solar_kw"] = round(grid_solar_kw, 1)

            except Exception as e:
                logger.warning(f"Failed to get solar telemetry: {e}")

            # Gather BESS telemetry
            try:
                for device in devices:
                    if device.device_type == DeviceType.BESS:
                        bess_data = {}

                        for point_name in ["soc", "power", "mode", "temperature"]:
                            if point_name in device.points:
                                try:
                                    value = await device_manager.read_device_value(device.id, point_name)
                                    if value.value is not None:
                                        bess_data[point_name] = value.value
                                except Exception:
                                    pass

                        if bess_data:
                            conditions["bess_soc_pct"] = bess_data.get("soc")
                            conditions["bess_power_kw"] = bess_data.get("power")
                            conditions["bess_mode"] = bess_data.get("mode")
                            conditions["bess_temperature"] = bess_data.get("temperature")
                            conditions["_data_sources"]["bess"] = "live"
                            break  # Only first BESS device

            except Exception as e:
                logger.warning(f"Failed to get BESS telemetry: {e}")

            return conditions

        except Exception as e:
            logger.error(f"Error gathering current conditions: {e}")
            # Return default conditions
            return {
                "indoor_temp": 22.0,
                "outdoor_temp": 28.0,
                "humidity": 55.0,
                "occupancy": "medium",
                "equipment_status": "normal",
                "timestamp": datetime.now().isoformat(),
                "zone_occupancy": {},
            }

    def _generate_mock_weather_forecast(self) -> Dict[str, Any]:
        """Generate mock weather forecast for next 4 hours."""
        return {
            "current_temp": 28.0,
            "forecast": [
                {"time": "+1h", "temp": 28.5, "humidity": 55},
                {"time": "+2h", "temp": 29.0, "humidity": 53},
                {"time": "+3h", "temp": 29.5, "humidity": 50},
                {"time": "+4h", "temp": 30.0, "humidity": 48},
            ],
            "conditions": "partly_cloudy",
        }

    def _generate_mock_energy_prices(self) -> Dict[str, Any]:
        """Generate mock energy pricing (South African time-of-use)."""
        return {
            "current_rate": 2.28,  # R/kWh standard (City Power LPU-TOU 2025/26)
            "peak_rate": 3.01,  # R/kWh peak
            "off_peak_rate": 1.77,  # R/kWh off-peak
            "period": "standard",  # peak, off_peak, standard
            "currency": "ZAR",
        }

    def _build_optimization_prompt(
        self,
        site: Dict[str, Any],
        current_conditions: Dict[str, Any],
        weather_forecast: Dict[str, Any],
        energy_prices: Dict[str, Any],
        equipment_inventory: Dict[str, List[Device]],
        dali_zones: Optional[Dict[str, Any]] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build optimization prompt for Claude with ALL available equipment.

        Equipment inventory varies by building - some have generators, others don't.
        The AI should only recommend changes for equipment that exists at this site.

        Args:
            site: Site configuration
            current_conditions: Current building conditions
            weather_forecast: Weather forecast
            energy_prices: Energy pricing
            equipment_inventory: Equipment by type
            dali_zones: DALI zone data
            profile: Optimization profile with weights and thresholds
        """
        dali_zones = dali_zones or {}

        # Extract equipment by type for specific sections
        hvac_devices = equipment_inventory.get("hvac", [])
        lighting_devices = equipment_inventory.get("lighting", [])

        # Get controllable equipment only
        controllable = self._get_controllable_equipment(equipment_inventory)

        # Build equipment inventory summary
        inventory_summary = []
        for device_type, devices in equipment_inventory.items():
            if devices:
                inventory_summary.append(f"- {device_type.upper()}: {len(devices)} devices")

        # Build profile section if profile is provided
        profile_section = ""
        if profile:
            profile_weights = profile.get("weights", {})
            profile_thresholds = profile.get("thresholds", {})
            profile_section = f"""
**ACTIVE OPTIMIZATION PROFILE: {profile.get("name", "Default")}**
{profile.get("description", "No description available")}

**Optimization Weights (priorities):**
- Runtime/Equipment Health: {profile_weights.get("runtime", 0.25):.0%}
- Comfort: {profile_weights.get("comfort", 0.25):.0%}
- Cost: {profile_weights.get("cost", 0.25):.0%}
- Maintenance: {profile_weights.get("maintenance", 0.15):.0%}
- Energy: {profile_weights.get("energy", 0.10):.0%}

**Profile-Specific Decision Guidance:**
"""
            # Add profile-specific guidance
            profile_name = profile.get("name", "").lower()
            if "asset" in profile_name or "sweat" in profile_name:
                profile_section += """- MAXIMIZE equipment runtime and utilization
- Accept higher maintenance risk to extend asset life
- Reduce idle hours - keep systems running efficiently
- Use relaxed comfort bands to maximize runtime"""
            elif "comfort" in profile_name:
                profile_section += """- PRIORITIZE occupant comfort with tight temperature control
- Maintain setpoints within ±1°C of target
- Fast fault response and recovery
- Accept higher energy costs for comfort"""
            elif "cost" in profile_name or "saving" in profile_name:
                profile_section += """- MINIMIZE operational costs and energy consumption
- Aggressive load shifting and demand response
- Accept wider comfort bands (±2°C) during off-peak
- Prioritize peak-shaving and cost reduction"""

            profile_section += f"""

**Profile Thresholds & Constraints:**
{json.dumps(profile_thresholds, indent=2) if profile_thresholds else "No specific thresholds"}

**Your optimization must respect these profile priorities above all else.**
"""

        prompt = (
            "You are an expert building optimization engineer. "
            "Analyze this building's equipment and recommend optimal "
            "setpoints for energy efficiency and occupant comfort.\n\n"
            "**IMPORTANT:** This building has a SPECIFIC equipment "
            "inventory. Only recommend changes for equipment that "
            "EXISTS at this site. Different buildings have different "
            "equipment combinations.\n\n"
        )

        op_hours = site.get("operating_hours", {})
        op_start = op_hours.get("start", "08:00")
        op_end = op_hours.get("end", "18:00")

        prompt += f"""**Building:** {site["name"]} ({site["id"]})
- Type: {site.get("type", "commercial")}
- Size: {site.get("sqm", 5000)} sqm
- Floors: {site.get("floors", 1)}
- Operating hours: {op_start} - {op_end}
- Region: {site.get("region", "Gauteng")}

**Equipment Inventory at This Site:**
{chr(10).join(inventory_summary) if inventory_summary else "No equipment registered"}
{profile_section}

**Current Conditions:**
- Indoor temperature: {current_conditions.get("indoor_temp", 22)}°C
- Outdoor temperature: {current_conditions.get("outdoor_temp", 28)}°C
- Humidity: {current_conditions.get("humidity", 55)}%
- Occupancy: {current_conditions.get("occupancy", "unknown")}
- Equipment status: {current_conditions.get("equipment_status", "normal")}

{self._format_solar_bess_telemetry(current_conditions)}
**Weather Forecast (next 4 hours):**
{json.dumps(weather_forecast, indent=2)}

**Energy Pricing (South African):**
{json.dumps(energy_prices, indent=2)}

{self._format_all_equipment_sections(equipment_inventory)}

**All Available Control Points (by system):**
{self._format_all_control_points(controllable)}

{self._format_zone_context(hvac_devices)}

**Zone-Aware Optimization Rules (Southern Hemisphere - South Africa):**
- Executive/Server zones (P1): Maintain tighter comfort bands, never sacrifice cooling
- North/West-facing zones: Account for strongest direct and afternoon solar heat gain
- Top floor zones: Apply stronger optimization response due to roof-driven heat gain
- Meeting rooms (P2): Pre-condition 15 min before scheduled meetings
- Load shedding: Prioritize by zone_priority (P1 = critical, P5 = shed first)
- Plant rooms (P5): Can accept wider temperature ranges for energy savings

**Equipment-Specific Constraints (SAFETY LIMITS):**

HVAC:
- CHW temperature: 5-15°C (minimum 5°C to prevent freeze damage)
- Zone setpoints: 20-26°C (standard), 21-23°C (executive), 18-22°C (server)
- Humidity: 30-65% RH

Lighting (DALI):
- Minimum 10% (level 25) in occupied zones for safety
- Minimum 70% (level 178) in emergency zones
- Unoccupied zones: dim to 20% (level 51) not off

Power/Generators:
- Generator: start only during load shedding or mains failure
- UPS: maintain battery charge >50%
- ATS: automatic transfer, no manual override unless emergency

Solar PV:
- Inverters: monitor only, no direct setpoint control (cloud-managed)
- Curtailment: only if grid export limit exceeded or NRS 097 violation
- Performance ratio target: >80% (investigate if below 75%)

BESS (Battery Storage):
- SOC limits: maintain 10-90% (never fully discharge or overcharge)
- Discharge priority: peak TOU periods (07:00-10:00, 18:00-20:00)
- Charge priority: off-peak (22:00-06:00) or excess solar generation
- Load shedding: BESS discharge to critical loads before generator start
- Mode changes: idle→discharge allowed, charging→discharge needs 60s transition

{self._format_lighting_section(lighting_devices, dali_zones)}

**Your Task:**
1. Review the equipment inventory - ONLY recommend changes for equipment that EXISTS at this site
2. Analyze current conditions vs outdoor weather and occupancy
3. Consider energy pricing (higher rates = more aggressive optimization)
4. Apply zone-aware rules based on zone_type and exposure
5. Recommend setpoint changes for ALL relevant equipment types:
   - HVAC: temperature setpoints, fan speeds, damper positions
   - Lighting: DALI dim levels (0-254), scene selection
   - Power: generator start/stop (only if load shedding), UPS mode
   - Solar: performance alerts, curtailment if export limit reached
   - BESS: dispatch mode (charge/discharge/idle), SOC targets, load shedding response
   - Meters: no direct control, but use readings for context
6. CRITICAL: Use EXACT point_name from "All Available Control Points" above
7. Project energy savings in ZAR per hour (breakdown by system)
8. Ensure all recommendations are within safety limits
9. Prioritize cross-system coordination:
   - Unoccupied zones: raise HVAC AND dim lights
   - Peak solar: charge BESS
   - Load shedding: BESS before generator

**Response Format (JSON):**
```json
{{
  "recommendations": [
    {{
      "equipment_id": "device-id",
      "equipment_name": "Device Name",
      "point_name": "zone_cooling_setpoint",
      "current_value": 22.0,
      "recommended_value": 23.0,
      "unit": "°C",
      "reason": "Raise setpoint during low occupancy",
      "system": "hvac"
    }},
    {{
      "equipment_id": "zone-L11-S",
      "equipment_name": "Level 11 South",
      "point_name": "dim_level",
      "current_value": 254,
      "recommended_value": 51,
      "unit": "level",
      "reason": "Zone unoccupied - dim to 20%",
      "system": "lighting"
    }},
    {{
      "equipment_id": "S002-GEN-1",
      "equipment_name": "Main Generator",
      "point_name": "mode",
      "current_value": "standby",
      "recommended_value": "standby",
      "unit": "mode",
      "reason": "No load shedding - maintain standby",
      "system": "power"
    }},
    {{
      "equipment_id": "S002-BESS-B1-001",
      "equipment_name": "Battery Energy Storage (B1)",
      "point_name": "mode",
      "current_value": "idle",
      "recommended_value": "discharging",
      "unit": "mode",
      "reason": "Peak TOU period - discharge BESS to reduce grid import",
      "system": "bess"
    }}
  ],
  "cross_system_recommendations": [
    {{
      "zone_id": "Zone-L11-S",
      "zone_name": "Level 11 South",
      "hvac_action": "Raise setpoint +2°C",
      "lighting_action": "Dim to 20%",
      "power_action": null,
      "reason": "Zone unoccupied - coordinated energy savings",
      "combined_savings_kw": 1.2
    }}
  ],
  "projected_savings": {{
    "hvac_kwh": 12.5,
    "lighting_kwh": 3.2,
    "power_kwh": 0.0,
    "solar_kwh": 0.0,
    "bess_kwh": 8.5,
    "total_kwh": 24.2,
    "cost_zar_per_hour": 60.50,
    "percentage_improvement": 15.2
  }},
  "equipment_not_optimized": ["S002-GEN-1", "S002-UPS-1"],
  "equipment_not_optimized_reason": "Generator and UPS in standby - no optimization needed",
  "confidence": 0.85,
  "reasoning": "Summary of optimization strategy for this building's specific equipment"
}}
```

Provide ONLY the JSON response, no additional text."""

        return prompt

    async def _analyze_with_claude(
        self,
        site_id: str,
        prompt: str,
        current_conditions: Dict[str, Any],
        equipment_inventory: Dict[str, List[Device]],
        dali_zones: Optional[Dict[str, Any]] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> OptimizationRecommendation:
        """Analyze using Claude AI with full equipment inventory.

        Args:
            site_id: Site identifier
            prompt: Optimization prompt with profile information
            current_conditions: Current building conditions
            equipment_inventory: Equipment by type
            dali_zones: DALI zone data
            profile: Active optimization profile (if any)
        """
        try:
            logger.info(f"Using Claude AI for optimization of site {site_id}")

            # Call Claude (synchronous call for analysis)

            response_text = ""
            async for chunk in self._claude_service.stream_response(
                messages=[{"role": "user", "content": prompt}],
                include_building_context=False,  # Don't include full context to save tokens
            ):
                response_text += chunk

            # Parse JSON response
            try:
                # Extract JSON from response (handle markdown code blocks)
                if "```json" in response_text:
                    json_start = response_text.find("```json") + 7
                    json_end = response_text.find("```", json_start)
                    json_text = response_text[json_start:json_end].strip()
                elif "```" in response_text:
                    json_start = response_text.find("```") + 3
                    json_end = response_text.find("```", json_start)
                    json_text = response_text[json_start:json_end].strip()
                else:
                    json_text = response_text.strip()

                result = json.loads(json_text)

                return OptimizationRecommendation(
                    site_id=site_id,
                    timestamp=datetime.now().isoformat(),
                    recommendations=result.get("recommendations", []),
                    projected_savings=result.get("projected_savings", {}),
                    confidence=result.get("confidence", 0.7),
                    reasoning=result.get("reasoning", ""),
                    profile=profile.get("name") if profile else None,
                    profile_applied=bool(profile),
                )

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Claude response as JSON: {e}")
                logger.debug(f"Response text: {response_text}")
                # Fall back to rule-based
                raise

        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            raise

    def _score_and_rank_recommendations(
        self, recommendation: OptimizationRecommendation, profile: Dict[str, Any]
    ) -> OptimizationRecommendation:
        """Score and rank recommendations using profile weights.

        Applies multi-objective scoring to recommendations and ranks them by score.
        Updates the recommendation object with scores and summary statistics.

        Args:
            recommendation: OptimizationRecommendation with recommendations list
            profile: Active optimization profile with weights

        Returns:
            OptimizationRecommendation with scored and ranked recommendations
        """
        try:
            from app.services.recommendation_scorer import RecommendationScorer

            # Create scorer with profile weights
            scorer = RecommendationScorer(profile)

            # Score and rank recommendations
            ranked_recs = scorer.rank_recommendations(recommendation.recommendations)

            # Update recommendation object
            recommendation.recommendations = ranked_recs

            # Create scoring summary
            if ranked_recs:
                scores = [r.get("multi_objective_score", 0) for r in ranked_recs]
                recommendation.scoring_summary = {
                    "total_recommendations": len(ranked_recs),
                    "top_score": scores[0] if scores else 0,
                    "avg_score": sum(scores) / len(scores) if scores else 0,
                }
            else:
                recommendation.scoring_summary = {
                    "total_recommendations": 0,
                    "top_score": 0,
                    "avg_score": 0,
                }

            logger.info(
                f"Scored {len(ranked_recs)} recommendations for site {recommendation.site_id}. "
                f"Top score: {recommendation.scoring_summary.get('top_score', 0):.3f}, "
                f"Avg score: {recommendation.scoring_summary.get('avg_score', 0):.3f}"
            )

            return recommendation

        except Exception as e:
            logger.warning(f"Failed to score recommendations: {e}. Returning unscored.")
            return recommendation

    def _find_device_by_type(self, hvac_devices: List[Device], hvac_type: str) -> Optional[Device]:
        """Find a device by its hvac_type (zone_controller, chiller, chw_system, etc.)."""
        for device in hvac_devices:
            if hasattr(device, "hvac_type") and device.hvac_type == hvac_type:
                return device
        return None

    def _find_devices_by_type(self, hvac_devices: List[Device], hvac_type: str) -> List[Device]:
        """Find ALL devices of a specific hvac_type."""
        return [d for d in hvac_devices if hasattr(d, "hvac_type") and d.hvac_type == hvac_type]

    def _find_devices_with_point(self, hvac_devices: List[Device], point_name: str) -> List[Device]:
        """Find ALL devices that have a specific point."""
        return [d for d in hvac_devices if point_name in d.points]

    def _find_point_on_device(self, device: Device, possible_point_names: List[str]) -> Optional[DevicePoint]:
        """Find a point on a device by checking multiple possible names."""
        for point_name in possible_point_names:
            if point_name in device.points:
                return device.points[point_name]
        return None

    def _has_any_point(self, device: Device, possible_point_names: List[str]) -> bool:
        """Check if device has any of the specified points."""
        return any(point_name in device.points for point_name in possible_point_names)

    def _format_device_list(self, hvac_devices: List[Device]) -> str:
        """Format device list for Claude prompt."""
        if not hvac_devices:
            return "No HVAC devices found"
        lines = []
        for d in hvac_devices:
            hvac_type = getattr(d, "hvac_type", "unknown")
            location = getattr(d, "location", "unknown location")
            lines.append(f"- {d.id}: {d.name} ({hvac_type}) at {location}")
        return "\n".join(lines)

    def _format_available_points(self, hvac_devices: List[Device]) -> str:
        """Format available control points for Claude prompt."""
        if not hvac_devices:
            return "No control points available"
        lines = []
        for d in hvac_devices:
            writable_points = [name for name, point in d.points.items() if point.writable]
            if writable_points:
                lines.append(f"- {d.id} ({d.name}): {', '.join(writable_points)}")
        return "\n".join(lines) if lines else "No writable control points found"

    def _find_device_with_point(self, hvac_devices: List[Device], point_name: str) -> Optional[Device]:
        """Find a device that has a specific point."""
        for device in hvac_devices:
            if point_name in device.points:
                return device
        return None

    # Equipment Inventory Methods (Site-Specific)

    def _categorize_equipment(self, devices: List[Device]) -> Dict[str, List[Device]]:
        """Categorize all equipment by type for site-specific optimization.

        Different buildings have different equipment combinations:
        - Building A: HVAC + DALI + Generators + Meters
        - Building B: HVAC + Standard Lighting + UPS
        - Building C: HVAC + DALI + Security + Fire

        Returns:
            Dict mapping device type to list of devices
        """
        inventory: Dict[str, List[Device]] = {}

        for device in devices:
            # Get device type key (e.g., "hvac", "lighting", "power")
            type_key = device.device_type.value if device.device_type else "other"

            if type_key not in inventory:
                inventory[type_key] = []
            inventory[type_key].append(device)

        return inventory

    def _summarize_inventory(self, inventory: Dict[str, List[Device]]) -> str:
        """Create a summary string of equipment inventory for logging."""
        parts = []
        for device_type, devices in inventory.items():
            if devices:
                parts.append(f"{device_type}={len(devices)}")
        return ", ".join(parts) if parts else "empty"

    def _get_controllable_equipment(self, inventory: Dict[str, List[Device]]) -> Dict[str, List[Device]]:
        """Filter inventory to only include equipment with writable points.

        This is used for recommendations - we can only recommend changes
        to equipment that has controllable parameters.
        """
        controllable: Dict[str, List[Device]] = {}

        for device_type, devices in inventory.items():
            controllable_devices = []
            for device in devices:
                writable_points = [name for name, point in device.points.items() if point.writable]
                if writable_points:
                    controllable_devices.append(device)

            if controllable_devices:
                controllable[device_type] = controllable_devices

        return controllable

    def _format_equipment_by_type(self, devices: List[Device], equipment_type: str) -> str:
        """Format equipment list for a specific type in the AI prompt."""
        if not devices:
            return f"No {equipment_type} equipment available"

        lines = []
        for d in devices:
            # Get type-specific attributes
            extra_info = ""
            if equipment_type == "hvac":
                hvac_type = getattr(d, "hvac_type", "unknown")
                extra_info = f" ({hvac_type})"
            elif equipment_type == "power":
                # For generators, UPS, ATS, meters
                power_type = getattr(d, "equipment", {})
                if hasattr(power_type, "get"):
                    extra_info = f" ({power_type.get('type', 'unknown')})"
            elif equipment_type == "meter":
                extra_info = " (energy meter)"

            location = getattr(d, "location", "unknown location")
            if hasattr(d, "device_location") and d.device_location:
                loc = d.device_location
                location = f"{getattr(loc, 'building', '')}/{getattr(loc, 'floor', '')}/{getattr(loc, 'zone', '')}"

            lines.append(f"- {d.id}: {d.name}{extra_info} at {location}")

        return "\n".join(lines)

    def _format_all_equipment_sections(self, inventory: Dict[str, List[Device]]) -> str:
        """Format all equipment types into prompt sections."""
        sections = []

        # Order equipment types by optimization priority
        type_order = ["hvac", "lighting", "power", "solar", "bess", "meter", "security", "fire_safety", "other"]

        for device_type in type_order:
            devices = inventory.get(device_type, [])
            if devices:
                type_label = device_type.upper().replace("_", " ")
                section = f"""**{type_label} Equipment ({len(devices)} devices):**
{self._format_equipment_by_type(devices, device_type)}"""
                sections.append(section)

        # Add any remaining types not in the order
        for device_type, devices in inventory.items():
            if device_type not in type_order and devices:
                type_label = device_type.upper().replace("_", " ")
                section = f"""**{type_label} Equipment ({len(devices)} devices):**
{self._format_equipment_by_type(devices, device_type)}"""
                sections.append(section)

        return "\n\n".join(sections) if sections else "No equipment available"

    def _format_all_control_points(self, inventory: Dict[str, List[Device]]) -> str:
        """Format all writable control points across all equipment types."""
        lines = []

        for device_type, devices in inventory.items():
            type_label = device_type.upper()
            type_lines = []

            for d in devices:
                writable_points = [name for name, point in d.points.items() if point.writable]
                if writable_points:
                    type_lines.append(f"  - {d.id} ({d.name}): {', '.join(writable_points)}")

            if type_lines:
                lines.append(f"\n[{type_label}]")
                lines.extend(type_lines)

        return "\n".join(lines) if lines else "No writable control points found"

    # Zone-Aware Optimization Helper Methods

    def _group_devices_by_zone(self, hvac_devices: List[Device]) -> Dict[str, List[Device]]:
        """Group devices by their zone name for coordinated optimization."""
        zones: Dict[str, List[Device]] = {}
        for device in hvac_devices:
            zone = (
                getattr(device.device_location, "zone", "Unknown") if hasattr(device, "device_location") else "Unknown"
            )
            if zone not in zones:
                zones[zone] = []
            zones[zone].append(device)
        return zones

    def _group_devices_by_floor(self, hvac_devices: List[Device]) -> Dict[str, List[Device]]:
        """Group devices by floor level."""
        floors: Dict[str, List[Device]] = {}
        for device in hvac_devices:
            floor = (
                getattr(device.device_location, "floor", "Unknown") if hasattr(device, "device_location") else "Unknown"
            )
            if floor not in floors:
                floors[floor] = []
            floors[floor].append(device)
        return floors

    def _get_zone_priority(self, device: Device) -> int:
        """Get zone priority for load shedding ordering (1=highest priority, 5=lowest)."""
        if hasattr(device, "device_location") and device.device_location:
            return getattr(device.device_location, "zone_priority", 3)
        return 3  # Default to middle priority

    def _get_zone_type(self, device: Device) -> Optional[ZoneType]:
        """Get the zone type for a device."""
        if hasattr(device, "device_location") and device.device_location:
            return getattr(device.device_location, "zone_type", None)
        return None

    def _get_exposure(self, device: Device) -> Optional[ExposureDirection]:
        """Get the exposure direction for a device."""
        if hasattr(device, "device_location") and device.device_location:
            return getattr(device.device_location, "exposure", None)
        return None

    def _get_floor_level(self, device: Device) -> int:
        """Get numeric floor level from device location.

        Returns:
            Floor level as integer (-1=basement, 0=ground, 1+=upper floors)
        """
        if not hasattr(device, "device_location") or not device.device_location:
            return 0

        floor = getattr(device.device_location, "floor", "Ground")
        if floor == "Basement":
            return -1
        elif floor == "Ground":
            return 0
        elif floor == "Roof":
            return 99  # High number for roof
        elif floor.startswith("FL"):
            try:
                return int(floor[2:])
            except ValueError:
                return 0
        return 0

    def _get_exposure_modifier(self, device: Device, outdoor_temp: float) -> float:
        """Get temperature adjustment based on exposure direction and outdoor temp.

        In the Southern Hemisphere (South Africa), the sun tracks through the
        NORTHERN sky:
        - North-facing zones receive maximum direct solar radiation
        - South-facing zones receive minimal direct sun (mostly diffuse)
        - East gets morning sun, West gets afternoon sun

        Args:
            device: The device to check
            outdoor_temp: Current outdoor temperature

        Returns:
            Temperature modifier in degrees (positive = needs more cooling)
        """
        exposure = self._get_exposure(device)
        if exposure is None:
            return 0.0

        # Only apply modifiers when outdoor temp is warm enough to matter
        if outdoor_temp < 25.0:
            return 0.0

        hour = datetime.now().hour
        modifiers = {
            ExposureDirection.NORTH: 1.5 if 10 <= hour <= 16 else 0.5,  # Max solar gain (sun in north sky in SA)
            ExposureDirection.WEST: 1.0 if 14 <= hour <= 18 else 0.0,  # Afternoon heat
            ExposureDirection.EAST: 1.0 if 6 <= hour <= 10 else 0.0,  # Morning heat
            ExposureDirection.SOUTH: 0.3 if 10 <= hour <= 16 else 0.0,  # Minimal direct, some diffuse/reflected
            ExposureDirection.INTERIOR: -0.5,  # Slightly less cooling needed
        }
        return modifiers.get(exposure, 0.0)

    def _calculate_data_quality_penalty(self, conditions: Dict[str, Any]) -> float:
        """Calculate a confidence penalty based on how much sensor data is defaulted.

        When sensors fail and we fall back to hardcoded defaults (22C indoor,
        28C outdoor, 55% humidity), we should trust the resulting recommendations
        less. This returns a penalty (0.0 to 0.25) to subtract from confidence.

        Penalty weights reflect how much each data source affects recommendation
        quality:
        - indoor_temp: 0.08 (most critical - wrong indoor temp = wrong setpoint)
        - outdoor_temp: 0.06 (drives rule triggers like temp_diff > 3C)
        - humidity: 0.03 (affects humidity rule only)
        - occupancy/dali: 0.05 (affects lighting + unoccupied zone rules)
        - solar: 0.02 (affects BESS charging decisions)
        - bess: 0.01 (affects BESS dispatch only)

        Max penalty: 0.25 (all defaults = confidence drops from 0.7 to 0.45)

        Args:
            conditions: Current conditions dict with _data_sources metadata

        Returns:
            Penalty value to subtract from confidence (0.0 to 0.25)
        """
        sources = conditions.get("_data_sources", {})
        if not sources:
            return 0.0  # No tracking metadata - legacy call, no penalty

        penalty_weights = {
            "indoor_temp": 0.08,
            "outdoor_temp": 0.06,
            "humidity": 0.03,
            "occupancy": 0.05,
            "solar": 0.02,
            "bess": 0.01,
        }

        penalty = 0.0
        defaulted_sources = []
        for source, weight in penalty_weights.items():
            status = sources.get(source, "default")
            if status != "live":
                penalty += weight
                defaulted_sources.append(source)

        if defaulted_sources:
            logger.info(f"Data quality penalty: -{penalty:.2f} confidence (defaulted: {', '.join(defaulted_sources)})")

        return penalty

    def _sort_recommendations_by_priority(
        self,
        recommendations: List[Dict],
        hvac_devices: List[Device],
    ) -> List[Dict]:
        """Sort recommendations by zone priority (critical zones first)."""
        device_map = {d.id: d for d in hvac_devices}

        def get_priority(rec: Dict) -> int:
            device = device_map.get(rec.get("equipment_id"))
            if device:
                return self._get_zone_priority(device)
            return 3  # Default priority

        return sorted(recommendations, key=get_priority)

    def _format_zone_context(self, hvac_devices: List[Device]) -> str:
        """Format zone context for Claude prompt."""
        zones_by_type: Dict[str, List[str]] = {}
        for device in hvac_devices:
            zone_type = self._get_zone_type(device)
            exposure = self._get_exposure(device)
            priority = self._get_zone_priority(device)

            zone_type_str = zone_type.value if zone_type else "unknown"
            exposure_str = exposure.value if exposure else "unknown"
            key = f"{zone_type_str}|{exposure_str}|P{priority}"

            if key not in zones_by_type:
                zones_by_type[key] = []
            zones_by_type[key].append(device.name)

        lines = ["**Zone Classification:**"]
        for key, devices in sorted(zones_by_type.items()):
            zone_type, exposure, priority = key.split("|")
            lines.append(f"- {zone_type} ({exposure}, {priority}): {', '.join(devices)}")
        return "\n".join(lines)

    # DALI Lighting Optimization Helper Methods

    def _gather_dali_zone_data(self, dali_service, site_id: str) -> Dict[str, Any]:
        """Gather DALI zone occupancy and lighting data for optimization.

        Args:
            dali_service: DALI service instance
            site_id: Site to gather data for

        Returns:
            Dictionary with zone occupancy and lighting summaries
        """
        zone_data = {}

        try:
            # Get all zones from DALI service
            zones = dali_service.get_all_zones()

            for zone in zones:
                zone_id = zone.get("zone_id")
                if not zone_id:
                    continue

                # Get occupancy data
                occupancy = dali_service.get_zone_occupancy(zone_id)
                # Get lighting data
                lighting = dali_service.get_zone_lighting(zone_id)

                zone_data[zone_id] = {
                    "zone_id": zone_id,
                    "zone_name": zone.get("name", zone_id),
                    "floor": zone.get("floor", "Unknown"),
                    "area_sqm": zone.get("area_sqm", 0),
                    "desk_count": zone.get("desk_count", 0),
                    "active_scene": zone.get("active_scene"),
                    "active_scene_name": zone.get("active_scene_name"),
                    "occupancy": occupancy.to_dict() if occupancy else None,
                    "lighting": lighting.to_dict() if lighting else None,
                    # Computed optimization flags
                    "is_occupied": occupancy.occupancy_percent > 10 if occupancy else True,
                    "has_high_daylight": occupancy.avg_lux_level > 500 if occupancy else False,
                    "is_over_lit": (
                        lighting.avg_dim_level > 50 and occupancy.occupancy_percent < 20
                        if (lighting and occupancy)
                        else False
                    ),
                }

        except Exception as e:
            logger.warning(f"Failed to gather DALI zone data: {e}")

        return zone_data

    def _format_solar_bess_telemetry(self, conditions: Dict[str, Any]) -> str:
        """Format solar/BESS telemetry section for the optimization prompt.

        Only included when solar data exists in conditions (backward compatible).
        """
        solar_kw = conditions.get("solar_generation_kw")
        if solar_kw is None and conditions.get("bess_soc_pct") is None:
            return ""

        lines = ["**Solar & BESS Telemetry:**"]

        if solar_kw is not None:
            lines.append(f"- Total PV generation: {solar_kw} kW")
        eff = conditions.get("solar_avg_efficiency_pct")
        if eff is not None:
            lines.append(f"- Average inverter efficiency: {eff}%")
        grid = conditions.get("grid_solar_kw")
        if grid is not None:
            lines.append(f"- Grid solar meter reading: {grid} kW")

        soc = conditions.get("bess_soc_pct")
        if soc is not None:
            lines.append(f"- BESS SOC: {soc}%")
        bess_power = conditions.get("bess_power_kw")
        if bess_power is not None:
            direction = "discharging" if bess_power > 0 else "charging" if bess_power < 0 else "idle"
            lines.append(f"- BESS power: {abs(bess_power)} kW ({direction})")
        bess_mode = conditions.get("bess_mode")
        if bess_mode is not None:
            lines.append(f"- BESS mode: {bess_mode}")
        bess_temp = conditions.get("bess_temperature")
        if bess_temp is not None:
            lines.append(f"- BESS temperature: {bess_temp}°C")

        return "\n".join(lines) + "\n"

    def _format_lighting_section(
        self,
        lighting_devices: List[Device],
        dali_zones: Dict[str, Any],
    ) -> str:
        """Format DALI lighting section for Claude prompt.

        Args:
            lighting_devices: List of lighting device objects
            dali_zones: DALI zone data from _gather_dali_zone_data

        Returns:
            Formatted string for Claude prompt
        """
        if not dali_zones:
            return ""

        lines = []

        # DALI Lighting System Summary
        lines.append("**DALI Lighting System:**")
        total_zones = len(dali_zones)
        occupied_zones = sum(1 for z in dali_zones.values() if z.get("is_occupied"))
        over_lit_zones = [z for z in dali_zones.values() if z.get("is_over_lit")]

        lines.append(f"- Total zones: {total_zones}")
        lines.append(f"- Occupied zones: {occupied_zones}")
        lines.append(f"- Over-lit unoccupied zones (ENERGY WASTE): {len(over_lit_zones)}")

        # List over-lit zones specifically
        if over_lit_zones:
            lines.append("\n**⚠️ Over-lit Unoccupied Zones (Priority for dimming):**")
            for zone in over_lit_zones:
                occ = zone.get("occupancy", {})
                light = zone.get("lighting", {})
                lines.append(
                    f"- {zone['zone_name']}: "
                    f"{occ.get('occupancy_percent', 0):.0f}% occupied, "
                    f"lights at {light.get('avg_brightness', 0):.0f}% ({light.get('total_power_watts', 0):.0f}W)"
                )

        # Lighting Telemetry by Zone
        lines.append("\n**Lighting Telemetry by Zone:**")
        for zone_id, zone in dali_zones.items():
            occ = zone.get("occupancy", {})
            light = zone.get("lighting", {})

            occ_pct = occ.get("occupancy_percent", 0) if occ else 0
            avg_lux = occ.get("avg_lux_level", 0) if occ else 0
            dim_level = light.get("avg_brightness", 0) if light else 0
            power_w = light.get("total_power_watts", 0) if light else 0
            faulty = light.get("faulty_luminaires", 0) if light else 0
            scene = zone.get("active_scene_name", "Manual")

            status = "🟢" if zone.get("is_occupied") else "⚪"
            lines.append(
                f"- {status} {zone['zone_name']}: "
                f"occupancy={occ_pct:.0f}%, lux={avg_lux:.0f}, "
                f"dim={dim_level:.0f}%, power={power_w:.0f}W, scene={scene}"
                + (f", faulty={faulty}" if faulty > 0 else "")
            )

        # Lighting Optimization Rules
        lines.append("\n**Lighting Optimization Rules:**")
        lines.append("- Daylight harvesting: When avg_lux > 500 (setpoint), dim proportionally")
        lines.append("- Unoccupied zones: Dim to 20% (level 51) for safety lighting only")
        lines.append("- Minimum brightness: 10% (level 25) in any occupied zone")
        lines.append("- Emergency zones: Never below 70% (level 178)")
        lines.append("- Scene override: Respect active scenes in meeting rooms during occupation")

        return "\n".join(lines)

    def _format_lighting_device_list(self, lighting_devices: List[Device]) -> str:
        """Format lighting device list for Claude prompt."""
        if not lighting_devices:
            return "No lighting devices found"
        lines = []
        for d in lighting_devices:
            lighting_type = getattr(d, "lighting_type", "unknown")
            location = getattr(d, "location", "unknown location")
            lines.append(f"- {d.id}: {d.name} ({lighting_type}) at {location}")
        return "\n".join(lines)

    def _should_skip_zone_optimization(self, device: Device, zone_type: Optional[ZoneType]) -> bool:
        """Check if zone type should have restricted optimization.

        Server rooms and critical zones should not have cooling reduced.
        """
        if zone_type == ZoneType.SERVER_ROOM:
            return True  # Never reduce cooling in server rooms
        return False

    def _get_zone_specific_setpoint_limits(self, device: Device, zone_type: Optional[ZoneType]) -> tuple:
        """Get zone-specific setpoint min/max limits.

        Returns:
            Tuple of (min_temp, max_temp) for the zone type
        """
        if zone_type == ZoneType.SERVER_ROOM:
            return (18.0, 22.0)  # Tighter range for server rooms
        elif zone_type == ZoneType.EXECUTIVE:
            return (21.0, 23.0)  # Tighter comfort range for executive
        elif zone_type == ZoneType.BANKING_HALL:
            return (20.0, 24.0)  # Customer comfort
        elif zone_type == ZoneType.MEETING_ROOM:
            return (20.0, 24.0)  # Standard comfort when occupied
        elif zone_type == ZoneType.PLANT_ROOM:
            return (16.0, 30.0)  # Wide range for equipment areas
        elif zone_type == ZoneType.PARKING:
            return (10.0, 35.0)  # Minimal HVAC
        else:  # OPEN_OFFICE, LOBBY, default
            return (20.0, 26.0)  # Standard comfort range

    def _apply_zone_aware_adjustments(
        self,
        device: Device,
        base_setpoint_change: float,
        outdoor_temp: float,
    ) -> float:
        """Apply zone-aware adjustments to setpoint recommendations.

        Args:
            device: The device to optimize
            base_setpoint_change: Initial recommended setpoint change
            outdoor_temp: Current outdoor temperature

        Returns:
            Adjusted setpoint change accounting for zone factors
        """
        zone_type = self._get_zone_type(device)
        floor_level = self._get_floor_level(device)
        exposure_modifier = self._get_exposure_modifier(device, outdoor_temp)

        adjusted_change = base_setpoint_change

        # Zone type adjustments
        if zone_type == ZoneType.EXECUTIVE:
            # Reduce setpoint increase for executive areas (comfort priority)
            adjusted_change *= 0.5
        elif zone_type == ZoneType.SERVER_ROOM:
            # No setpoint increase for server rooms
            adjusted_change = 0.0
        elif zone_type == ZoneType.PLANT_ROOM:
            # Can be more aggressive with plant rooms
            adjusted_change *= 1.5

        # Floor level adjustments
        if floor_level >= 3 or floor_level == 99:  # Top floor or roof
            # Apply stronger optimization on top floors/roof per policy tuning.
            adjusted_change *= 1.2
        elif floor_level == 0:  # Ground floor
            # Account for entry air infiltration
            adjusted_change *= 0.9

        # Exposure adjustments - south/west facing need less setpoint increase
        if exposure_modifier > 0:
            # Zones with solar gain need more cooling, so reduce setpoint increase
            adjusted_change -= exposure_modifier * 0.3

        return max(0.0, adjusted_change)  # Don't go negative

    def _analyze_with_rules(
        self,
        site_id: str,
        current_conditions: Dict[str, Any],
        weather_forecast: Dict[str, Any],
        energy_prices: Dict[str, Any],
        equipment_inventory: Dict[str, List[Device]],
        dali_zones: Optional[Dict[str, Any]] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> OptimizationRecommendation:
        """Fallback rule-based optimization for ALL equipment types.

        Uses equipment inventory to generate recommendations for whatever
        equipment exists at this site. Different buildings have different
        equipment combinations.

        Args:
            profile: Active optimization profile (if any)
        """
        logger.info(f"Using rule-based optimization for site {site_id}")
        dali_zones = dali_zones or {}
        if not isinstance(equipment_inventory, dict):
            equipment_inventory = {
                "hvac": list(equipment_inventory) if equipment_inventory else [],
                "power": [],
                "lighting": [],
                "meter": [],
            }

        # Extract equipment by type from inventory
        hvac_devices = equipment_inventory.get("hvac", [])
        power_devices = equipment_inventory.get("power", [])

        indoor_temp = current_conditions.get("indoor_temp", 22.0)
        outdoor_temp = current_conditions.get("outdoor_temp", 28.0)
        humidity = current_conditions.get("humidity", 55.0)
        temp_diff = outdoor_temp - indoor_temp

        recommendations = []
        confidence = 0.7  # Lower confidence for rule-based

        # Find ALL devices of each type (multi-device support)
        # Prioritize explicit hvac_type matches, only fall back to point-based matching if none found
        zone_controllers = self._find_devices_by_type(hvac_devices, "zone_controller")
        if not zone_controllers:
            # Fall back to devices with zone_cooling_setpoint or cooling_setpoint that aren't FCUs
            zone_controllers = [
                d
                for d in hvac_devices
                if self._has_any_point(d, ["zone_cooling_setpoint", "cooling_setpoint"])
                and getattr(d, "hvac_type", "") != "fcu"
            ]

        chw_systems = self._find_devices_by_type(hvac_devices, "chw_system")
        if not chw_systems:
            # Fall back to devices with CHW setpoint
            chw_systems = [
                d for d in hvac_devices if self._has_any_point(d, ["chw_supply_temp_setpoint", "supply_temp_setpoint"])
            ]

        fcus = self._find_devices_by_type(hvac_devices, "fcu")
        chillers = self._find_devices_by_type(hvac_devices, "chiller")

        # Track which device/point combinations have been recommended to avoid duplicates
        recommended_pairs = set()

        # Helper to add recommendation only if not already recommended
        def add_recommendation(device, point_name, current_value, recommended_value, reason):
            pair = (device.id, point_name)
            if pair not in recommended_pairs:
                recommended_pairs.add(pair)
                recommendations.append(
                    {
                        "equipment_id": device.id,
                        "equipment_name": device.name,
                        "point_name": point_name,
                        "current_value": current_value,
                        "recommended_value": recommended_value,
                        "unit": "°C",
                        "reason": reason,
                    }
                )

        # Rule 1: Zone temperature optimization for ALL zone controllers (ZONE-AWARE)
        # If outdoor > indoor + 3°C, recommend increasing cooling setpoint based on zone type
        if temp_diff > 3.0 and indoor_temp < 24.0:
            for zone_controller in zone_controllers:
                zone_type = self._get_zone_type(zone_controller)

                # Skip optimization for critical zones
                if self._should_skip_zone_optimization(zone_controller, zone_type):
                    continue

                # Check for multiple possible cooling setpoint names
                cooling_point_names = ["zone_cooling_setpoint", "cooling_setpoint", "cooling_setpoint_temp"]
                current_point = self._find_point_on_device(zone_controller, cooling_point_names)

                if current_point:
                    point_name = current_point.name
                    current_value = current_point.default_value if current_point else indoor_temp

                    # Apply zone-aware adjustment to base 1.5°C increase
                    adjusted_change = self._apply_zone_aware_adjustments(zone_controller, 1.5, outdoor_temp)

                    if adjusted_change > 0.1:  # Only recommend if meaningful change
                        # Get zone-specific limits
                        _, max_temp = self._get_zone_specific_setpoint_limits(zone_controller, zone_type)
                        new_setpoint = min(current_value + adjusted_change, max_temp)

                        zone_info = f" ({zone_type.value} zone)" if zone_type else ""
                        add_recommendation(
                            zone_controller,
                            point_name,
                            current_value,
                            round(new_setpoint, 1),
                            f"Increase setpoint {adjusted_change:.1f}"
                            f"°C{zone_info} as outdoor temp rising"
                            f" to {outdoor_temp}°C - reduces "
                            f"cooling load while maintaining comfort",
                        )

        # Rule 2: Humidity optimization for ALL zone controllers with humidity setpoint
        # Guard: Only raise humidity setpoint during dry conditions (winter/dry season).
        # In Gauteng's wet summers (Oct-Mar), outdoor humidity is already high and
        # raising the setpoint risks condensation and mold growth.
        current_month = datetime.now().month
        is_wet_season = current_month in (10, 11, 12, 1, 2, 3)  # Oct-Mar (SA wet season)

        # Only recommend humidity raise if: dry conditions AND dry season OR very dry
        humidity_threshold = 40.0 if is_wet_season else 50.0
        humidity_cap = 55.0 if is_wet_season else 60.0

        if humidity < humidity_threshold:
            for zone_controller in zone_controllers:
                if "humidity_setpoint" in zone_controller.points:
                    current_humidity_sp = zone_controller.points.get("humidity_setpoint")
                    current_value = current_humidity_sp.default_value if current_humidity_sp else 55.0
                    new_humidity = min(current_value + 3.0, humidity_cap)

                    season_note = " (wet season: conservative cap)" if is_wet_season else ""
                    add_recommendation(
                        zone_controller,
                        "humidity_setpoint",
                        current_value,
                        new_humidity,
                        f"Allow humidity to rise 3% as outdoor "
                        f"humidity drops{season_note}"
                        f" - reduces dehumidification energy",
                    )

        # Rule 3: CHW temperature optimization for ALL chillers
        # If outdoor temp is high, can raise CHW supply temp for efficiency
        if outdoor_temp > 28.0:
            for chiller in chillers:
                # Check for multiple possible CHW setpoint names
                chw_point_names = ["chw_supply_temp_setpoint", "supply_temp_setpoint", "chilled_water_setpoint"]
                current_point = self._find_point_on_device(chiller, chw_point_names)

                if current_point:
                    point_name = current_point.name
                    current_value = current_point.default_value if current_point else 7.0
                    new_chw_temp = min(current_value + 1.5, 9.0)  # Don't go above 9°C

                    add_recommendation(
                        chiller,
                        point_name,
                        current_value,
                        new_chw_temp,
                        "Increase CHW temp 1.5°C for higher chiller efficiency with rising outdoor temps",
                    )

        # Rule 4: FCU optimization for ALL FCUs (ZONE-AWARE)
        # Optimize fan speed and setpoints based on conditions and zone type
        # FCU recommendations are marked as advisory (low confidence) - no human approval needed
        if temp_diff > 2.0:
            for fcu in fcus:
                zone_type = self._get_zone_type(fcu)

                # Skip optimization for critical zones
                if self._should_skip_zone_optimization(fcu, zone_type):
                    continue

                # Optimize cooling setpoint if available
                cooling_point_names = ["cooling_setpoint", "zone_cooling_setpoint", "room_temp_setpoint"]
                cooling_point = self._find_point_on_device(fcu, cooling_point_names)

                if cooling_point:
                    current_value = cooling_point.default_value if cooling_point else 22.0

                    # Apply zone-aware adjustment to base 1.0°C increase
                    adjusted_change = self._apply_zone_aware_adjustments(fcu, 1.0, outdoor_temp)

                    if adjusted_change > 0.1:
                        # Get zone-specific limits
                        _, max_temp = self._get_zone_specific_setpoint_limits(fcu, zone_type)
                        new_setpoint = min(current_value + adjusted_change, max_temp)

                        zone_info = f" ({zone_type.value} zone)" if zone_type else ""
                        exposure = self._get_exposure(fcu)
                        exposure_info = f", {exposure.value}-facing" if exposure else ""

                        add_recommendation(
                            fcu,
                            cooling_point.name,
                            current_value,
                            round(new_setpoint, 1),
                            f"Increase FCU setpoint "
                            f"{adjusted_change:.1f}°C"
                            f"{zone_info}{exposure_info}"
                            f" to reduce cooling load during"
                            f" high outdoor temps"
                            f" ({outdoor_temp}°C)",
                        )
                        # Mark as advisory - add low confidence to route to Tier 1
                        recommendations[-1]["confidence"] = 0.45  # Below tier2_min (~0.6)

                # Optimize fan speed if available and conditions warrant
                # Don't reduce fan speed in executive zones (comfort priority)
                if (
                    "fan_speed" in fcu.points
                    and temp_diff < 5.0
                    and zone_type not in [ZoneType.EXECUTIVE, ZoneType.SERVER_ROOM]
                ):
                    current_speed = fcu.points.get("fan_speed")
                    current_value = current_speed.default_value if current_speed else 75.0
                    # Reduce fan speed slightly if temp difference is moderate
                    new_speed = max(current_value - 10.0, 50.0)

                    if new_speed < current_value:
                        add_recommendation(
                            fcu,
                            "fan_speed",
                            current_value,
                            new_speed,
                            "Reduce fan speed 10% for energy savings"
                            " - moderate temperature differential"
                            " allows lower airflow",
                        )
                        # Mark as advisory - add low confidence to route to Tier 1
                        recommendations[-1]["confidence"] = 0.45  # Below tier2_min (~0.6)

        # Rule 5: AHU Supply Air Temperature Reset
        ahus = self._find_devices_by_type(hvac_devices, "ahu")
        if not ahus:
            # Fallback: devices with supply_temp_setpoint or supply_air_temp_setpoint
            ahus = [
                d
                for d in hvac_devices
                if self._has_any_point(d, ["supply_temp_setpoint", "supply_air_temp_setpoint"])
                and getattr(d, "hvac_type", "") not in ("fcu", "chiller")
            ]

        if outdoor_temp < 18.0:
            # Mild outdoor temp: raise supply air temp to save reheat energy
            for ahu in ahus:
                sat_point_names = ["supply_temp_setpoint", "supply_air_temp_setpoint"]
                sat_point = self._find_point_on_device(ahu, sat_point_names)
                if sat_point:
                    current_value = sat_point.default_value if sat_point else 12.0
                    new_sat = min(current_value + 2.0, 14.0)
                    if new_sat > current_value:
                        add_recommendation(
                            ahu,
                            sat_point.name,
                            current_value,
                            new_sat,
                            f"Raise AHU supply air temp {new_sat - current_value:.1f}°C"
                            f" — mild outdoor temp ({outdoor_temp}°C) reduces"
                            f" reheat energy",
                        )
        elif outdoor_temp > 32.0:
            # Hot outdoor: lower supply air for more cooling capacity
            for ahu in ahus:
                sat_point_names = ["supply_temp_setpoint", "supply_air_temp_setpoint"]
                sat_point = self._find_point_on_device(ahu, sat_point_names)
                if sat_point:
                    current_value = sat_point.default_value if sat_point else 12.0
                    new_sat = max(current_value - 1.0, 11.0)
                    if new_sat < current_value:
                        add_recommendation(
                            ahu,
                            sat_point.name,
                            current_value,
                            new_sat,
                            f"Lower AHU supply air to {new_sat}°C — high outdoor"
                            f" temp ({outdoor_temp}°C) requires more cooling capacity",
                        )

        # Rule 6: AHU Economizer / Fresh Air Damper
        if 15.0 <= outdoor_temp <= 22.0 and humidity < 65.0:
            # Mild and dry: enable economizer for free cooling
            for ahu in ahus:
                eco_point_names = ["economizer_mode", "fresh_air_damper", "outdoor_air_damper"]
                eco_point = self._find_point_on_device(ahu, eco_point_names)
                if eco_point:
                    current_value = eco_point.default_value if eco_point else 20.0
                    # For damper points, open to 80-100%; for mode points, set to 1 (enabled)
                    if "mode" in eco_point.name:
                        target_value = 1  # enabled
                        reason = (
                            f"Enable AHU economizer — outdoor temp {outdoor_temp}°C"
                            f" and humidity {humidity}% ideal for free cooling"
                        )
                    else:
                        target_value = 85.0  # 85% open
                        reason = (
                            f"Open AHU fresh air damper to 85% — outdoor"
                            f" {outdoor_temp}°C/{humidity}% RH provides free cooling"
                        )
                    add_recommendation(ahu, eco_point.name, current_value, target_value, reason)
        elif outdoor_temp > 28.0:
            # Hot: close fresh air damper to minimum
            for ahu in ahus:
                damper_point_names = ["fresh_air_damper", "outdoor_air_damper"]
                damper_point = self._find_point_on_device(ahu, damper_point_names)
                if damper_point:
                    current_value = damper_point.default_value if damper_point else 50.0
                    if current_value > 20.0:
                        add_recommendation(
                            ahu,
                            damper_point.name,
                            current_value,
                            15.0,
                            f"Close AHU fresh air damper to 15% minimum —"
                            f" outdoor temp {outdoor_temp}°C too hot for economizer",
                        )

        # Rule 7: VAV Damper Position Optimization
        vavs = self._find_devices_by_type(hvac_devices, "vav")
        if not vavs:
            # Fallback: devices with damper_position or airflow_setpoint
            vavs = [
                d
                for d in hvac_devices
                if self._has_any_point(d, ["damper_position", "airflow_setpoint"])
                and getattr(d, "hvac_type", "") not in ("fcu", "ahu")
            ]

        if temp_diff > 2.0:
            for vav in vavs:
                zone_type = self._get_zone_type(vav)

                # Skip critical zones (server rooms keep higher minimum)
                if self._should_skip_zone_optimization(vav, zone_type):
                    continue

                damper_point_names = ["damper_position", "airflow_setpoint"]
                damper_point = self._find_point_on_device(vav, damper_point_names)
                if damper_point:
                    current_value = damper_point.default_value if damper_point else 70.0

                    # Apply zone-aware adjustment
                    adjusted_change = self._apply_zone_aware_adjustments(vav, -15.0, outdoor_temp)
                    # Executive/server zones get smaller reduction
                    if zone_type in [ZoneType.EXECUTIVE, ZoneType.SERVER_ROOM]:
                        adjusted_change = adjusted_change * 0.5

                    new_position = max(current_value + adjusted_change, 30.0)  # 30% minimum
                    if new_position < current_value - 5:  # Only recommend meaningful change
                        zone_info = f" ({zone_type.value} zone)" if zone_type else ""
                        add_recommendation(
                            vav,
                            damper_point.name,
                            current_value,
                            round(new_position, 0),
                            f"Reduce VAV damper to {new_position:.0f}%{zone_info}"
                            f" — outdoor temp rising ({outdoor_temp}°C),"
                            f" reduce airflow to save fan energy",
                        )
                        recommendations[-1]["unit"] = "%"
                        recommendations[-1]["confidence"] = 0.5

        # Rule 8: Pump Speed Optimization (affinity laws: 50% speed ≈ 12.5% power)
        pumps = [d for d in hvac_devices if self._has_any_point(d, ["speed_percent", "pump_speed", "flow_setpoint"])]

        if pumps and temp_diff < 5.0:
            # Moderate conditions: reduce pump speed proportionally
            # Count actively cooling FCUs/AHUs to estimate load
            active_cooling_count = len(fcus) + len(ahus)  # noqa: F841

            for pump in pumps:
                speed_point_names = ["speed_percent", "pump_speed"]
                speed_point = self._find_point_on_device(pump, speed_point_names)
                if speed_point:
                    current_value = speed_point.default_value if speed_point else 80.0
                    # Reduce by 20% when temp diff is moderate
                    target_speed = max(current_value - 20.0, 35.0)

                    if target_speed < current_value - 5:
                        add_recommendation(
                            pump,
                            speed_point.name,
                            current_value,
                            round(target_speed, 0),
                            f"Reduce pump speed to {target_speed:.0f}%"
                            f" — moderate cooling load (temp diff {temp_diff:.1f}°C)."
                            f" Affinity laws: ~{(1 - (target_speed / 100) ** 3) * 100:.0f}% power savings",
                        )
                        recommendations[-1]["unit"] = "%"
                        recommendations[-1]["confidence"] = 0.5

        # ============================================================
        # DALI Lighting — Tridonic Handles Native Controls
        # ============================================================
        # Tridonic DALI-2 gateway natively handles:
        #   - Daylight harvesting (continuous proportional dimming to 500 lux setpoint)
        #   - Occupancy-based dimming (PIR sensors → 20% when unoccupied)
        #   - Emergency zone protection (maintains 70% minimum)
        # AI does NOT duplicate these. Only cross-system coordination recommended.
        lighting_recommendations = []
        cross_system_recommendations = []
        lighting_savings_kw = 0.0

        if dali_zones:
            for zone_id, zone in dali_zones.items():
                lighting = zone.get("lighting", {})
                is_occupied = zone.get("is_occupied", True)

                if not lighting:
                    continue

                zone_name = zone.get("zone_name", zone_id)

                # Cross-system only: coordinate HVAC + lighting when zone unoccupied
                # (Tridonic dims lighting on its own, but can't adjust HVAC)
                if not is_occupied:
                    cross_system_recommendations.append(
                        {
                            "zone_id": zone_id,
                            "zone_name": zone_name,
                            "hvac_action": "Raise setpoint +2°C",
                            "lighting_action": "Managed by Tridonic controller",
                            "reason": "Zone unoccupied - HVAC setback (lighting handled by Tridonic)",
                            "combined_savings_kw": round(0.5, 2),  # HVAC savings only
                        }
                    )

        # ============================================================
        # Power Equipment Rules (Generators, UPS, ATS)
        # ============================================================
        power_recommendations = []

        # Only optimize power equipment if it exists at this site
        if power_devices:
            logger.info(f"Processing {len(power_devices)} power devices for optimization")

            for device in power_devices:
                device_type = device.name.lower()

                # Generator optimization
                if "gen" in device_type or "generator" in device_type:
                    # Generator should stay in standby unless load shedding
                    # This is informational - we don't change generator state automatically
                    if "mode" in device.points or "run_mode" in device.points:
                        point_name = "mode" if "mode" in device.points else "run_mode"
                        current_mode = (
                            device.points[point_name].default_value
                            if device.points[point_name].default_value
                            else "standby"
                        )

                        # Don't recommend starting generator unless load shedding
                        # Just confirm standby mode is appropriate
                        power_recommendations.append(
                            {
                                "equipment_id": device.id,
                                "equipment_name": device.name,
                                "point_name": point_name,
                                "current_value": current_mode,
                                "recommended_value": "standby",
                                "unit": "mode",
                                "reason": "No load shedding - maintain standby mode for efficiency",
                                "system": "power",
                            }
                        )

                # UPS optimization
                elif "ups" in device_type:
                    # UPS should maintain charge level, recommend eco mode if available
                    if "eco_mode" in device.points:
                        eco_mode = device.points["eco_mode"]
                        current_value = eco_mode.default_value if eco_mode.default_value is not None else False

                        # Enable eco mode during off-peak hours for efficiency
                        energy_period = energy_prices.get("period", "standard")
                        if energy_period == "off_peak" and not current_value:
                            power_recommendations.append(
                                {
                                    "equipment_id": device.id,
                                    "equipment_name": device.name,
                                    "point_name": "eco_mode",
                                    "current_value": current_value,
                                    "recommended_value": True,
                                    "unit": "bool",
                                    "reason": "Enable UPS eco mode during off-peak hours for efficiency",
                                    "system": "power",
                                }
                            )

                # ATS (Automatic Transfer Switch) - monitoring only
                elif "ats" in device_type:
                    # ATS operates automatically, no optimization needed
                    # Just log that it exists for the AI context
                    pass

        # ============================================================
        # Solar PV Rules (Inverters, Generation Monitoring)
        # ============================================================
        solar_recommendations = []
        solar_devices = equipment_inventory.get("solar", [])

        if solar_devices:
            logger.info(f"Processing {len(solar_devices)} solar devices for optimization")

            for device in solar_devices:
                device_name = device.name.lower()

                # Solar inverter monitoring
                if "inv" in device_name or "inverter" in device_name or "solar" in device_name:
                    # Check efficiency/performance ratio
                    efficiency_point = self._find_point_on_device(device, ["efficiency", "performance_ratio", "pr"])
                    if efficiency_point:
                        efficiency = (
                            efficiency_point.default_value if efficiency_point.default_value is not None else 95.0
                        )
                        if efficiency < 90.0:
                            solar_recommendations.append(
                                {
                                    "equipment_id": device.id,
                                    "equipment_name": device.name,
                                    "point_name": efficiency_point.name,
                                    "current_value": efficiency,
                                    "recommended_value": "investigate",
                                    "unit": "%",
                                    "reason": (
                                        f"Inverter efficiency "
                                        f"{efficiency:.1f}% below 90%"
                                        f" threshold - check for "
                                        f"shading, soiling, or"
                                        f" inverter fault"
                                    ),
                                    "system": "solar",
                                }
                            )

                    # Check status
                    status_point = self._find_point_on_device(device, ["status", "operating_status", "state"])
                    if status_point:
                        status = status_point.default_value if status_point.default_value is not None else "running"
                        if isinstance(status, str) and status.lower() in ["offline", "fault", "error", "stopped"]:
                            solar_recommendations.append(
                                {
                                    "equipment_id": device.id,
                                    "equipment_name": device.name,
                                    "point_name": status_point.name,
                                    "current_value": status,
                                    "recommended_value": "investigate",
                                    "unit": "status",
                                    "reason": f"Solar inverter {status} - investigate for potential generation loss",
                                    "system": "solar",
                                }
                            )

        # ============================================================
        # BESS Rules (Battery Dispatch, SOC Management)
        # ============================================================
        bess_recommendations = []
        bess_devices = equipment_inventory.get("bess", [])
        bess_savings_kw = 0.0

        if bess_devices:
            logger.info(f"Processing {len(bess_devices)} BESS devices for optimization")

            # Determine current TOU period from energy prices
            energy_period = energy_prices.get("period", "standard")
            current_hour = datetime.now().hour
            is_peak = energy_period == "peak" or current_hour in range(7, 10) or current_hour in range(18, 20)
            is_off_peak = energy_period == "off_peak" or current_hour in range(22, 24) or current_hour in range(0, 6)
            is_load_shedding = current_conditions.get("load_shedding", False)

            for device in bess_devices:
                # Find SOC point
                soc_point = self._find_point_on_device(
                    device, ["soc", "state_of_charge", "battery_level", "soc_percent"]
                )
                soc = soc_point.default_value if soc_point and soc_point.default_value is not None else 50.0

                # Find mode point
                mode_point = self._find_point_on_device(device, ["mode", "dispatch_mode", "operating_mode"])
                current_mode = (
                    mode_point.default_value if mode_point and mode_point.default_value is not None else "idle"
                )
                mode_point_name = mode_point.name if mode_point else "mode"

                # BESS dispatch rules (priority order)
                if is_load_shedding and soc > 15:
                    # Load shedding: discharge BESS before starting generator
                    recommended_mode = "discharging"
                    reason = (
                        f"Load shedding active - discharge BESS"
                        f" (SOC {soc:.0f}%) to critical loads"
                        f" before generator start"
                    )
                    bess_savings_kw += 50.0  # Significant savings by avoiding generator
                elif is_peak and soc > 20:
                    # Peak TOU: discharge to reduce grid import
                    recommended_mode = "discharging"
                    reason = f"Peak TOU period - discharge BESS (SOC {soc:.0f}%) to reduce expensive grid import"
                    bess_savings_kw += 25.0
                elif current_conditions.get("solar_generation_kw", 0) > 0 and soc < 90:
                    # Solar excess: charge BESS from surplus PV generation
                    solar_kw = current_conditions.get("solar_generation_kw", 0)
                    recommended_mode = "charging"
                    reason = (
                        f"Solar PV generating {solar_kw:.0f} kW - charge BESS from {soc:.0f}% "
                        f"using excess solar instead of exporting to grid"
                    )
                    bess_savings_kw += 15.0  # Store solar for peak use
                elif is_off_peak and soc < 80:
                    # Off-peak: charge from cheap grid power
                    recommended_mode = "charging"
                    reason = f"Off-peak rates - charge BESS from {soc:.0f}% to 80% target using cheap grid power"
                    bess_savings_kw += 5.0  # Preparing for peak savings
                else:
                    # Standard period or SOC constraints prevent action
                    recommended_mode = "idle"
                    reason = f"Standard period with SOC at {soc:.0f}% - maintain idle for battery longevity"

                if str(current_mode).lower() != recommended_mode:
                    bess_recommendations.append(
                        {
                            "equipment_id": device.id,
                            "equipment_name": device.name,
                            "point_name": mode_point_name,
                            "current_value": current_mode,
                            "recommended_value": recommended_mode,
                            "unit": "mode",
                            "reason": reason,
                            "system": "bess",
                        }
                    )
                else:
                    # Even if mode matches, include as confirmation
                    bess_recommendations.append(
                        {
                            "equipment_id": device.id,
                            "equipment_name": device.name,
                            "point_name": mode_point_name,
                            "current_value": current_mode,
                            "recommended_value": recommended_mode,
                            "unit": "mode",
                            "reason": reason,
                            "system": "bess",
                        }
                    )

        # Merge lighting recommendations with HVAC recommendations
        for rec in lighting_recommendations:
            recommendations.append(rec)

        # Merge power recommendations
        for rec in power_recommendations:
            recommendations.append(rec)

        # Merge solar recommendations
        for rec in solar_recommendations:
            recommendations.append(rec)

        # Merge BESS recommendations
        for rec in bess_recommendations:
            recommendations.append(rec)

        # Sort recommendations by zone priority (critical zones first)
        recommendations = self._sort_recommendations_by_priority(recommendations, hvac_devices)

        # Calculate projected savings based on number and type of recommendations
        hvac_recs = [r for r in recommendations if r.get("system") == "hvac" or r.get("system") is None]
        lighting_recs = [r for r in recommendations if r.get("system") == "lighting"]
        power_recs = [r for r in recommendations if r.get("system") == "power"]
        solar_recs = [r for r in recommendations if r.get("system") == "solar"]
        bess_recs = [r for r in recommendations if r.get("system") == "bess"]

        hvac_savings = 5.0 + (len(hvac_recs) * 4.5)  # kWh base for HVAC
        lighting_savings = lighting_savings_kw  # Calculated above for lighting
        power_savings = len(power_recs) * 2.0  # Modest savings from power optimization
        solar_savings = len(solar_recs) * 1.0  # Alert-based, modest direct savings
        bess_savings = bess_savings_kw  # Calculated above based on dispatch decisions

        energy_savings = hvac_savings + lighting_savings + power_savings + solar_savings + bess_savings
        energy_rate = energy_prices.get("current_rate", 2.28)
        cost_savings = energy_savings * energy_rate
        percentage = min(8.0 + (len(recommendations) * 1.5), 20.0)  # Higher cap with lighting

        reasoning_parts = []
        # Check for various cooling setpoint names
        cooling_point_names = ["cooling_setpoint", "zone_cooling_setpoint", "room_temp_setpoint"]
        if any(any(r["point_name"] == name for name in cooling_point_names) for r in recommendations):
            reasoning_parts.append("zone setpoint adjustment")
        if any("humidity" in r["point_name"].lower() for r in recommendations):
            reasoning_parts.append("humidity optimization")
        # Check for various CHW setpoint names
        chw_point_names = ["chw_supply_temp_setpoint", "supply_temp_setpoint"]
        if any(any(r["point_name"] == name for name in chw_point_names) for r in recommendations):
            reasoning_parts.append("CHW temperature optimization")
        if any("fan_speed" in r["point_name"] for r in recommendations):
            reasoning_parts.append("fan speed optimization")
        if lighting_recs:
            reasoning_parts.append("DALI lighting optimization")
        if power_recs:
            reasoning_parts.append("power equipment optimization")
        if solar_recs:
            reasoning_parts.append("solar PV monitoring")
        if bess_recs:
            reasoning_parts.append("BESS dispatch optimization")

        # Add zone-aware context to reasoning
        zone_context = []
        for rec in recommendations:
            device = next((d for d in hvac_devices if d.id == rec["equipment_id"]), None)
            if device:
                zone_type = self._get_zone_type(device)
                if zone_type and zone_type.value not in zone_context:
                    zone_context.append(zone_type.value)

        reasoning = (
            f"Rising outdoor temperatures ({outdoor_temp}°C) with current conditions require proactive optimization. "
        )
        if reasoning_parts:
            reasoning += f"Recommendations include: {', '.join(reasoning_parts)}. "
        if zone_context:
            reasoning += f"Zone-aware adjustments applied for: {', '.join(zone_context)} zones. "
        if cross_system_recommendations:
            reasoning += f"Coordinated {len(cross_system_recommendations)} cross-system optimizations. "
        reasoning += "All recommendations within safety limits and sorted by zone priority."

        # Build lighting summary
        lighting_summary = None
        if dali_zones:
            total_zones = len(dali_zones)
            occupied_zones = sum(1 for z in dali_zones.values() if z.get("is_occupied"))
            over_lit_count = sum(1 for z in dali_zones.values() if z.get("is_over_lit"))
            lighting_summary = {
                "total_zones": total_zones,
                "occupied_zones": occupied_zones,
                "unoccupied_zones": total_zones - occupied_zones,
                "over_lit_zones": over_lit_count,
                "lighting_recommendations_count": len(lighting_recs),
                "estimated_savings_kw": round(lighting_savings_kw, 2),
            }

        data_quality_penalty = self._calculate_data_quality_penalty(current_conditions)

        return OptimizationRecommendation(
            site_id=site_id,
            timestamp=datetime.now().isoformat(),
            recommendations=recommendations,
            projected_savings={
                "hvac_kwh": round(hvac_savings, 1),
                "lighting_kwh": round(lighting_savings, 1),
                "power_kwh": round(power_savings, 1),
                "solar_kwh": round(solar_savings, 1),
                "bess_kwh": round(bess_savings, 1),
                "energy_kwh": round(energy_savings, 1),
                "total_kwh": round(energy_savings, 1),
                "cost_zar_per_hour": round(cost_savings, 2),
                "percentage_improvement": round(percentage, 1),
            },
            confidence=max(0.1, confidence + (0.05 * len(recommendations)) - data_quality_penalty),
            reasoning=reasoning,
            cross_system_recommendations=cross_system_recommendations if cross_system_recommendations else None,
            lighting_summary=lighting_summary,
            profile=profile.get("name") if profile else None,
            profile_applied=bool(profile),
            data_quality={
                "sources": current_conditions.get("_data_sources", {}),
                "penalty_applied": data_quality_penalty,
            },
        )

    async def analyze_building_load_shedding(
        self,
        site_id: str,
        load_shedding_stage: int,
        current_conditions: Optional[Dict[str, Any]] = None,
    ) -> OptimizationRecommendation:
        """
        Generate load-shedding-aware optimization recommendations.

        During load shedding, we prioritize maintaining comfort in critical zones
        while allowing more aggressive optimization in lower-priority zones.

        Args:
            site_id: Site to analyze
            load_shedding_stage: Current Eskom stage (1-4, higher = more severe)
            current_conditions: Current building conditions (optional)

        Returns:
            OptimizationRecommendation with zone-priority-filtered recommendations
        """
        # Get normal recommendations first
        recommendation = await self.analyze_building(site_id, current_conditions)

        # Priority threshold based on load shedding stage
        # Stage 1: Optimize all zones up to P4 (keep P1, shed P5)
        # Stage 2: Optimize all zones up to P3 (keep P1-P2, shed P4-P5)
        # Stage 3: Optimize all zones up to P2 (keep P1, shed P3-P5)
        # Stage 4: Only maintain P1 (critical zones only)
        priority_threshold = {
            1: 4,  # Keep P1-P4, shed P5 (parking, plant rooms)
            2: 3,  # Keep P1-P3, shed P4-P5 (lobby, parking, plant)
            3: 2,  # Keep P1-P2, shed P3-P5 (executive, server, meeting only)
            4: 1,  # Keep P1 only (executive, server rooms)
        }
        max_priority_to_maintain = priority_threshold.get(load_shedding_stage, 3)

        # Get devices for priority lookup
        devices = await device_manager.list_devices_by_site(site_id)
        device_map = {d.id: d for d in devices}

        # Filter recommendations based on zone priority
        filtered_recs = []
        for rec in recommendation.recommendations:
            device = device_map.get(rec.get("equipment_id"))
            if device:
                zone_priority = self._get_zone_priority(device)
                if zone_priority <= max_priority_to_maintain:
                    # Keep this recommendation (critical zone)
                    filtered_recs.append(rec)
                else:
                    # More aggressive optimization for lower-priority zones
                    # Double the setpoint change for zones being shed
                    modified_rec = rec.copy()
                    current = rec.get("current_value", 22.0)
                    recommended = rec.get("recommended_value", 22.0)
                    change = recommended - current
                    # Double the change for shedding zones (more aggressive)
                    modified_rec["recommended_value"] = round(current + (change * 2), 1)
                    modified_rec["reason"] = f"[LOAD SHEDDING Stage {load_shedding_stage}] " + rec.get("reason", "")
                    filtered_recs.append(modified_rec)

        # Adjust projected savings based on stage (more aggressive = more savings)
        savings_multiplier = 1.0 + (load_shedding_stage * 0.2)  # 1.2x to 1.8x
        adjusted_savings = recommendation.projected_savings.copy()
        adjusted_savings["energy_kwh"] = round(adjusted_savings.get("energy_kwh", 0) * savings_multiplier, 1)
        adjusted_savings["cost_zar_per_hour"] = round(
            adjusted_savings.get("cost_zar_per_hour", 0) * savings_multiplier, 2
        )
        adjusted_savings["percentage_improvement"] = round(
            min(adjusted_savings.get("percentage_improvement", 0) * savings_multiplier, 25.0), 1
        )

        return OptimizationRecommendation(
            site_id=site_id,
            timestamp=datetime.now().isoformat(),
            recommendations=filtered_recs,
            projected_savings=adjusted_savings,
            confidence=recommendation.confidence,
            reasoning=(
                f"Load shedding Stage {load_shedding_stage}: "
                f"Maintaining P1-P{max_priority_to_maintain} "
                f"zones at normal comfort. "
                f"Lower priority zones "
                f"(P{max_priority_to_maintain + 1}-P5) receive "
                f"more aggressive optimization. "
                f"{recommendation.reasoning}"
            ),
        )

    def _get_device_zone_priority(self, device_id: str) -> int:
        """Get zone priority for a device by ID (synchronous helper)."""
        # This is used when we don't have the device object handy
        # Returns default priority if device not found
        return 3

    async def validate_recommendation(
        self,
        site_id: str,
        recommendation: OptimizationRecommendation,
    ) -> Dict[str, Any]:
        """
        Validate a recommendation against safety rules.

        Args:
            site_id: Site ID
            recommendation: Recommendation to validate

        Returns:
            Validation result with allowed flag and details
        """
        try:
            devices = await device_manager.list_devices_by_site(site_id)

            all_allowed = True
            validation_results = []

            for rec in recommendation.recommendations:
                equipment_id = rec.get("equipment_id")
                point_name = rec.get("point_name")
                value = rec.get("recommended_value")

                # Find device
                device = next((d for d in devices if d.id == equipment_id), None)
                if not device:
                    validation_results.append(
                        {
                            "equipment_id": equipment_id,
                            "point_name": point_name,
                            "allowed": False,
                            "reason": f"Device {equipment_id} not found",
                        }
                    )
                    all_allowed = False
                    continue

                # Validate against safety rules
                if not safety_engine._initialized:
                    await safety_engine.initialize()

                safety_result = await safety_engine.validate_control(device, point_name, value)

                validation_results.append(
                    {
                        "equipment_id": equipment_id,
                        "point_name": point_name,
                        "allowed": safety_result["allowed"],
                        "reason": safety_result.get("message", ""),
                        "warnings": safety_result.get("warnings", []),
                    }
                )

                if not safety_result["allowed"]:
                    all_allowed = False

            return {
                "allowed": all_allowed,
                "validation_results": validation_results,
            }

        except Exception as e:
            logger.error(f"Error validating recommendation: {e}")
            return {
                "allowed": False,
                "validation_results": [],
                "error": str(e),
            }


# Singleton instance
_ai_optimizer_instance = None


def get_ai_optimizer():
    """Get or create the singleton AI optimizer instance."""
    global _ai_optimizer_instance
    if _ai_optimizer_instance is None:
        _ai_optimizer_instance = AIOptimizerService()
    return _ai_optimizer_instance
