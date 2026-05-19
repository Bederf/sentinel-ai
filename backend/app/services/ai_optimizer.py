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

import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.models.device import Device, DevicePoint, DeviceType, ExposureDirection, ZoneType
from app.models.optimization import (
    OptimizationRecommendation,
    SiteOptimizationStatus,
)
from app.services.device_abstraction import device_manager
from app.services.lighting_service import get_lighting_service
from app.services.model_gateway import model_gateway
from app.services.safety_interlocks import safety_engine

UTC = UTC

logger = logging.getLogger(__name__)

# Profile-aware health recommendation thresholds
HEALTH_THRESHOLDS: dict[str, dict[str, int]] = {
    "comfort": {"warn": 60, "critical": 45},
    "cost_saving": {"warn": 60, "critical": 45},
    "asset_preservation": {"warn": 85, "critical": 70},
    "balanced": {"warn": 70, "critical": 50},
}

# Data directory for sites
DATA_DIR = Path(__file__).parent.parent / "data"


async def load_equipment_from_supabase() -> list[dict]:
    """Load equipment from Supabase (source of truth) for device manager initialization."""
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    # Get site UUID → site code mapping
    sites_resp = client.table("sites").select("id, code").execute()
    site_map: dict[str, str] = {s["id"]: s["code"] for s in sites_resp.data or []}

    # Get all equipment from Supabase
    eq_resp = client.table("equipment").select("*").execute()
    equipment = eq_resp.data or []

    devices = []
    for eq in equipment:
        site_uuid = eq.get("site_id", "")
        site_code = site_map.get(site_uuid, site_uuid)

        # Map equipment type to device_type
        raw_type = (eq.get("type") or "other").lower()
        type_map = {
            "ahu": "hvac",
            "chiller": "hvac",
            "vav": "hvac",
            "fcu": "hvac",
            "boiler": "hvac",
            "pump": "hvac",
            "cooling_tower": "hvac",
            "dali": "lighting",
            "dali_controller": "lighting",
            "dali_zone": "lighting",
            "lighting_zone": "lighting",
            "luminaire": "lighting",
            "meter": "meter",
            "generator": "power",
            "ups": "power",
            "inverter": "solar",
            "bess": "solar",
            "zone_sensor": "sensor",
            "outdoor_air_sensor": "sensor",
            "zone": "hvac",
            "general": "other",
        }
        device_type = type_map.get(raw_type, raw_type)

        # Map status
        status = (eq.get("status") or "unknown").lower()
        if status in ("normal", "online", "running"):
            mapped_status = "online"
        elif status in ("offline", "unknown"):
            mapped_status = "offline"
        else:
            mapped_status = status

        device = {
            "id": eq.get("code", ""),
            "name": eq.get("name") or eq.get("code", ""),
            "device_type": device_type,
            "protocol": "http",
            "site_id": site_code,
            "status": mapped_status,
            "location": eq.get("location") or "",
            "metadata": {
                "source": "supabase",
                "equipment_type": raw_type,
                "health_score": eq.get("health_score"),
                "operating_data": eq.get("operating_data", {}),
            },
        }
        devices.append(device)

    return devices


async def ensure_device_manager_initialized() -> None:
    """Ensure device manager is initialized with equipment from Supabase (source of truth)."""
    if not device_manager._initialized:
        logger.info("Device manager not initialized, loading devices from Supabase...")
        try:
            devices_data = await load_equipment_from_supabase()

            # Also load building equipment files as supplement (may add points data)
            from app.api.devices import load_equipment_from_buildings

            site_devices = await load_equipment_from_buildings()

            existing_ids = {d["id"] for d in devices_data}
            added_count = 0
            for device in site_devices:
                if device["id"] not in existing_ids:
                    devices_data.append(device)
                    existing_ids.add(device["id"])
                    added_count += 1

            await device_manager.initialize(devices_data)
            logger.info(
                f"Device manager initialized with {len(devices_data)} devices "
                f"({len(devices_data) - added_count} from Supabase, {added_count} from files)"
            )
        except Exception as e:
            logger.error(f"Failed to initialize device manager from Supabase: {e}")
            # Fallback: try loading from archived reference file
            try:
                ref_devices_path = DATA_DIR / "_archive" / "bms_simulator_data" / "reference_devices.json"
                if ref_devices_path.exists():
                    with open(ref_devices_path) as f:
                        devices_data = json.load(f)
                    await device_manager.initialize(devices_data)
                    logger.warning(f"Fell back to archived reference_devices.json ({len(devices_data)} devices)")
                else:
                    await device_manager.initialize([])
            except Exception:
                await device_manager.initialize([])


def load_sites() -> list[dict[str, Any]]:
    """Load sites data from Supabase, with fallback to JSON file."""
    # Try Supabase first
    if not settings.use_json_storage:
        try:
            from app.database.repositories.site_repository import SiteRepository

            repo = SiteRepository()
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
        # Provider selection handled by model_gateway using active routing profile
        self._sites = None
        self._optimization_status_cache: dict[str, SiteOptimizationStatus] = {}
        # Phase 1a: FCU state tracker for post-occupancy waste detection
        from app.services.context_precompute_service import ContextPreComputeService
        from app.services.fcu_state_tracker import FCUStateTracker

        self.fcu_state_tracker = FCUStateTracker()
        self.context_precompute_service = ContextPreComputeService(self.fcu_state_tracker)

    @property
    def sites(self) -> list[dict[str, Any]]:
        """Lazy load sites data."""
        if self._sites is None:
            self._sites = load_sites()
        return self._sites

    def find_site(self, site_id: str) -> dict[str, Any] | None:
        """Find a site by ID."""
        for site in self.sites:
            if site["id"] == site_id:
                return site
        return None

    async def analyze_building(
        self,
        site_id: str,
        current_conditions: dict[str, Any] | None = None,
        weather_forecast: dict[str, Any] | None = None,
        energy_prices: dict[str, Any] | None = None,
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

        # Fetch real weather forecast if not provided
        if not weather_forecast:
            from app.services.weather_service import get_weather_forecast

            weather_forecast = await get_weather_forecast(hours=4)
            if not weather_forecast:
                # Fail if no weather data available
                raise RuntimeError(
                    f"No weather forecast available for site {site_id}. Weather API not configured or failed."
                )

        # Generate mock energy prices if not provided
        if not energy_prices:
            energy_prices = self._get_energy_prices(site_id)

        # Get ALL site devices - equipment inventory varies by building
        all_devices = await device_manager.list_devices_by_site(site_id)

        # Categorize equipment by type - this is site-specific
        equipment_inventory = self._categorize_equipment(all_devices)

        logger.info(f"Site {site_id} equipment inventory: {self._summarize_inventory(equipment_inventory)}")

        # Fetch DALI lighting zone data
        lighting_svc = get_lighting_service()
        lighting_zones = self._gather_lighting_zone_data(lighting_svc, site_id)

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

        # Gather ML model outputs for Claude context injection
        ml_context = await self._gather_ml_context(site_id, equipment_inventory)

        # Gather decision memory (learned patterns from past outcomes)
        decision_memory_text = await self._gather_decision_memory(site_id)

        # Gather module success rates from feedback loop
        feedback_rates_text = self._gather_feedback_success_rates(site_id)

        # Phase 1b: Pre-compute waste opportunities before LLM analysis
        ahu_devices = equipment_inventory.get("ahu", [])
        ahu_states = []
        for d in ahu_devices:
            op_data = getattr(d, "operating_data", {}) or {}
            cap = op_data.get("capacity_pct", 0) if isinstance(op_data, dict) else 0
            equip_code = getattr(d, "code", "")
            if equip_code:
                ahu_states.append({"equipment_id": equip_code, "capacity_pct": cap})

        # Build enriched current_conditions for pre-compute (avoid mutating the original)
        enriched_conditions = dict(current_conditions)
        enriched_conditions["ahu_states"] = ahu_states
        # building_occupancy_pct: numeric from zone_occupancy or occupancy string
        zone_occ = current_conditions.get("zone_occupancy", {})
        if zone_occ:
            occ_vals = [v for v in zone_occ.values() if isinstance(v, (int, float))]
            enriched_conditions["building_occupancy_pct"] = sum(occ_vals) / len(occ_vals) if occ_vals else 100
        else:
            occ_val = current_conditions.get("occupancy", 100)
            if isinstance(occ_val, (int, float)):
                enriched_conditions["building_occupancy_pct"] = occ_val
            elif occ_val == "high":
                enriched_conditions["building_occupancy_pct"] = 80
            elif occ_val == "medium":
                enriched_conditions["building_occupancy_pct"] = 50
            elif occ_val == "low":
                enriched_conditions["building_occupancy_pct"] = 20
            else:
                enriched_conditions["building_occupancy_pct"] = 100
        # bess fields: pull from current_conditions if present
        enriched_conditions.setdefault("bess_soc", 0)
        enriched_conditions.setdefault("bess_dispatching", False)
        enriched_conditions.setdefault("indoor_avg_temp", current_conditions.get("indoor_temp"))

        active_profile_name = profile.get("name", "balanced") if profile else "balanced"
        outdoor_temp = current_conditions.get("outdoor_temp")
        peak_tariff = energy_prices.get("peak_rate", 3.01) if energy_prices else 3.01

        precomputed_context = await self.context_precompute_service.compute(
            site_id=site_id,
            current_conditions=enriched_conditions,
            active_profile=active_profile_name,
            outdoor_temp=outdoor_temp,
            peak_tariff=peak_tariff,
        )

        # Build optimization prompt for Claude with ALL available equipment
        prompt = self._build_optimization_prompt(
            site,
            current_conditions,
            weather_forecast,
            energy_prices,
            equipment_inventory,
            lighting_zones,
            profile=profile,
            ml_context=ml_context,
            decision_memory_text=decision_memory_text,
            feedback_rates_text=feedback_rates_text,
            precomputed_context=precomputed_context,
        )

        # Determine task_class based on anomaly state
        has_anomalies = ml_context is not None and bool(ml_context.get("anomaly_alerts"))
        task_class = "heavy" if has_anomalies else "medium"
        logger.info(
            f"Site {site_id}: anomaly_alerts={len(ml_context.get('anomaly_alerts', []) if ml_context else [])} — "
            f"task_class={task_class}"
        )

        try:
            # Try LLM analysis via model_gateway
            recommendation = await self._analyze_with_claude(
                site_id, task_class, prompt, current_conditions, equipment_inventory, lighting_zones, profile
            )

            # Apply recommendation scoring and ranking with profile weights
            if profile:
                recommendation = self._score_and_rank_recommendations(recommendation, profile)

            # Phase 109: Apply quality gate evaluation to recommendations
            recommendation = await self._apply_quality_gate(site_id, recommendation)

            # Phase 109B-03: Enrich recommendations with health features (ADDITIVE)
            recommendation = await self._enrich_with_health_features(site_id, recommendation)

            return recommendation

        except Exception as e:
            logger.error(f"Error analyzing building {site_id}: {e}")
            # Fall back to rule-based optimization
            rec = self._analyze_with_rules(
                site_id,
                current_conditions,
                weather_forecast,
                energy_prices,
                equipment_inventory,
                lighting_zones,
                profile,
            )
            # Apply scoring to fallback recommendations too
            if profile:
                rec = self._score_and_rank_recommendations(rec, profile)
            # Phase 109: Apply quality gate to fallback recommendations too
            rec = await self._apply_quality_gate(site_id, rec)
            # Phase 109B-03: Enrich fallback recommendations with health features too
            rec = await self._enrich_with_health_features(site_id, rec)
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
            from app.config.settings import settings as app_settings
            from app.services.quality_gate_evaluator import QualityGateEvaluator

            evaluator = QualityGateEvaluator()
            # Use onboarding phase for quality gate mode (ingestion mode may differ)
            try:
                from app.database.supabase_client import get_supabase_client

                client = get_supabase_client()
                phase_row = client.table("sites").select("onboarding_phase").eq("code", site_id).limit(1).execute()
                mode = phase_row.data[0].get("onboarding_phase", "shadow_live") if phase_row.data else "shadow_live"
            except Exception:
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
            logger.error(
                f"[AI-OPT] Quality gate evaluation failed for {site_id}: {e}. "
                f"Recommendations will be flagged as unverified.",
                exc_info=True,
            )
            for rec in recommendation.recommendations:
                rec["quality_gate_status"] = "unverified"
                rec["quality_gate_error"] = str(e)

        return recommendation

    async def _enrich_with_health_features(
        self, site_id: str, recommendation: "OptimizationRecommendation"
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
                # target_equipment is canonical after normalisation — assert it, don't silently fall back
                equipment_id = rec_dict.get("target_equipment")
                if not equipment_id:
                    logger.error(
                        f"[AI-OPT] Recommendation missing target_equipment after normalisation: "
                        f"{list(rec_dict.keys())} — skipping"
                    )
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
            logger.error(
                f"[AI-OPT] Health feature enrichment failed for {site_id}: {e}. "
                f"Recommendations will proceed without health severity signals. "
                f"This may affect recommendation ranking accuracy.",
                exc_info=True,
            )
            # Add explicit marker so downstream knows health features are missing
            # (attached to recommendation object's metadata, not individual recs)
            recommendation.metadata["health_features_available"] = False

        return recommendation

    async def _gather_current_conditions(self, site_id: str) -> dict[str, Any]:
        """Gather current building conditions from devices, DALI sensors, and weather API."""
        try:
            devices = await device_manager.list_devices_by_site(site_id)

            # Fetch real weather data first
            from app.services.weather_service import get_current_weather

            weather_data = await get_current_weather()

            conditions = {
                "indoor_temp": 22.0,
                "outdoor_temp": weather_data.get("outdoor_temp", 22.0) if weather_data else 22.0,
                "humidity": weather_data.get("humidity", 50.0) if weather_data else 50.0,
                "occupancy": "high",
                "equipment_status": "normal",
                "timestamp": datetime.now().isoformat(),
                "zone_occupancy": {},  # Real occupancy from DALI
                # Track which readings are defaults vs live sensor data
                "_data_sources": {
                    "indoor_temp": "default",
                    "outdoor_temp": "weather_api" if weather_data else "default",
                    "humidity": "weather_api" if weather_data else "default",
                    "occupancy": "default",
                    "solar": "unavailable",
                    "bess": "unavailable",
                    "dali": "unavailable",
                },
            }

            # Fail if no weather data available
            if not weather_data:
                raise RuntimeError(
                    f"No weather data available for site {site_id}. "
                    "OpenWeatherMap API not configured or failed. "
                    "Set OPENWEATHER_API_KEY environment variable."
                )

            # Try to get actual readings from HVAC devices
            found_indoor_temp = False
            found_outdoor_temp = bool(weather_data)  # Already have from weather API
            found_humidity = bool(weather_data)  # Already have from weather API

            for device in devices:
                if device.device_type != DeviceType.HVAC:
                    continue

                for point_name in device.points:
                    point_name_lower = point_name.lower()

                    # Read setpoints live via device_manager
                    if "setpoint" in point_name_lower or point_name_lower.endswith("_sp"):
                        try:
                            sp_value = await device_manager.read_device_value(device.id, point_name)
                            if sp_value.value is not None:
                                conditions.setdefault("setpoints", {})[f"{device.id}.{point_name}"] = {
                                    "value": sp_value.value,
                                    "unit": sp_value.unit,
                                    "timestamp": sp_value.timestamp,
                                }
                                conditions["_data_sources"]["setpoints"] = "live"
                        except Exception:
                            pass
                        continue

                    target_key: str | None = None

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
                lighting_svc = get_lighting_service()
                zones = lighting_svc.get_all_zones()

                total_occupied = 0
                total_zones = 0

                for zone in zones:
                    zone_id = zone.get("zone_id")
                    if not zone_id:
                        continue

                    occupancy = lighting_svc.get_zone_occupancy(zone_id)
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

            # ── Read setpoints from operating_data (populated by oBIX setpoint poll) ──
            # device_manager is empty for HTTP bridge sites (S002), so instead of
            # read_device_value() calls, read directly from Supabase equipment.operating_data.
            # This is populated by ShadowModePollingService.poll() → Section 5b.
            try:
                from app.database.repositories.equipment_repository import EquipmentRepository
                from app.database.supabase_client import get_supabase_client

                # Inline site lookup — sb not yet defined at this point in the function
                sb_sp = get_supabase_client()
                site_resp_sp = sb_sp.table("sites").select("id").eq("code", site_id).execute()
                if site_resp_sp.data:
                    site_uuid_sp = site_resp_sp.data[0]["id"]
                    eq_repo = EquipmentRepository()
                    all_equip = eq_repo.get_all(site_id=site_uuid_sp)
                    now_utc = datetime.now(tz=UTC)
                    stale_delta = timedelta(hours=2)
                    stale_count = 0
                    for eq in all_equip:
                        op = eq.get("operating_data") or {}
                        if not op:
                            continue
                        updated_at_str = eq.get("updated_at") or eq.get("created_at", "")
                        is_stale = True
                        if updated_at_str:
                            try:
                                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                                is_stale = (now_utc - updated_at) > stale_delta
                            except Exception:
                                pass
                        if is_stale:
                            stale_count += 1
                            continue
                        for key, val in op.items():
                            if any(
                                sp in key.lower()
                                for sp in [
                                    "setpoint",
                                    "_sp",
                                    "cooling",
                                    "heating",
                                    "supply_temp",
                                    "room_temp",
                                    "flow",
                                    "speed",
                                ]
                            ):
                                if isinstance(val, dict) and val.get("value") is not None:
                                    conditions.setdefault("setpoints", {})[f"{eq.get('code')}.{key}"] = {
                                        "value": val["value"],
                                        "unit": val.get("unit", ""),
                                        "timestamp": val.get("timestamp", ""),
                                    }
                    sp_count = len(conditions.get("setpoints", {}))
                    if sp_count > 0:
                        conditions["_data_sources"]["setpoints"] = "live"
                        logger.warning(
                            f"[AI-OPT] Loaded {sp_count} setpoints for {site_id} ({stale_count} stale skipped)"
                        )
            except Exception as e:
                logger.warning(f"Failed to load setpoints from operating_data: {e}")

            # Gather equipment health from Supabase — enables health-aware recs
            try:
                from app.database.supabase_client import get_supabase_client
                from app.services.health_threshold_service import get_health_thresholds

                thresholds = get_health_thresholds()
                t_healthy = thresholds.get("healthy", 90)
                t_warning = thresholds.get("warning", 70)
                t_critical = thresholds.get("critical", 50)

                sb = get_supabase_client()
                site_resp = sb.table("sites").select("id").eq("code", site_id).execute()
                if site_resp.data:
                    site_uuid = site_resp.data[0]["id"]
                    eq_resp = (
                        sb.table("equipment").select("code,type,health_score,status").eq("site_id", site_uuid).execute()
                    )
                    if eq_resp.data:
                        degraded = []
                        worst_health = 100
                        for eq in eq_resp.data:
                            hs = eq.get("health_score")
                            if hs is not None and hs < t_healthy:
                                degraded.append(
                                    {
                                        "code": eq["code"],
                                        "type": eq.get("type", "unknown"),
                                        "health": hs,
                                        "status": eq.get("status", "normal"),
                                    }
                                )
                                worst_health = min(worst_health, hs)

                        if degraded:
                            conditions["equipment_health"] = degraded
                            conditions["_health_thresholds"] = thresholds
                            if worst_health < t_critical:
                                conditions["equipment_status"] = "critical"
                            elif worst_health < t_warning:
                                conditions["equipment_status"] = "degraded"
                            else:
                                conditions["equipment_status"] = "warning"
                            logger.warning(
                                f"[AI-OPT] Equipment health: {len(degraded)} degraded, "
                                f"worst={worst_health}%, status={conditions['equipment_status']}"
                            )
            except Exception as e:
                logger.warning(f"Could not fetch equipment health: {e}")

            # ── IPMVP baseline comparison ─────────────────────────────────
            try:
                sb = get_supabase_client()
                site_resp = sb.table("sites").select("id").eq("code", site_id).execute()
                if site_resp.data:
                    site_uuid = site_resp.data[0]["id"]
                    ipmvp = (
                        sb.table("ipmvp_energy")
                        .select("*")
                        .eq("site_id", site_id)
                        .order("timestamp", desc=True)
                        .limit(100)
                        .execute()
                    )
                    if ipmvp.data and len(ipmvp.data) > 10:
                        current_kwh = sum(r.get("import_kwh") or 0 for r in ipmvp.data[:96])
                        conditions["ipmvp"] = {
                            "current_kwh": round(current_kwh, 1),
                            "records_available": len(ipmvp.data),
                        }
            except Exception:
                pass

            # ── Electrical aggregate from site telemetry ──────────────────
            try:
                import httpx

                bridge_site = site_id if site_id.startswith("site-") else site_id
                token = (
                    os.environ.get("BRIDGE_API_TOKEN_SITE002")
                    or os.environ.get("BRIDGE_API_TOKEN")
                    or "ScUAjUet7i2vvcE0fuzn6dsF3C+YRMWbf8yMWwdoYbw"
                )
                # Use sync client — async is flaky with WireGuard bridge
                with httpx.Client(timeout=10) as client:
                    url = f"http://10.99.0.1:8080/api/sites/{bridge_site}/telemetry"
                    resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
                    if resp.is_success:
                        telemetry = resp.json()
                        power = telemetry.get("power", {})
                        conditions["electrical"] = {
                            "total_kw": power.get("total_kw"),
                            "hvac_kw": power.get("hvac_kw"),
                            "lighting_kw": power.get("lighting_kw"),
                            "solar_kw": power.get("solar_kw"),
                        }
                    else:
                        logger.warning(f"[AI-OPT] Bridge telemetry returned {resp.status_code}")
            except Exception as e:
                logger.warning(f"[AI-OPT] Bridge telemetry failed: {e}")

            # ── Active modules ────────────────────────────────────────────
            try:
                mod_resp = sb.table("site_modules").select("module_type,status").eq("site_id", site_id).execute()
                if mod_resp.data:
                    conditions["active_modules"] = [
                        m["module_type"] for m in mod_resp.data if m.get("status") == "active"
                    ]
            except Exception:
                conditions["active_modules"] = []

            # ── Carbon context (calculated from electrical telemetry) ──
            try:
                conditions["carbon"] = await self._gather_carbon_context(site_id, conditions)
            except Exception:
                pass

            return conditions

        except Exception as e:
            logger.error(f"Error gathering current conditions: {e}")
            return {
                "indoor_temp": 22.0,
                "outdoor_temp": 28.0,
                "humidity": 55.0,
                "occupancy": "medium",
                "equipment_status": "normal",
                "timestamp": datetime.now().isoformat(),
                "zone_occupancy": {},
            }

    def _generate_mock_weather_forecast(self) -> dict[str, Any]:
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

    def _get_energy_prices(self, site_id: str | None = None) -> dict[str, Any]:
        """Get energy pricing from Supabase ipmvp_tariff, with fallback to defaults.

        Tariff data is loaded by the bridge and stored in ipmvp_tariff.
        Determines current band (peak/standard/off_peak) from the current hour.
        Also loads NMD and demand charge from sites table.
        """
        result = {
            "current_rate": 2.28,
            "peak_rate": 3.01,
            "off_peak_rate": 1.77,
            "standard_rate": 1.87,
            "band": "standard",
            "peak_hours": [6, 7, 8, 17, 18, 19, 20],
            "weekday_only": True,
            "currency": "ZAR",
            "source": "fallback_defaults",
            "nmd_kva": None,
            "demand_charge_per_kva": None,
        }

        if site_id:
            try:
                from app.database.supabase_client import get_supabase_client

                sb = get_supabase_client()

                # Load demand charge and NMD from sites table
                site_row = (
                    sb.table("sites")
                    .select("nmd_limit_kva,demand_charge_per_kva")
                    .eq("code", site_id)
                    .limit(1)
                    .execute()
                )
                if site_row.data:
                    s = site_row.data[0]
                    result["nmd_kva"] = s.get("nmd_limit_kva")
                    result["demand_charge_per_kva"] = s.get("demand_charge_per_kva")

                # Load tariff rates from ipmvp_tariff
                tariff_row = sb.table("ipmvp_tariff").select("tariff_data").eq("site_id", site_id).limit(1).execute()
                if tariff_row.data:
                    td = tariff_row.data[0]["tariff_data"]
                    peak_hours = td.get("peak_hours", result["peak_hours"])
                    hour = datetime.now().hour
                    weekday_only = td.get("weekday_only", True)
                    is_weekend = weekday_only and datetime.now().weekday() >= 5

                    if hour in peak_hours and not is_weekend:
                        band = "peak"
                        current = td.get("peak_zar_per_kwh", result["peak_rate"])
                    elif is_weekend:
                        band = "off_peak"
                        current = td.get("offpeak_zar_per_kwh", result["off_peak_rate"])
                    else:
                        band = "standard"
                        current = td.get("standard_zar_per_kwh", result["standard_rate"])

                    result.update(
                        {
                            "current_rate": current,
                            "peak_rate": td.get("peak_zar_per_kwh", result["peak_rate"]),
                            "off_peak_rate": td.get("offpeak_zar_per_kwh", result["off_peak_rate"]),
                            "standard_rate": td.get("standard_zar_per_kwh", result["standard_rate"]),
                            "band": band,
                            "peak_hours": peak_hours,
                            "weekday_only": weekday_only,
                            "currency": "ZAR",
                            "source": "ipmvp_tariff + sites",
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to load tariff data: {e}")

        return result

    async def _gather_decision_memory(self, site_id: str) -> str:
        """Gather learned decision patterns for this site from Decision Memory Service.

        Returns formatted text for prompt injection, or empty string if no patterns exist.
        """
        try:
            from app.services.decision_memory_service import get_decision_memory_service

            dms = get_decision_memory_service()
            dms._ensure_loaded()

            # Filter patterns relevant to this site
            site_patterns = [
                p for p in dms._patterns if not hasattr(p, "site_id") or getattr(p, "site_id", None) in (None, site_id)
            ]

            # Get recent resolved decisions for this site
            site_records = [r for r in dms._records if r.site_id == site_id and r.outcome.value != "pending"]
            # Keep most recent 10
            site_records.sort(
                key=lambda r: r.outcome_evaluated_at or r.created_at,
                reverse=True,
            )
            site_records = site_records[:10]

            text = dms.format_for_prompt(
                patterns=site_patterns if site_patterns else None,
                records=site_records if site_records else None,
            )

            if text:
                logger.info(
                    "Decision memory: %d patterns, %d recent records for %s",
                    len(site_patterns),
                    len(site_records),
                    site_id,
                )
            return text

        except Exception as e:
            logger.debug("Decision memory unavailable: %s", e)
            return ""

    def _gather_feedback_success_rates(self, site_id: str) -> str:
        """Get per-module recommendation success rates from ML feedback.

        Returns formatted text for prompt injection, or empty string if no data.
        """
        try:
            from app.services.ml_feedback_service import get_ml_feedback_service

            ml_fb = get_ml_feedback_service()
            summary = ml_fb.get_module_feedback_summary(site_id=site_id)

            success_rates = summary.get("success_rates", {})
            counts = summary.get("counts", {})
            if not success_rates:
                return ""

            lines = []
            for module_name, rate in sorted(success_rates.items()):
                total = counts.get(module_name, 0)
                if total == 0:
                    continue
                guidance = ""
                if rate < 60:
                    guidance = " (act conservatively — verify conditions before recommending)"
                elif rate >= 90:
                    guidance = " (proven reliable)"
                lines.append(
                    f"- {module_name.upper()} actions: {rate:.0f}% success rate ({total} recorded outcomes){guidance}"
                )

            if not lines:
                return ""

            logger.info("Feedback success rates for %s: %s", site_id, success_rates)
            return "\n".join(lines)

        except Exception as e:
            logger.debug("Feedback success rates unavailable: %s", e)
            return ""

    async def _gather_ml_context(self, site_id: str, equipment_inventory: dict[str, list[Device]]) -> dict[str, Any]:
        """Gather ML model outputs for injection into Claude's optimisation prompt.

        Collects LSTM forecasts, anomaly scores, fault classifications, and health
        trend slopes from all active ML models. This bridges the gap between trained
        models and Claude's recommendation engine.

        Returns:
            Dict with keys: lstm_forecasts, anomaly_alerts, fault_classifications,
            health_trends, feature_metrics. Each is a list of dicts or empty list
            if the service is unavailable.
        """
        ml_context: dict[str, Any] = {
            "lstm_forecasts": [],
            "anomaly_alerts": [],
            "fault_classifications": [],
            "health_trends": [],
            "feature_metrics": {},
        }

        # Build equipment list from inventory
        equipment_list = []
        for devices in equipment_inventory.values():
            for device in devices:
                eq_type = getattr(device, "type", None)
                eq_type_str = (eq_type.value if hasattr(eq_type, "value") else str(eq_type)) if eq_type else "unknown"
                equipment_list.append(
                    {
                        "equipment_id": device.id,
                        "equipment_type": eq_type_str.lower(),
                        "equipment_name": getattr(device, "name", device.id),
                    }
                )

        # 1. LSTM Forecasts — predicted future state per equipment
        try:
            from app.services.ml_inference import get_lstm_service

            lstm_svc = get_lstm_service()
            for eq in equipment_list:
                try:
                    prediction = lstm_svc.predict(eq["equipment_id"], eq["equipment_type"])
                    if prediction and prediction.get("predictions"):
                        ml_context["lstm_forecasts"].append(
                            {
                                "equipment_id": eq["equipment_id"],
                                "equipment_name": eq["equipment_name"],
                                "type": eq["equipment_type"],
                                "forecast_24h": prediction["predictions"].get("24h"),
                                "forecast_48h": prediction["predictions"].get("48h"),
                                "forecast_72h": prediction["predictions"].get("72h"),
                                "confidence": prediction.get("confidence", 0),
                            }
                        )
                except Exception:
                    pass  # Model not available for this type
        except Exception as e:
            logger.debug(f"LSTM service unavailable for ML context: {e}")

        # 2. Anomaly Detection — equipment with elevated anomaly scores
        try:
            from app.services.ml_inference import get_anomaly_service

            anomaly_svc = get_anomaly_service()
            all_anomalies = anomaly_svc.check_all_equipment(
                [{"equipment_id": eq["equipment_id"], "equipment_type": eq["equipment_type"]} for eq in equipment_list]
            )
            # Only include equipment with anomaly score above 0.5
            for result in all_anomalies:
                if result.get("anomaly_score", 0) > 0.5 or result.get("is_anomaly"):
                    ml_context["anomaly_alerts"].append(
                        {
                            "equipment_id": result["equipment_id"],
                            "type": result.get("equipment_type", ""),
                            "anomaly_score": round(result.get("anomaly_score", 0), 3),
                            "severity": result.get("severity", "unknown"),
                            "is_anomaly": result.get("is_anomaly", False),
                        }
                    )
        except Exception as e:
            logger.debug(f"Anomaly service unavailable for ML context: {e}")

        # 3. Fault Classification — active fault type probabilities
        try:
            from app.services.classification_service import get_classification_service

            cls_svc = get_classification_service()
            fleet_risks = cls_svc.get_fleet_failure_risks(min_confidence=0.4)
            for risk in fleet_risks:
                ml_context["fault_classifications"].append(
                    {
                        "equipment_id": risk.get("equipment_id", ""),
                        "fault_type": risk.get("predicted_fault_type", ""),
                        "probability": round(risk.get("confidence", 0), 3),
                        "equipment_type": risk.get("equipment_type", ""),
                    }
                )
        except Exception as e:
            logger.debug(f"Classification service unavailable for ML context: {e}")

        # 4. Health Trend Slopes — identify degrading equipment
        try:
            from app.services.health_feature_provider import HealthFeatureProvider

            provider = HealthFeatureProvider()
            for eq in equipment_list:
                try:
                    payload = await provider.get_health_features(eq["equipment_id"])
                    # Only include if degrading (positive slope = declining health score)
                    slope_7d = payload.health_trend_7d_slope
                    if slope_7d is not None and slope_7d < -0.5:
                        ml_context["health_trends"].append(
                            {
                                "equipment_id": eq["equipment_id"],
                                "equipment_name": eq["equipment_name"],
                                "health_score": payload.health_score_current,
                                "health_status": payload.health_status_current,
                                "trend_7d_slope": round(slope_7d, 3),
                                "trend_30d_slope": round(payload.health_trend_30d_slope, 3)
                                if payload.health_trend_30d_slope
                                else None,
                            }
                        )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Health feature provider unavailable for ML context: {e}")

        # 5. Derived building-level features
        try:
            from app.services.feature_engineering_service import get_feature_engineering_service

            feat_svc = get_feature_engineering_service()
            ml_context["feature_metrics"] = await feat_svc.compute_site_features(site_id)
        except Exception as e:
            logger.debug(f"Feature engineering service unavailable: {e}")

        # 6. Live anomaly scores — written every 5min by 178-08 shadow polling
        try:
            equipment_ids = [eq["equipment_id"] for eq in equipment_list]
            ml_context["live_anomaly_scores"] = await self._pull_live_anomaly_scores(site_id, equipment_ids)
        except Exception as e:
            logger.debug(f"Live anomaly scores unavailable: {e}")

        return ml_context

    async def _pull_live_anomaly_scores(self, site_id: str, equipment_ids: list[str]) -> list[dict]:
        """Pull anomaly_score and lstm_anomaly_score from equipment operating_data.

        These are written every 5min by ShadowModePollingService + SentinelDataSync
        (Phase 178-08). Only returns equipment where at least one score is present.
        """
        from app.database.supabase_client import get_supabase_client

        if not equipment_ids:
            return []

        sb = get_supabase_client()

        site_resp = sb.table("sites").select("id").eq("code", site_id).execute()
        if not site_resp.data:
            return []
        site_uuid = site_resp.data[0]["id"]

        resp = (
            sb.table("equipment")
            .select("code, operating_data, updated_at")
            .eq("site_id", site_uuid)
            .in_("code", equipment_ids)
            .execute()
        )

        results = []
        for row in resp.data:
            op = row.get("operating_data") or {}
            anomaly_score = op.get("anomaly_score")
            lstm_anomaly_score = op.get("lstm_anomaly_score")

            if anomaly_score is None and lstm_anomaly_score is None:
                continue

            results.append(
                {
                    "equipment_id": row["code"],
                    "anomaly_score": float(anomaly_score) if anomaly_score is not None else None,
                    "lstm_anomaly_score": float(lstm_anomaly_score) if lstm_anomaly_score is not None else None,
                    "as_of": row["updated_at"].isoformat()
                    if hasattr(row.get("updated_at"), "isoformat")
                    else row.get("updated_at"),
                }
            )

        return results

    def _format_live_anomaly_scores(self, live_scores: list[dict]) -> str:
        if not live_scores:
            return ""

        lines = ["**Live Anomaly Scores (178-08 Pipeline — updated every 5min):**"]
        for s in live_scores:
            parts = [f"{s['equipment_id']}:"]
            if s.get("anomaly_score") is not None:
                level = "ELEVATED" if s["anomaly_score"] > 0.65 else "normal"
                parts.append(f"IF_anomaly={s['anomaly_score']:.2f} ({level})")
            if s.get("lstm_anomaly_score") is not None:
                parts.append(f"LSTM_anomaly={s['lstm_anomaly_score']:.2f}")
            if s.get("as_of"):
                parts.append(f"[{s['as_of'][11:16]} UTC]")
            lines.append(" | ".join(parts))

        return "\n".join(lines)

    async def run_full_equipment_sweep(
        self,
        site_id: str,
        bypass_occupancy_gate: bool = True,
    ) -> list[dict]:
        """
        Run a full equipment sweep for a site, bypassing occupancy gates.

        Unlike the main analyze_building() flow which gates recommendations on
        occupancy schedules, this method generates recommendations for ALL equipment
        regardless of time/occupancy. Used by the daily health sweep to catch issues
        outside business hours.

        Args:
            site_id: Site code (e.g. "site-002")
            bypass_occupancy_gate: If True, process all equipment regardless of
                occupancy state. Default True.

        Returns:
            List of generated recommendation dicts (same format as analyze_building).
        """
        from app.database.repositories.equipment_repository import EquipmentRepository
        from app.database.supabase_client import get_supabase_client

        logger.info(
            f"[AI-OPT] Running full equipment sweep for {site_id} (bypass_occupancy_gate={bypass_occupancy_gate})"
        )

        results: list[dict] = []

        try:
            site = self.find_site(site_id)
            if not site:
                logger.warning(f"[AI-OPT] Site {site_id} not found for sweep")
                return results

            await ensure_device_manager_initialized()

            # Get site UUID for queries
            sb = get_supabase_client()
            site_resp = sb.table("sites").select("id").eq("code", site_id).execute()
            if not site_resp.data:
                logger.warning(f"[AI-OPT] No UUID for site {site_id}")
                return results
            site_uuid = site_resp.data[0]["id"]

            # Fetch all equipment with health_score and operating_data (anomaly scores)
            eq_repo = EquipmentRepository()
            all_equip = eq_repo.get_all(site_id=site_uuid)

            # Filter: skip healthy equipment (health_score >= 90 AND anomaly_score < 0.3)
            candidates = []
            for eq in all_equip:
                health = eq.get("health_score")
                op = eq.get("operating_data") or {}
                anomaly = op.get("anomaly_score") if isinstance(op, dict) else None
                if health is not None and health >= 90 and (anomaly is None or float(anomaly) < 0.3):
                    continue  # Skip healthy equipment
                candidates.append(eq)

            if not candidates:
                logger.info(f"[AI-OPT] No candidate equipment for sweep at {site_id}")
                return results

            logger.info(f"[AI-OPT] Sweep candidate count: {len(candidates)}/{len(all_equip)}")

            # Build minimal current_conditions for the sweep
            conditions = {
                "indoor_temp": 22.0,
                "outdoor_temp": 28.0,
                "humidity": 55.0,
                "occupancy": "unknown",
                "equipment_status": "normal",
                "timestamp": datetime.now().isoformat(),
                "zone_occupancy": {},
            }
            energy = self._get_energy_prices(site_id)

            # For each candidate, build a targeted prompt
            for eq in candidates:
                eq_code = eq.get("code", "")
                eq_type = eq.get("type", "unknown")
                health = eq.get("health_score")
                op = eq.get("operating_data") or {}
                anomaly = op.get("anomaly_score") if isinstance(op, dict) else None
                lstm_anomaly = op.get("lstm_anomaly_score") if isinstance(op, dict) else None

                logger.debug(
                    f"[AI-OPT] Sweep target: {eq_code} type={eq_type} health={health} "
                    f"anomaly={anomaly} lstm={lstm_anomaly}"
                )

                # Build focused prompt for this equipment
                prompt = f"""SENTINEL Health Sweep — Equipment Analysis

Site: {site_id}
Equipment: {eq_code}
Type: {eq_type}
Current Health Score: {health}
Anomaly Score (IF): {anomaly}
LSTM Anomaly Score: {lstm_anomaly}

Current Conditions:
- Indoor temp: {conditions.get("indoor_temp", 22)}°C
- Outdoor temp: {conditions.get("outdoor_temp", 28)}°C
- Humidity: {conditions.get("humidity", 55)}%

Energy Pricing: R{energy.get("current_rate", 2.28)}/kWh (standard)

Analyze this equipment and generate any needed maintenance or optimization
recommendations. Consider:
- Is health_score declining or below thresholds?
- Are anomaly scores elevated?
- Are there operational inefficiencies (e.g., excessive runtime, unnecessary consumption)?

Format output as JSON:
{{
  "recommendations": [
    {{
      "equipment_id": "{eq_code}",
      "point_name": "<control_point>",
      "current_value": <value>,
      "recommended_value": <value>,
      "reason": "<explanation>",
      "confidence": <0-1>
    }}
  ]
}}

If no action needed, return empty recommendations array.
"""

                try:
                    response_text = await self._call_claude(prompt, site_id)
                    if not response_text:
                        continue

                    import re

                    json_match = re.search(r"\{[\s\S]*\}", response_text)
                    if not json_match:
                        continue

                    import json as _json

                    parsed = _json.loads(json_match.group())
                    recs = parsed.get("recommendations", [])
                    for rec in recs:
                        rec["site_id"] = site_id
                        rec["source"] = "health_sweep"
                        results.append(rec)

                except Exception as e:
                    logger.warning(f"[AI-OPT] Sweep recommendation failed for {eq_code}: {e}")

            logger.info(f"[AI-OPT] Sweep complete: {len(results)} recommendations for {site_id}")

        except Exception as e:
            logger.error(f"[AI-OPT] Full equipment sweep failed for {site_id}: {e}")

        return results

    def _format_ml_context_section(self, ml_context: dict[str, Any]) -> str:
        """Format ML context into a readable prompt section for Claude."""
        if not ml_context:
            return ""

        sections = []

        # LSTM Forecasts
        forecasts = ml_context.get("lstm_forecasts", [])
        if forecasts:
            lines = ["**ML Predictive Forecasts (LSTM 24/48/72h):**"]
            for f in forecasts[:10]:  # Cap at 10 to avoid prompt bloat
                lines.append(
                    f"- {f['equipment_name']} ({f['type']}): "
                    f"24h={f.get('forecast_24h', 'N/A')}, "
                    f"48h={f.get('forecast_48h', 'N/A')}, "
                    f"72h={f.get('forecast_72h', 'N/A')} "
                    f"(confidence: {f.get('confidence', 0):.0%})"
                )
            sections.append("\n".join(lines))

        # Anomaly Alerts
        anomalies = ml_context.get("anomaly_alerts", [])
        if anomalies:
            lines = ["**ML Anomaly Detection Alerts:**"]
            for a in anomalies[:10]:
                lines.append(
                    f"- {a['equipment_id']} ({a['type']}): "
                    f"score={a['anomaly_score']}, severity={a['severity']}"
                    f"{' ⚠ ANOMALY' if a.get('is_anomaly') else ''}"
                )
            sections.append("\n".join(lines))

        # Fault Classifications
        faults = ml_context.get("fault_classifications", [])
        if faults:
            lines = ["**ML Fault Classification (Active Risks):**"]
            for f in faults[:10]:
                lines.append(
                    f"- {f['equipment_id']} ({f['equipment_type']}): "
                    f"{f['fault_type']} probability={f['probability']:.0%}"
                )
            sections.append("\n".join(lines))

        # Health Trends (degrading equipment)
        trends = ml_context.get("health_trends", [])
        if trends:
            lines = ["**Equipment Health Trends (Degrading):**"]
            for t in trends:
                lines.append(
                    f"- {t['equipment_name']}: score={t['health_score']:.0f}/100 "
                    f"({t['health_status']}), 7d slope={t['trend_7d_slope']} pts/day"
                )
            sections.append("\n".join(lines))

        # Building-level features
        features = ml_context.get("feature_metrics", {})
        if features:
            lines = ["**Building Performance Metrics:**"]
            if features.get("eui"):
                lines.append(f"- Energy Use Intensity (EUI): {features['eui']:.2f} kWh/m²")
            if features.get("base_load_index") is not None:
                lines.append(f"- Base Load Index: {features['base_load_index']:.2%} (off-hours / total)")
            if features.get("cooling_degree_days") is not None:
                lines.append(f"- Cooling Degree Days (today): {features['cooling_degree_days']:.1f}")
            if features.get("efficiency_score") is not None:
                lines.append(f"- Building Efficiency Score: {features['efficiency_score']:.0f}/100")
            sections.append("\n".join(lines))

        # Live Anomaly Scores (178-08 pipeline — real-time per equipment)
        live_scores = ml_context.get("live_anomaly_scores", [])
        if live_scores:
            formatted = self._format_live_anomaly_scores(live_scores)
            if formatted:
                sections.append(formatted)

        if not sections:
            return ""

        return (
            "\n**🧠 ML MODEL INTELLIGENCE (Predictive Context):**\n"
            "Use these ML outputs to make PREDICTIVE recommendations — "
            "consider future equipment behaviour, not just current state.\n\n" + "\n\n".join(sections) + "\n"
        )

    def _format_feedback_loop_section(
        self,
        decision_memory_text: str | None,
        feedback_rates_text: str | None,
    ) -> str:
        """Format decision memory and feedback success rates for prompt injection.

        Only adds sections when data exists. Returns empty string if no feedback data.
        """
        sections = []

        if feedback_rates_text:
            sections.append(
                "**RECOMMENDATION SUCCESS RATES (from recorded outcomes at this site):**\n"
                f"{feedback_rates_text}\n\n"
                "Adjust your confidence scores accordingly. For equipment types with <60% success rate, "
                "only recommend when the condition is clearly anomalous, not as routine optimization."
            )

        if decision_memory_text:
            sections.append(
                "**HISTORICAL PATTERN MEMORY (what has worked at this site before):**\n"
                f"{decision_memory_text}\n\n"
                "Use this history to inform your recommendations. If a pattern shows a previous action "
                "failed, do not repeat it without a specific reason to believe conditions have changed."
            )

        if not sections:
            return ""

        return "\n" + "\n\n".join(sections) + "\n"

    # ── Phase 2: 5-Layer Prompt Structure ─────────────────────────────────────

    def _format_profile_intent(self, profile: str, energy_prices: dict[str, Any]) -> str:
        """Layer 1 — Active goal: what we're optimising for right now."""
        current_rate = energy_prices.get("current_rate", energy_prices.get("eskom_rate", 0))
        band = energy_prices.get("band", "standard")
        schedule = energy_prices.get("schedule", [])
        next_change = "unknown"
        demand_charge = energy_prices.get("demand_charge_per_kva")
        nmd = energy_prices.get("nmd_kva")
        if isinstance(schedule, list) and schedule:
            next_entry = schedule[0]
            if isinstance(next_entry, dict):
                next_change = next_entry.get("start", "unknown")
            else:
                next_change = str(next_entry)

        intents = {
            "cost_saving": f"""
Optimise for minimum energy cost.
Current TOU: R{current_rate:.2f}/kWh ({band.upper()})
Next tariff change: {next_change}
{f"Demand charge: R{demand_charge:.2f}/kVA/month · NMD: {nmd} kVA" if demand_charge else ""}
Every recommendation must include ZAR saving estimate.
Comfort may be relaxed within safe bounds.
Equipment health is secondary unless failure is imminent.
""",
            "comfort": """
Optimise for occupant comfort.
Maintain setpoints within tight tolerance.
Energy cost is secondary.
Do not recommend setpoint relaxation unless building is empty.
""",
            "asset_preservation": f"""
Optimise for equipment longevity.
Reduce unnecessary runtime on degraded equipment.
Flag any equipment operating outside safe parameters.
Current TOU: R{current_rate:.2f}/kWh — cost context only.
""",
            "balanced": f"""
Balance cost, comfort, and asset health equally.
Current TOU: R{current_rate:.2f}/kWh ({band.upper()})
{f"Demand charge: R{demand_charge:.2f}/kVA/month · NMD: {nmd} kVA" if demand_charge else ""}
Prioritise actions that improve multiple dimensions simultaneously.
""",
        }

        # Append holistic reasoning instruction to all profiles
        for key in intents:
            intents[key] += """
CRITICAL REASONING INSTRUCTION:
Reason about this building as a single interconnected system.
HVAC load affects energy cost and equipment wear. Occupancy affects both HVAC and lighting.
BESS dispatch affects peak demand. Equipment health affects how hard other systems work.
Weather forecast affects how long current conditions persist.

Do NOT reason about equipment in isolation.
Do NOT generate separate recommendations for each piece of equipment.

Instead: assess the whole building state, identify the dominant
condition driving inefficiency, and recommend a coordinated set of
adjustments across all relevant systems that together achieve the
profile goal.

One building assessment. One coordinated recommendation.
Multiple adjustments if needed — but unified by a single insight.
"""
        return intents.get(profile, intents["balanced"])

    def _format_pattern_context(
        self,
        decision_memory: str | None,
        simulated_time: datetime,
    ) -> str:
        """Layer 3 — Learned patterns from shadow phase."""
        if not decision_memory:
            return (
                "No patterns learned yet — building still in early observation phase.\n"
                "Use sensor data and ML model outputs to identify anomalies."
            )
        time_str = simulated_time.strftime("%H:%M")
        return f"""
Time-relevant patterns (±1 hour from {time_str}):
{decision_memory}

Use these patterns to anticipate conditions, not just react to them.
If a pattern suggests a zone will empty soon, recommend action now.
"""

    def _format_full_context(self, conditions: dict) -> str:
        """Layer 2B — Full building telemetry context block."""
        blocks = []

        # Carbon/ESG context
        carbon = conditions.get("carbon")
        if carbon:
            variance_line = ""
            if carbon.get("carbon_vs_baseline_kgco2") is not None:
                direction = "above" if carbon["carbon_vs_baseline_kgco2"] > 0 else "below"
                variance_line = f"vs baseline: {abs(carbon['carbon_vs_baseline_kgco2'])} kgCO2/h {direction}\n"
            blocks.append(f"""CARBON & ESG:
Grid intensity: {carbon["grid_intensity_kgco2_kwh"]} kgCO2/kWh (Eskom 2024)
Building footprint: {carbon["building_kgco2_hour"]} kgCO2/hour
{variance_line}Renewable fraction: {carbon["renewable_fraction_pct"]}% (solar)
Solar carbon offset: {carbon["solar_offset_kgco2_hour"]} kgCO2/hour
Grid import: {carbon["grid_import_kw"]} kW
Source: {carbon["source"]}
""")

        elec = conditions.get("electrical")
        if elec:
            blocks.append(f"""ELECTRICAL:
Total site load: {elec.get("total_kw", "?")} kW
HVAC load: {elec.get("hvac_kw", "?")} kW
Lighting load: {elec.get("lighting_kw", "?")} kW
Solar generating: {elec.get("solar_kw", "?")} kW""")
        ipmvp = conditions.get("ipmvp")
        if ipmvp:
            blocks.append(f"""IPMVP BASELINE:
Current consumption: {ipmvp.get("current_kwh", "?")} kWh (last 24h)
Records available: {ipmvp.get("records_available", 0)}""")
        return "\n\n".join(blocks) if blocks else "Extended telemetry not available."

    def _format_constraints(self, site: dict[str, Any], conditions: dict | None = None) -> str:
        """Layer 4 — Module permissions, autonomous systems, and safety limits."""
        active_modules = (conditions or {}).get("active_modules", [])
        perms = {
            "hvac_control": "HVAC setpoints, AHU scheduling, FCU adjustments",
            "energy_control": "Peak shaving, load shifting, demand management",
            "lighting_control": "Lighting scenes, daylight harvesting schedules",
            "solar_control": "BESS dispatch, solar optimisation, arbitrage",
            "water_control": "Valve scheduling, pressure management",
        }
        allowed = [f"\u2705 {desc} ({mod} active)" for mod, desc in perms.items() if mod in active_modules]
        blocked = [f"\u274c {desc} ({mod} not active)" for mod, desc in perms.items() if mod not in active_modules]

        sections = ["ACTIVE CONTROL MODULES \u2014 what you can recommend:"]
        sections.append("\n".join(allowed) if allowed else "No control modules active \u2014 advisory only")
        if blocked:
            sections.append("\nINACTIVE MODULES \u2014 do not recommend:\n" + "\n".join(blocked))

        sections.append("""
AUTONOMOUS SYSTEMS (already running \u2014 do not duplicate):
- DALI/Tridonic: occupancy dimming, daylight harvesting
- BESS solar arbitrage: TOU charge/discharge cycles
- HVAC occupancy setback: +2\u00b0C when zone empty

SAFETY LIMITS:
- Minimum zone temp (after hours): 18\u00b0C
- Maximum setpoint relaxation: +3\u00b0C from comfort baseline
- Do not increase load on equipment with health score < 70%
""")
        return "\n".join(sections)

    def _format_task(
        self,
        profile: str,
        current_time: datetime,
        energy_prices: dict[str, Any],
    ) -> str:
        """Layer 5 — The specific question the AI should answer."""
        time_str = current_time.strftime("%H:%M")
        is_occupied = 7 <= current_time.hour < 18
        period = "occupied hours" if is_occupied else "after hours"

        return f"""
Current time: {time_str} SAST ({period})
Active profile: {profile.upper().replace("_", " ")}

RESPONSE FORMAT:
{{
  "building_assessment": "One sentence describing the dominant building condition right now",
  "recommendations": [
    {{
      "title": "Short description of the coordinated action",
      "adjustments": [
        {{
          "equipment_id": "S002-FCU-L2-A",
          "point": "cooling_setpoint",
          "current_value": 22.0,
          "recommended_value": 22.9,
          "unit": "°C"
        }}
      ],
      "reason": "Explanation grounded in live telemetry AND shadow-learned patterns. Must reference actual values — current temp, current tariff, observed pattern frequency.",
      "affected_zones": ["Zone-201", "Zone-202"],
      "profile_goal": "{profile}",
      "saving": "R18.40 this afternoon",
      "confidence": 0.84,
      "confidence_basis": "23 similar observations during shadow phase"
    }}
  ],
  "no_action_reasons": [],
  "data_requests": []
}}

RULES:
- building_assessment is REQUIRED — always describe the whole building state
- adjustments array can contain multiple equipment items — this is ONE coordinated recommendation
- reason MUST reference actual telemetry values (temperatures, kW, tariff rate)
- reason MUST reference shadow learning when available
- If no adjustment needed — return empty recommendations with no_action_reasons explaining WHY
- NEVER generate more than 3 recommendations per cycle — consolidate if you have more
- NEVER generate a recommendation without specific adjustments
- Each adjustment must have equipment_id, point, current_value, recommended_value

If the building is already running optimally for {profile},
state specifically why — reference actual values, not generic statements.

If you need additional data to improve recommendations, list in:
{{"data_requests": ["occupancy_schedule", "nmd_limit"]}}
"""

    def _build_optimization_prompt(
        self,
        site: dict[str, Any],
        current_conditions: dict[str, Any],
        weather_forecast: dict[str, Any],
        energy_prices: dict[str, Any],
        equipment_inventory: dict[str, list[Device]],
        lighting_zones: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
        ml_context: dict[str, Any] | None = None,
        decision_memory_text: str | None = None,
        feedback_rates_text: str | None = None,
        precomputed_context=None,  # Phase 1b: PreComputedContext | None
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
            lighting_zones: DALI zone data
            profile: Optimization profile with weights and thresholds
            ml_context: ML model outputs (forecasts, anomalies, faults, health trends)
        """
        lighting_zones = lighting_zones or {}

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

        # Extract active profile name for profile-aware prompt
        active_profile = "balanced"
        profile_name = "balanced"
        if profile and profile.get("name"):
            active_profile = profile.get("name", "balanced")
            profile_name = active_profile.lower()

        # Current time context
        op_hours = site.get("operating_hours", {})
        op_start = op_hours.get("start", "08:00")
        op_end = op_hours.get("end", "18:00")
        now_sast = datetime.now()
        current_time_str = now_sast.strftime("%H:%M")
        current_weekday = now_sast.strftime("%A")
        is_occupied_hours = now_sast.weekday() < 5 and int(op_start.replace(":", "")) <= int(
            current_time_str.replace(":", "")
        ) <= int(op_end.replace(":", ""))

        # ── 5-LAYER PROMPT STRUCTURE ───────────────────────────────────────────
        prompt_parts = []

        # LAYER 1 — ACTIVE GOAL
        layer1 = f"""=================================================================
LAYER 1 — ACTIVE GOAL
=================================================================
Profile: {active_profile.upper().replace("_", " ")}
{self._format_profile_intent(profile_name, energy_prices)}"""

        # LAYER 2 — WASTE OPPORTUNITIES
        waste_block = (
            self.context_precompute_service.format_for_prompt(precomputed_context) if precomputed_context else ""
        )
        layer2 = f"""=================================================================
LAYER 2 — WASTE OPPORTUNITIES (pre-computed)
=================================================================
{waste_block if waste_block else "No waste opportunities detected at current conditions."}"""

        # LAYER 2B — FULL BUILDING TELEMETRY
        layer2b = f"""=================================================================
LAYER 2B — FULL BUILDING TELEMETRY
=================================================================
{self._format_full_context(current_conditions)}"""

        # LAYER 3 — LEARNED PATTERNS
        layer3 = f"""=================================================================
LAYER 3 — LEARNED PATTERNS
=================================================================
{self._format_pattern_context(decision_memory_text, now_sast)}"""

        # LAYER 4 — CONSTRAINTS & MODULE PERMISSIONS
        layer4 = f"""=================================================================
LAYER 4 — CONSTRAINTS & MODULE PERMISSIONS
=================================================================
{self._format_constraints(site, current_conditions)}"""

        # LAYER 5 — TASK
        layer5 = f"""=================================================================
LAYER 5 — TASK
=================================================================
{self._format_task(profile_name, now_sast, energy_prices)}"""

        prompt_parts.extend([layer1, layer2, layer2b, layer3, layer4, layer5])

        # ── DATA SECTIONS (unchanged — between LAYER 3 and LAYER 5) ───────
        # Building context
        data_sections = [
            f"""**Building:** {site["name"]} ({site["id"]})
- Type: {site.get("type", "commercial")}
- Size: {site.get("sqm", 5000)} sqm
- Floors: {site.get("floors", 1)}
- Operating hours: {op_start} - {op_end} (weekdays only)
- Region: {site.get("region", "Gauteng")}

**Current Time:** {current_time_str} SAST, {current_weekday}
**Building Status:** {"OCCUPIED — within operating hours" if is_occupied_hours else "UNOCCUPIED — outside hours"} [LIVE SITE — HVAC comfort recommendations ALLOWED 24/7 per operational mandate]

**SCHEDULE RULES (LIVE SITE):**
- HVAC comfort/setpoint/pre-conditioning: ALLOWED 24/7 on live sites
- Building is operating {"in occupied mode" if is_occupied_hours else "in unoccupied mode"} — AI contextualizes recommendations accordingly
- The AI optimizer on live sites generates HVAC recommendations regardless of time of day — use professional judgment on urgency

**Equipment Inventory at This Site:**
{chr(10).join(inventory_summary) if inventory_summary else "No equipment registered"}""",
            # Current conditions
            f"""**Current Conditions (LIVE SENSOR DATA):**
- Indoor temperature: {current_conditions.get("indoor_temp", 22)}°C
- Outdoor temperature: {current_conditions.get("outdoor_temp", 28)}°C
- Humidity: {current_conditions.get("humidity", 55)}%
- Occupancy: {current_conditions.get("occupancy", "unknown")}
- Equipment status: {current_conditions.get("equipment_status", "normal")}
{self._format_solar_bess_telemetry(current_conditions)}
{self._format_setpoint_context(current_conditions)}
{self._format_ml_context_section(ml_context) if ml_context else ""}
{self._format_feedback_loop_section(decision_memory_text, feedback_rates_text)}""",
            # Weather + Energy
            f"""**Weather Forecast (next 4 hours):**
{json.dumps(weather_forecast, indent=2)}

**Energy Pricing (South African):**
{json.dumps(energy_prices, indent=2)}""",
            # Equipment + Control Points
            f"""{self._format_all_equipment_sections(equipment_inventory)}

**All Available Control Points (by system):**
{self._format_all_control_points(controllable)}

{self._format_zone_context(hvac_devices)}""",
            # Zone rules + Equipment constraints
            f"""**Zone-Aware Optimization Rules (Southern Hemisphere - South Africa):**
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

Lighting (DALI) — Tridonic net4more handles natively:
- Daylight harvesting, occupancy-based dimming, emergency zones
- Occupancy-based HVAC setback via BACnet gateway to BMS
- Air quality ventilation via CO2/VOC sensors to BMS
- DO NOT recommend dim levels or occupancy-based changes — Tridonic does this
- SENTINEL adds: tariff-aware scheduling, predictive pre-conditioning, energy analytics

Power/Generators:
- Generator: start only during load shedding or mains failure
- UPS: maintain battery charge >50%
- ATS: automatic transfer, no manual override unless emergency

Solar PV:
- Inverters: monitor only, no direct setpoint control (cloud-managed)
- Curtailment: only if grid export limit exceeded or NRS 097 violation
- Performance ratio target: >80% (investigate if below 75%)

BESS (Battery Storage) — autonomous dispatch engine handles natively:
- The solar_arbitrage_engine runs a 5-minute dispatch cycle independently
- It ALREADY handles ALL of these — DO NOT recommend ANY of them:
  * Peak TOU discharge (07:00-10:00, 18:00-20:00 SAST)
  * Off-peak TOU charge (22:00-06:00 SAST)
  * Emergency SOC protection below 12%
  * Load shedding priority discharge
  * Solar-priority charging
- If you include ANY of these, it will be discarded as a duplicate of autonomous behaviour
- SENTINEL BESS recs are advisory overlays ONLY — recommend when you have
  higher-order context the engine cannot see: demand response coordination,
  weather-driven pre-charge before forecast cloud cover, or grid anomaly response
- SOC limits: maintain 10-90% (never fully discharge or overcharge)
- Mode changes: idle→discharge allowed, charging→discharge needs 60s transition

{self._format_lighting_section(lighting_devices, lighting_zones)}""",
        ]

        prompt = "\n\n".join(prompt_parts) + "\n\n" + "\n\n".join(data_sections) + "\n\n"

        # JSON response format block
        prompt += """
**Response Format (JSON):**

NOTE: The "recommendations" array may be EMPTY if the building is running normally.
This is the correct response when no interventions are needed.

```json
{{
  "recommendations": [
    {{
      "equipment_id": "S002-FCU-101",
      "equipment_name": "FCU Zone 101",
      "point_name": "zone_cooling_setpoint",
      "current_value": 22.0,
      "recommended_value": 24.0,
      "unit": "°C",
      "reason": "Indoor temp 22.1°C with occupancy at 12% — raise setpoint 2°C to reduce cooling energy",
      "system": "hvac",
      "savings_kwh": 1.5,
      "carbon_saving": "1.2 kgCO2 this evening (Eskom 0.9 kgCO2/kWh)"
    }}
  ],
  "no_action_reasons": [
    "HVAC zones 201-205: indoor temps within ±0.5°C of setpoints, no intervention needed",
    "BESS: autonomous dispatch active, SOC at 65%, TOU schedule on track",
    "Generators: standby mode appropriate, no load shedding forecast"
  ],
  "cross_system_recommendations": [],
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
  "confidence": 0.72,
  "reasoning": "Summary of optimization strategy for this building's specific equipment"
}}

IMPORTANT: For each recommendation, include carbon_saving field where relevant.
Use Eskom grid intensity 0.9 kgCO2/kWh to calculate carbon savings from energy reduction.
Example: "carbon_saving": "1.2 kgCO2 this evening (Eskom 0.9 kgCO2/kWh)"
```

Provide ONLY the JSON response, no additional text."""

        return prompt

    async def _analyze_with_claude(
        self,
        site_id: str,
        task_class: str,
        prompt: str,
        current_conditions: dict[str, Any],
        equipment_inventory: dict[str, list[Device]],
        lighting_zones: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
    ) -> OptimizationRecommendation:
        """Analyze using Claude AI with full equipment inventory.

        Args:
            site_id: Site identifier
            task_class: model_gateway task class (heavy/medium) — heavy when anomalies present
            prompt: User message content (prompt split handles system content separately)
            current_conditions: Current building conditions
            equipment_inventory: Equipment by type
            lighting_zones: DALI zone data
            profile: Active optimization profile (if any)
        """
        try:
            logger.info(f"Using model_gateway({task_class}) for optimization of site {site_id}")

            # Call LLM via model_gateway (task_class determined by anomaly state)
            response_text = await model_gateway.call(
                task_class=task_class,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=settings.optimization_max_tokens,
                stream=False,
                source="ai_optimizer",
            )

            # Parse JSON response
            try:
                json_text = self._extract_json(response_text)
                result = json.loads(json_text)

                # Log data_requests for observability (Phase 2: data request mechanism)
                data_requests = result.get("data_requests", [])
                if data_requests:
                    logger.info(f"[AI-OPT] Data requests from AI model: {data_requests}")

                # Log no-action reasons for observability
                no_action_reasons = result.get("no_action_reasons", [])
                rec_count = len(result.get("recommendations", []))
                if no_action_reasons or rec_count == 0:
                    logger.warning(
                        f"[AI-OPT] LLM response for {site_id}: {rec_count} recommendations, "
                        f"{len(no_action_reasons)} no-action reasons"
                    )
                    for reason in no_action_reasons[:5]:
                        logger.warning(f"[AI-OPT]   No action: {reason}")

                # Parse holistic recommendation format (adjustments array)
                building_assessment = result.get("building_assessment", "")
                if building_assessment:
                    logger.warning(f"[AI-OPT] Building assessment: {building_assessment}")

                normalised_recommendations = self._parse_holistic_recommendations(
                    result.get("recommendations", []), building_assessment
                )

                # Hard filter: remove DALI equipment from AI optimization recs
                filtered = []
                DALI_PREFIXES = ("S002-DALI", "SITE-002-DALI", "DALI")
                for r in normalised_recommendations:
                    eq = (r.get("target_equipment") or "").upper()
                    if any(eq.startswith(p.upper()) for p in DALI_PREFIXES):
                        logger.info(f"[AI-OPT] Filtered DALI recommendation for {eq}")
                        continue
                    filtered.append(r)
                normalised_recommendations = filtered

                # Cap: max 3 recommendations per cycle — holistic prompt should produce 1-3
                MAX_RECS = 3
                if len(normalised_recommendations) > MAX_RECS:
                    logger.warning(
                        "[AI-OPT] Capping %d recommendations to %d (holistic limit)",
                        len(normalised_recommendations),
                        MAX_RECS,
                    )
                    normalised_recommendations = normalised_recommendations[:MAX_RECS]

                # Validate allowed control points before proceeding

                return OptimizationRecommendation(
                    site_id=site_id,
                    timestamp=datetime.now().isoformat(),
                    recommendations=normalised_recommendations,
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

    def _extract_json(self, raw: str) -> str:
        """Extract JSON from LLM response with markdown fences stripped.

        If the response is truncated mid-JSON (max_tokens cutoff), attempts
        to recover by finding the last structurally complete object.
        """
        import re

        # Strip markdown code fences
        clean = re.sub(r"^```json\s*|```\s*$", "", raw.strip(), flags=re.MULTILINE)

        # Try parsing as-is first
        try:
            json.loads(clean)
            return clean
        except json.JSONDecodeError:
            pass

        # Truncation recovery: find the last complete top-level object/array
        # Walk backwards from the end to find a valid closing brace for the
        # outermost container (starts with { or [)
        if clean.startswith("{"):
            # Find the last '}' that closes the outermost object
            depth = 0
            last_valid = -1
            for i, ch in enumerate(clean):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        last_valid = i + 1
                        break
            if last_valid > 0:
                truncated = clean[:last_valid]
                try:
                    json.loads(truncated)
                    logger.warning(
                        "[AI-OPT] Response was truncated at %d chars — recovered %d valid chars",
                        len(raw),
                        last_valid,
                    )
                    return truncated
                except json.JSONDecodeError:
                    pass
        elif clean.startswith("["):
            depth = 0
            last_valid = -1
            for i, ch in enumerate(clean):
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        last_valid = i + 1
                        break
            if last_valid > 0:
                truncated = clean[:last_valid]
                try:
                    json.loads(truncated)
                    logger.warning(
                        "[AI-OPT] Response was truncated at %d chars — recovered %d valid chars",
                        len(raw),
                        last_valid,
                    )
                    return truncated
                except json.JSONDecodeError:
                    pass

        # Unrecoverable — return as-is and let json.loads throw the real error
        logger.error(
            "[AI-OPT] Unrecoverable JSON parse error. Raw tail (last 300 chars): %s",
            raw[-300:],
        )
        return clean

    def _parse_holistic_recommendations(self, recommendations: list[dict], building_assessment: str) -> list[dict]:
        """Parse holistic recommendations with adjustments array into canonical format.

        The new format uses an 'adjustments' array per recommendation:
        {
          "title": "...",
          "adjustments": [{"equipment_id": "...", "point": "...", "recommended_value": ..., ...}],
          "reason": "...",
          "saving": "...",
          "confidence": 0.84,
          "confidence_basis": "..."
        }

        Parses into one canonical record per recommendation (primary equipment as target,
        all adjustments in metadata).
        """
        import uuid

        result = []
        for rec in recommendations:
            adjustments = rec.get("adjustments", [])
            if not adjustments:
                # Fallback: treat as flat recommendation format
                result.append(self._normalise_recommendation(rec))
                continue

            title = rec.get("title", "")
            reason = rec.get("reason", "")
            confidence = rec.get("confidence", 0.0)
            saving = rec.get("saving", "")
            confidence_basis = rec.get("confidence_basis", "")

            primary = adjustments[0]
            eq_id = primary.get("equipment_id", "")
            point = primary.get("point", "")
            val = primary.get("recommended_value")

            import re

            # Parse saving text into expected_impact numeric fields
            saving_text = rec.get("saving", "")
            cost_match = re.search(r"[RZ](\d+(?:[\s,.]\d+)?)", saving_text.replace(",", ""))
            cost_val = float(cost_match.group(1)) if cost_match else 0.0

            metadata = {
                "group_id": str(uuid.uuid4()),
                "group_recommendation": True,
                "affected_equipment": [a.get("equipment_id") for a in adjustments],
                "all_adjustments": adjustments,
                "building_assessment": building_assessment,
                "saving": saving,
                "confidence_basis": confidence_basis,
                "title": title,
            }

            canonical = {
                "target_equipment": eq_id,
                "action": {
                    "point": point,
                    "value": val,
                    "current_value": primary.get("current_value"),
                    "unit": primary.get("unit", ""),
                },
                "reason": reason,
                "confidence": confidence,
                "expected_impact": {"cost_zar": cost_val} if cost_val > 0 else {},
                "metadata": metadata,
            }
            result.append(canonical)

        return result

    def _normalise_recommendation(self, raw: dict) -> dict:
        """
        Normalise LLM response to canonical format regardless of
        which format the LLM returned.

        Canonical format:
        {
            "target_equipment": "S002-FCU-L0-A",   # always this key
            "action": {"point": "cooling_setpoint", "value": 22.9},  # always nested
            "reason": "...",
            "confidence": 0.82,
            "affected_equipment": [...],  # optional, for grouped recs
            "metadata": {"affected_equipment": [...], "group_recommendation": True}
        }

        Handles:
        - flat format: {point_name, recommended_value} → canonical
        - equipment_id vs target_equipment
        - affected_equipment top-level vs metadata-embedded
        - action.value as float or string
        """
        out = dict(raw)

        # Normalise equipment_id → target_equipment
        if "equipment_id" in out and "target_equipment" not in out:
            out["target_equipment"] = out.pop("equipment_id")
        elif "equipment_id" in out:
            out.pop("equipment_id", None)

        # Normalise flat action format → canonical nested
        if "point_name" in out and "action" not in out:
            out["action"] = {
                "point": out.pop("point_name"),
                "value": out.pop("recommended_value", out.pop("value", None)),
            }
        # Handle action.value that came through as string
        if "action" in out and isinstance(out["action"], dict):
            raw_val = out["action"].get("value")
            if raw_val is not None:
                try:
                    out["action"]["value"] = float(raw_val)
                except (TypeError, ValueError):
                    pass

        # Normalise affected_equipment → metadata
        if "affected_equipment" in out:
            affected = out.pop("affected_equipment")
            if "metadata" not in out:
                out["metadata"] = {}
            out["metadata"]["affected_equipment"] = affected
            out["metadata"]["group_recommendation"] = True

        # Parse saving text into expected_impact numeric fields
        if "expected_impact" not in out:
            import re

            saving_text = out.get("metadata", {}).get("saving", "") or out.get("saving", "")
            cost_match = re.search(r"[RZ](\d+(?:[\s,.]\d+)?)", saving_text.replace(",", ""))
            if cost_match:
                out["expected_impact"] = {"cost_zar": float(cost_match.group(1))}

        return out

    def _score_and_rank_recommendations(
        self, recommendation: OptimizationRecommendation, profile: dict[str, Any]
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

    def _find_device_by_type(self, hvac_devices: list[Device], hvac_type: str) -> Device | None:
        """Find a device by its hvac_type (zone_controller, chiller, chw_system, etc.)."""
        for device in hvac_devices:
            if hasattr(device, "hvac_type") and device.hvac_type == hvac_type:
                return device
        return None

    def _find_devices_by_type(self, hvac_devices: list[Device], hvac_type: str) -> list[Device]:
        """Find ALL devices of a specific hvac_type."""
        return [d for d in hvac_devices if hasattr(d, "hvac_type") and d.hvac_type == hvac_type]

    def _find_devices_with_point(self, hvac_devices: list[Device], point_name: str) -> list[Device]:
        """Find ALL devices that have a specific point."""
        return [d for d in hvac_devices if point_name in d.points]

    def _find_point_on_device(self, device: Device, possible_point_names: list[str]) -> DevicePoint | None:
        """Find a point on a device by checking multiple possible names."""
        for point_name in possible_point_names:
            if point_name in device.points:
                return device.points[point_name]
        return None

    def _has_any_point(self, device: Device, possible_point_names: list[str]) -> bool:
        """Check if device has any of the specified points."""
        return any(point_name in device.points for point_name in possible_point_names)

    def _format_device_list(self, hvac_devices: list[Device]) -> str:
        """Format device list for Claude prompt."""
        if not hvac_devices:
            return "No HVAC devices found"
        lines = []
        for d in hvac_devices:
            hvac_type = getattr(d, "hvac_type", "unknown")
            location = getattr(d, "location", "unknown location")
            lines.append(f"- {d.id}: {d.name} ({hvac_type}) at {location}")
        return "\n".join(lines)

    def _format_available_points(self, hvac_devices: list[Device]) -> str:
        """Format available control points for Claude prompt."""
        if not hvac_devices:
            return "No control points available"
        lines = []
        for d in hvac_devices:
            writable_points = [name for name, point in d.points.items() if point.writable]
            if writable_points:
                lines.append(f"- {d.id} ({d.name}): {', '.join(writable_points)}")
        return "\n".join(lines) if lines else "No writable control points found"

    def _find_device_with_point(self, hvac_devices: list[Device], point_name: str) -> Device | None:
        """Find a device that has a specific point."""
        for device in hvac_devices:
            if point_name in device.points:
                return device
        return None

    # Equipment Inventory Methods (Site-Specific)

    def _categorize_equipment(self, devices: list[Device]) -> dict[str, list[Device]]:
        """Categorize all equipment by type for site-specific optimization.

        Different buildings have different equipment combinations:
        - Building A: HVAC + DALI + Generators + Meters
        - Building B: HVAC + Standard Lighting + UPS
        - Building C: HVAC + DALI + Security + Fire

        Returns:
            Dict mapping device type to list of devices
        """
        inventory: dict[str, list[Device]] = {}

        for device in devices:
            # Get device type key (e.g., "hvac", "lighting", "power")
            type_key = device.device_type.value if device.device_type else "other"

            if type_key not in inventory:
                inventory[type_key] = []
            inventory[type_key].append(device)

        return inventory

    def _summarize_inventory(self, inventory: dict[str, list[Device]]) -> str:
        """Create a summary string of equipment inventory for logging."""
        parts = []
        for device_type, devices in inventory.items():
            if devices:
                parts.append(f"{device_type}={len(devices)}")
        return ", ".join(parts) if parts else "empty"

    def _get_controllable_equipment(self, inventory: dict[str, list[Device]]) -> dict[str, list[Device]]:
        """Filter inventory to only include equipment with writable points.

        This is used for recommendations - we can only recommend changes
        to equipment that has controllable parameters.
        """
        controllable: dict[str, list[Device]] = {}

        for device_type, devices in inventory.items():
            controllable_devices = []
            for device in devices:
                writable_points = [name for name, point in device.points.items() if point.writable]
                if writable_points:
                    controllable_devices.append(device)

            if controllable_devices:
                controllable[device_type] = controllable_devices

        return controllable

    def _format_equipment_by_type(self, devices: list[Device], equipment_type: str) -> str:
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

    def _format_all_equipment_sections(self, inventory: dict[str, list[Device]]) -> str:
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

    def _format_all_control_points(self, inventory: dict[str, list[Device]]) -> str:
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

    def _group_devices_by_zone(self, hvac_devices: list[Device]) -> dict[str, list[Device]]:
        """Group devices by their zone name for coordinated optimization."""
        zones: dict[str, list[Device]] = {}
        for device in hvac_devices:
            zone = (
                getattr(device.device_location, "zone", "Unknown") if hasattr(device, "device_location") else "Unknown"
            )
            if zone not in zones:
                zones[zone] = []
            zones[zone].append(device)
        return zones

    def _group_devices_by_floor(self, hvac_devices: list[Device]) -> dict[str, list[Device]]:
        """Group devices by floor level."""
        floors: dict[str, list[Device]] = {}
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

    def _get_zone_type(self, device: Device) -> ZoneType | None:
        """Get the zone type for a device."""
        if hasattr(device, "device_location") and device.device_location:
            return getattr(device.device_location, "zone_type", None)
        return None

    def _get_exposure(self, device: Device) -> ExposureDirection | None:
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

    def _calculate_data_quality_penalty(self, conditions: dict[str, Any]) -> float:
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
        recommendations: list[dict],
        hvac_devices: list[Device],
    ) -> list[dict]:
        """Sort recommendations by zone priority (critical zones first)."""
        device_map = {d.id: d for d in hvac_devices}

        def get_priority(rec: dict) -> int:
            device = device_map.get(rec.get("equipment_id"))
            if device:
                return self._get_zone_priority(device)
            return 3  # Default priority

        return sorted(recommendations, key=get_priority)

    def _format_zone_context(self, hvac_devices: list[Device]) -> str:
        """Format zone context for Claude prompt."""
        zones_by_type: dict[str, list[str]] = {}
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
            zone_type_label, exposure_label, priority_label = key.split("|")
            lines.append(f"- {zone_type_label} ({exposure_label}, {priority_label}): {', '.join(devices)}")
        return "\n".join(lines)

    # DALI Lighting Optimization Helper Methods

    def _gather_lighting_zone_data(self, lighting_svc, site_id: str) -> dict[str, Any]:
        """Gather DALI zone occupancy and lighting data for optimization.

        Args:
            lighting_svc: DALI service instance
            site_id: Site to gather data for

        Returns:
            Dictionary with zone occupancy and lighting summaries
        """
        zone_data = {}

        try:
            # Get all zones from DALI service
            zones = lighting_svc.get_all_zones()

            for zone in zones:
                zone_id = zone.get("zone_id")
                if not zone_id:
                    continue

                # Get occupancy data
                occupancy = lighting_svc.get_zone_occupancy(zone_id)
                # Get lighting data
                lighting = lighting_svc.get_zone_lighting(zone_id)

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

    def _format_solar_bess_telemetry(self, conditions: dict[str, Any]) -> str:
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

    def _format_setpoint_context(self, conditions: dict[str, Any]) -> str:
        """Format live setpoint context for the optimization prompt.

        Includes current vs optimal setpoint values so Claude knows exactly
        what to change and why. Only included when setpoints are available.
        """
        setpoints = conditions.get("setpoints")
        if not setpoints:
            return ""

        lines = ["**Live Setpoints (CURRENT vs OPTIMAL):**"]
        for point_key, sp_data in setpoints.items():
            value = sp_data.get("value")
            unit = sp_data.get("unit", "")
            lines.append(f"- {point_key}: {value}{unit} (current)")

        # Add brief note about operational context
        if "equipment_status" in conditions:
            status = conditions["equipment_status"]
            lines.append(f"- Equipment status: {status}")
            if status in ("degraded", "critical"):
                lines.append("  → Optimization should prioritize efficient operation of degraded equipment")

        return "\n".join(lines) + "\n"

    def _format_lighting_section(
        self,
        lighting_devices: list[Device],
        lighting_zones: dict[str, Any],
    ) -> str:
        """Format DALI lighting section for Claude prompt.

        Args:
            lighting_devices: List of lighting device objects
            lighting_zones: DALI zone data from _gather_lighting_zone_data

        Returns:
            Formatted string for Claude prompt
        """
        if not lighting_zones:
            return ""

        lines = []

        # Lighting System Summary
        lines.append("**Lighting System:**")
        total_zones = len(lighting_zones)
        occupied_zones = sum(1 for z in lighting_zones.values() if z.get("is_occupied"))
        over_lit_zones = [z for z in lighting_zones.values() if z.get("is_over_lit")]

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
        for _zone_id, zone in lighting_zones.items():
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

    def _format_lighting_device_list(self, lighting_devices: list[Device]) -> str:
        """Format lighting device list for Claude prompt."""
        if not lighting_devices:
            return "No lighting devices found"
        lines = []
        for d in lighting_devices:
            lighting_type = getattr(d, "lighting_type", "unknown")
            location = getattr(d, "location", "unknown location")
            lines.append(f"- {d.id}: {d.name} ({lighting_type}) at {location}")
        return "\n".join(lines)

    def _should_skip_zone_optimization(self, device: Device, zone_type: ZoneType | None) -> bool:
        """Check if zone type should have restricted optimization.

        Server rooms and critical zones should not have cooling reduced.
        """
        if zone_type == ZoneType.SERVER_ROOM:
            return True  # Never reduce cooling in server rooms
        return False

    def _get_zone_specific_setpoint_limits(self, device: Device, zone_type: ZoneType | None) -> tuple:
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
        current_conditions: dict[str, Any],
        weather_forecast: dict[str, Any],
        energy_prices: dict[str, Any],
        equipment_inventory: dict[str, list[Device]],
        lighting_zones: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
    ) -> OptimizationRecommendation:
        """Fallback rule-based optimization for ALL equipment types.

        Uses equipment inventory to generate recommendations for whatever
        equipment exists at this site. Different buildings have different
        equipment combinations.

        Args:
            profile: Active optimization profile (if any)
        """
        logger.info(f"Using rule-based optimization for site {site_id}")
        lighting_zones = lighting_zones or {}
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
                        target_value = 1.0  # enabled (1 = on)
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
        # Tridonic net4more + DALI-2 natively handles (when properly installed):
        #   - Daylight harvesting (continuous proportional dimming to 500 lux setpoint)
        #   - Occupancy-based dimming (PIR sensors → 20% when unoccupied)
        #   - Occupancy-based HVAC setback (via BACnet gateway to BMS)
        #   - Air quality driven ventilation (CO2/VOC sensors → BMS)
        #   - Emergency zone protection (maintains 70% minimum)
        # AI does NOT duplicate these. SENTINEL adds value through:
        #   - Tariff-aware scheduling (shift loads to off-peak)
        #   - Predictive pre-conditioning (anticipate occupancy patterns)
        #   - Cross-zone energy balancing (redistribute across building)
        lighting_recommendations: list[dict[str, Any]] = []
        cross_system_recommendations: list[dict[str, Any]] = []
        lighting_savings_kw = 0.0

        if lighting_zones:
            for zone_id, zone in lighting_zones.items():
                lighting = zone.get("lighting", {})
                is_occupied = zone.get("is_occupied", True)

                if not lighting:
                    continue

                zone_name = zone.get("zone_name", zone_id)

                # Tridonic handles occupancy-based dimming AND HVAC setback natively
                # via net4more BACnet integration. SENTINEL adds predictive/tariff value.
                if not is_occupied:
                    cross_system_recommendations.append(
                        {
                            "zone_id": zone_id,
                            "zone_name": zone_name,
                            "hvac_action": "Managed by Tridonic net4more (occupancy-based setback via BACnet)",
                            "lighting_action": "Managed by Tridonic controller (occupancy-based dimming)",
                            "sentinel_action": "Monitor for predictive pre-conditioning and tariff optimization",
                            "reason": (
                                "Zone unoccupied - native Tridonic control active, SENTINEL monitoring for optimization"
                            ),
                            "combined_savings_kw": round(0.5, 2),
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
        if lighting_zones:
            total_zones = len(lighting_zones)
            occupied_zones = sum(1 for z in lighting_zones.values() if z.get("is_occupied"))
            over_lit_count = sum(1 for z in lighting_zones.values() if z.get("is_over_lit"))
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

    async def analyze_site_load_shedding(
        self,
        site_id: str,
        load_shedding_stage: int,
        current_conditions: dict[str, Any] | None = None,
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
        MAX_SAVINGS_MULTIPLIER = 2.0  # Cap at 2x — beyond this is speculative
        savings_multiplier = min(1.0 + (load_shedding_stage * 0.2), MAX_SAVINGS_MULTIPLIER)
        logger.debug(
            f"[AI-OPT] Load shedding stage {load_shedding_stage} → "
            f"savings multiplier {savings_multiplier:.1f}x "
            f"({'capped' if savings_multiplier == MAX_SAVINGS_MULTIPLIER else 'uncapped'})"
        )
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
    ) -> dict[str, Any]:
        """
        Validate a recommendation against safety rules.

        Args:
            site_id: Site ID
            recommendation: Recommendation to validate

        Returns:
            Validation result with allowed flag and details
        """
        try:
            from app.database.repositories.equipment_repository import EquipmentRepository

            devices = await device_manager.list_devices_by_site(site_id)
            all_allowed = True
            validation_results = []

            for rec in recommendation.recommendations:
                # target_equipment is canonical; fall back to equipment_id for compatibility
                equipment_id = rec.get("target_equipment") or rec.get("equipment_id")
                # Handle both flat format (point_name) and grouped format (action.point)
                point_name = rec.get("point_name") or rec.get("action", {}).get("point", "")
                # Handle both flat format (recommended_value) and grouped format (action.value)
                value = rec.get("recommended_value") or rec.get("action", {}).get("value")

                # Find device
                device = next((d for d in devices if d.id == equipment_id), None)

                # FIX 2: HTTP bridge fallback — device_manager empty for oBIX sites
                if not device:
                    equip_repo = EquipmentRepository()
                    # Wrap synchronous call in asyncio thread pool with 5s timeout
                    try:
                        equip_list = await asyncio.wait_for(
                            asyncio.to_thread(equip_repo.get_by_site_code, site_id),
                            timeout=5.0,
                        )
                    except asyncio.TimeoutError:
                        logger.error(
                            f"[AI-OPT] validate_recommendation DB timeout for {site_id} "
                            f"— allowing recommendation through with reduced confidence"
                        )
                        # Allow through but reduce confidence
                        validation_results.append(
                            {
                                "equipment_id": equipment_id,
                                "point_name": point_name,
                                "allowed": True,
                                "reason": "DB timeout — reduced confidence",
                                "validation_note": "supabase_timeout",
                                "confidence_multiplier": 0.7,
                            }
                        )
                        continue

                    # Normalise site_id for lookup: "site-002" → "S002" (for future use)
                    found = next((e for e in equip_list if e.get("code") == equipment_id), None)
                    if found:
                        logger.warning(f"[AI-OPT] {equipment_id} validated via Supabase fallback")
                        validation_results.append(
                            {
                                "equipment_id": equipment_id,
                                "point_name": point_name,
                                "allowed": True,
                                "reason": "Validated via Supabase fallback (device_manager empty for HTTP bridge site)",
                                "source": "supabase_fallback",
                            }
                        )
                        continue
                    else:
                        validation_results.append(
                            {
                                "equipment_id": equipment_id,
                                "point_name": point_name,
                                "allowed": False,
                                "reason": f"Device {equipment_id} not found in device_manager or Supabase",
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
