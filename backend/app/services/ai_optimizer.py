"""AI Optimizer Service for building HVAC optimization.

Uses Claude AI to analyze building telemetry, weather forecasts, and energy
pricing to generate optimal HVAC setpoint recommendations.
"""

import logging
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from anthropic import Anthropic

from app.models.optimization import (
    OptimizationRecommendation,
    OptimizationSettings,
    OptimizationStatus,
    SiteOptimizationStatus,
    OptimizationHistoryEntry,
)
from app.models.device import Device, DeviceType, DevicePoint, ZoneType, ExposureDirection
from app.models.dali import ZoneOccupancy, ZoneLighting
from app.services.claude_service import claude_service
from app.services.device_abstraction import device_manager
from app.services.safety_interlocks import safety_engine
from app.services.dali_service import get_dali_service

logger = logging.getLogger(__name__)

# Data directory for sites
DATA_DIR = Path(__file__).parent.parent / "data"


async def ensure_device_manager_initialized() -> None:
    """Ensure device manager is initialized with mock devices if not already."""
    if not device_manager._initialized:
        logger.info("Device manager not initialized, loading mock devices...")
        try:
            mock_devices_path = DATA_DIR / "mock_devices.json"
            if mock_devices_path.exists():
                with open(mock_devices_path) as f:
                    devices_data = json.load(f)
                await device_manager.initialize(devices_data)
                logger.info(f"Device manager initialized with {len(devices_data)} devices")
            else:
                logger.warning("mock_devices.json not found, initializing empty device manager")
                await device_manager.initialize([])
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

        # Get site devices for context
        devices = await device_manager.list_devices_by_site(site_id)
        hvac_devices = [d for d in devices if d.device_type == DeviceType.HVAC]
        lighting_devices = [d for d in devices if d.device_type == DeviceType.LIGHTING]

        # Fetch DALI lighting zone data
        dali_service = get_dali_service()
        dali_zones = self._gather_dali_zone_data(dali_service, site_id)

        # Build optimization prompt for Claude
        prompt = self._build_optimization_prompt(
            site, current_conditions, weather_forecast, energy_prices, hvac_devices,
            lighting_devices, dali_zones
        )

        try:
            # Try to use Claude for analysis
            if self._claude_service.is_configured():
                recommendation = await self._analyze_with_claude(
                    site_id, prompt, current_conditions, hvac_devices, dali_zones
                )
            else:
                # Fall back to rule-based optimization
                recommendation = self._analyze_with_rules(
                    site_id, current_conditions, weather_forecast, energy_prices,
                    hvac_devices, dali_zones
                )

            return recommendation

        except Exception as e:
            logger.error(f"Error analyzing building {site_id}: {e}")
            # Fall back to rule-based optimization
            return self._analyze_with_rules(
                site_id, current_conditions, weather_forecast, energy_prices,
                hvac_devices, dali_zones
            )

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
            }

            # Try to get actual readings from devices
            for device in devices:
                if device.device_type == DeviceType.HVAC:
                    for point_name, point in device.points.items():
                        if "temp" in point_name.lower():
                            try:
                                value = await device_manager.read_device_value(device.id, point_name)
                                conditions["indoor_temp"] = value.value
                                break
                            except Exception:
                                pass

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
            "current_rate": 2.50,  # Rand per kWh
            "peak_rate": 3.50,
            "off_peak_rate": 1.80,
            "period": "standard",  # peak, off_peak, standard
            "currency": "ZAR",
        }

    def _build_optimization_prompt(
        self,
        site: Dict[str, Any],
        current_conditions: Dict[str, Any],
        weather_forecast: Dict[str, Any],
        energy_prices: Dict[str, Any],
        hvac_devices: List[Device],
        lighting_devices: Optional[List[Device]] = None,
        dali_zones: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build optimization prompt for Claude."""
        lighting_devices = lighting_devices or []
        dali_zones = dali_zones or {}

        prompt = f"""You are an expert building optimization engineer specializing in HVAC and DALI lighting systems. Analyze the following building data and recommend optimal setpoints for energy efficiency and occupant comfort.

**Building:** {site['name']} ({site['id']})
- Type: {site['type']}
- Size: {site['sqm']} sqm
- Operating hours: {site['operating_hours']}

**Current Conditions:**
- Indoor temperature: {current_conditions.get('indoor_temp', 22)}°C
- Outdoor temperature: {current_conditions.get('outdoor_temp', 28)}°C
- Humidity: {current_conditions.get('humidity', 55)}%
- Occupancy: {current_conditions.get('occupancy', 'unknown')}
- Equipment status: {current_conditions.get('equipment_status', 'unknown')}

**Weather Forecast (next 4 hours):**
{json.dumps(weather_forecast, indent=2)}

**Energy Pricing:**
{json.dumps(energy_prices, indent=2)}

**HVAC Equipment on Site ({len(hvac_devices)} devices):**
{self._format_device_list(hvac_devices)}

**Available Control Points:**
{self._format_available_points(hvac_devices)}

{self._format_zone_context(hvac_devices)}

**Zone-Aware Optimization Rules (IMPORTANT - Southern Hemisphere context):**
- Executive/Server zones (P1): Maintain tighter comfort bands, never sacrifice cooling
- South/West-facing zones: Account for afternoon solar heat gain (+1-2°C adjustment needed)
- Top floor zones: Roof heat gain requires 0.5-1°C lower setpoints than interior zones
- Meeting rooms (P2): Pre-condition 15 min before scheduled meetings
- Load shedding: Prioritize by zone_priority (P1 = critical, P5 = lowest priority)
- Plant rooms (P5): Can accept wider temperature ranges for energy savings

**Building Constraints (SAFETY LIMITS - MUST NOT EXCEED):**
- CHW temperature: 5-15°C (minimum 5°C to prevent freeze damage)
- Zone temperature setpoints: 20-26°C (standard comfort range)
- Executive zones: 21-23°C (tighter comfort band)
- Server rooms: 18-22°C (critical cooling)
- Humidity: 30-65% RH
- Lighting minimum: 10% (DALI level 25) in occupied zones for safety
- Lighting minimum: 70% (DALI level 178) in emergency zones

{self._format_lighting_section(lighting_devices, dali_zones)}

**Your Task:**
1. Analyze the current conditions vs outdoor weather
2. Consider energy pricing (higher rates = more aggressive optimization)
3. Apply zone-aware rules based on zone_type and exposure
4. Recommend specific HVAC setpoint changes
5. Recommend DALI lighting adjustments (dim level 0-254, use dim_level point)
6. IMPORTANT: Use the EXACT point_name from the "Available Control Points" list above
7. Project energy savings in ZAR per hour (include lighting savings)
8. Ensure all recommendations are within safety limits for each zone type
9. Prioritize cross-system coordination (e.g., unoccupied zones: raise HVAC AND dim lights)

**Response Format (JSON):**
```json
{{
  "recommendations": [
    {{
      "equipment_id": "device-id",
      "equipment_name": "Device Name",
      "point_name": "setpoint",
      "current_value": 22.0,
      "recommended_value": 23.0,
      "unit": "°C",
      "reason": "Brief explanation",
      "system": "hvac"
    }},
    {{
      "equipment_id": "zone-id",
      "equipment_name": "Zone Name",
      "point_name": "dim_level",
      "current_value": 254,
      "recommended_value": 51,
      "unit": "level",
      "reason": "Zone unoccupied - dim to 20%",
      "system": "lighting"
    }}
  ],
  "cross_system_recommendations": [
    {{
      "zone_id": "Zone-L11-S",
      "zone_name": "Level 11 South",
      "hvac_action": "Raise setpoint +2°C",
      "lighting_action": "Dim to 20%",
      "reason": "Zone unoccupied - coordinated energy savings",
      "combined_savings_kw": 1.2
    }}
  ],
  "projected_savings": {{
    "hvac_kwh": 12.5,
    "lighting_kwh": 3.2,
    "energy_kwh": 15.7,
    "cost_zar_per_hour": 39.25,
    "percentage_improvement": 12.5
  }},
  "confidence": 0.85,
  "reasoning": "Summary of why these changes are recommended"
}}
```

Provide ONLY the JSON response, no additional text."""

        return prompt

    async def _analyze_with_claude(
        self,
        site_id: str,
        prompt: str,
        current_conditions: Dict[str, Any],
        hvac_devices: List[Device],
        dali_zones: Optional[Dict[str, Any]] = None,
    ) -> OptimizationRecommendation:
        """Analyze using Claude AI."""
        try:
            logger.info(f"Using Claude AI for optimization of site {site_id}")

            # Call Claude (synchronous call for analysis)
            import asyncio

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
                )

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Claude response as JSON: {e}")
                logger.debug(f"Response text: {response_text}")
                # Fall back to rule-based
                raise

        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            raise

    def _find_device_by_type(self, hvac_devices: List[Device], hvac_type: str) -> Optional[Device]:
        """Find a device by its hvac_type (zone_controller, chiller, chw_system, etc.)."""
        for device in hvac_devices:
            if hasattr(device, 'hvac_type') and device.hvac_type == hvac_type:
                return device
        return None

    def _find_devices_by_type(self, hvac_devices: List[Device], hvac_type: str) -> List[Device]:
        """Find ALL devices of a specific hvac_type."""
        return [d for d in hvac_devices if hasattr(d, 'hvac_type') and d.hvac_type == hvac_type]

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
            hvac_type = getattr(d, 'hvac_type', 'unknown')
            location = getattr(d, 'location', 'unknown location')
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

    # Zone-Aware Optimization Helper Methods

    def _group_devices_by_zone(self, hvac_devices: List[Device]) -> Dict[str, List[Device]]:
        """Group devices by their zone name for coordinated optimization."""
        zones: Dict[str, List[Device]] = {}
        for device in hvac_devices:
            zone = getattr(device.device_location, 'zone', 'Unknown') if hasattr(device, 'device_location') else 'Unknown'
            if zone not in zones:
                zones[zone] = []
            zones[zone].append(device)
        return zones

    def _group_devices_by_floor(self, hvac_devices: List[Device]) -> Dict[str, List[Device]]:
        """Group devices by floor level."""
        floors: Dict[str, List[Device]] = {}
        for device in hvac_devices:
            floor = getattr(device.device_location, 'floor', 'Unknown') if hasattr(device, 'device_location') else 'Unknown'
            if floor not in floors:
                floors[floor] = []
            floors[floor].append(device)
        return floors

    def _get_zone_priority(self, device: Device) -> int:
        """Get zone priority for load shedding ordering (1=highest priority, 5=lowest)."""
        if hasattr(device, 'device_location') and device.device_location:
            return getattr(device.device_location, 'zone_priority', 3)
        return 3  # Default to middle priority

    def _get_zone_type(self, device: Device) -> Optional[ZoneType]:
        """Get the zone type for a device."""
        if hasattr(device, 'device_location') and device.device_location:
            return getattr(device.device_location, 'zone_type', None)
        return None

    def _get_exposure(self, device: Device) -> Optional[ExposureDirection]:
        """Get the exposure direction for a device."""
        if hasattr(device, 'device_location') and device.device_location:
            return getattr(device.device_location, 'exposure', None)
        return None

    def _get_floor_level(self, device: Device) -> int:
        """Get numeric floor level from device location.

        Returns:
            Floor level as integer (-1=basement, 0=ground, 1+=upper floors)
        """
        if not hasattr(device, 'device_location') or not device.device_location:
            return 0

        floor = getattr(device.device_location, 'floor', 'Ground')
        if floor == 'Basement':
            return -1
        elif floor == 'Ground':
            return 0
        elif floor == 'Roof':
            return 99  # High number for roof
        elif floor.startswith('FL'):
            try:
                return int(floor[2:])
            except ValueError:
                return 0
        return 0

    def _get_exposure_modifier(self, device: Device, outdoor_temp: float) -> float:
        """Get temperature adjustment based on exposure direction and outdoor temp.

        In the Southern Hemisphere (South Africa):
        - South-facing zones receive maximum solar radiation
        - North-facing zones receive minimal direct sun
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
            ExposureDirection.SOUTH: 1.5 if 10 <= hour <= 16 else 0.5,  # Max solar gain midday
            ExposureDirection.WEST: 1.0 if 14 <= hour <= 18 else 0.0,   # Afternoon heat
            ExposureDirection.EAST: 1.0 if 6 <= hour <= 10 else 0.0,    # Morning heat
            ExposureDirection.NORTH: 0.0,                                # Minimal gain in SA
            ExposureDirection.INTERIOR: -0.5,                            # Slightly less cooling needed
        }
        return modifiers.get(exposure, 0.0)

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

            zone_type_str = zone_type.value if zone_type else 'unknown'
            exposure_str = exposure.value if exposure else 'unknown'
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
                        lighting.avg_dim_level > 50 and
                        occupancy.occupancy_percent < 20 if (lighting and occupancy) else False
                    ),
                }

        except Exception as e:
            logger.warning(f"Failed to gather DALI zone data: {e}")

        return zone_data

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
            lighting_type = getattr(d, 'lighting_type', 'unknown')
            location = getattr(d, 'location', 'unknown location')
            lines.append(f"- {d.id}: {d.name} ({lighting_type}) at {location}")
        return "\n".join(lines)

    def _should_skip_zone_optimization(self, device: Device, zone_type: Optional[ZoneType]) -> bool:
        """Check if zone type should have restricted optimization.

        Server rooms and critical zones should not have cooling reduced.
        """
        if zone_type == ZoneType.SERVER_ROOM:
            return True  # Never reduce cooling in server rooms
        return False

    def _get_zone_specific_setpoint_limits(
        self, device: Device, zone_type: Optional[ZoneType]
    ) -> tuple:
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
            # Reduce setpoint increase due to roof heat gain
            adjusted_change *= 0.7
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
        hvac_devices: List[Device],
        dali_zones: Optional[Dict[str, Any]] = None,
    ) -> OptimizationRecommendation:
        """Fallback rule-based optimization for HVAC and lighting."""
        logger.info(f"Using rule-based optimization for site {site_id}")
        dali_zones = dali_zones or {}

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
                d for d in hvac_devices
                if self._has_any_point(d, ["zone_cooling_setpoint", "cooling_setpoint"])
                and getattr(d, 'hvac_type', '') != 'fcu'
            ]

        chw_systems = self._find_devices_by_type(hvac_devices, "chw_system")
        if not chw_systems:
            # Fall back to devices with CHW setpoint
            chw_systems = [
                d for d in hvac_devices
                if self._has_any_point(d, ["chw_supply_temp_setpoint", "supply_temp_setpoint"])
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
                recommendations.append({
                    "equipment_id": device.id,
                    "equipment_name": device.name,
                    "point_name": point_name,
                    "current_value": current_value,
                    "recommended_value": recommended_value,
                    "unit": "°C",
                    "reason": reason,
                })

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
                    adjusted_change = self._apply_zone_aware_adjustments(
                        zone_controller, 1.5, outdoor_temp
                    )

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
                            f"Increase setpoint {adjusted_change:.1f}°C{zone_info} as outdoor temp rising to {outdoor_temp}°C - reduces cooling load while maintaining comfort",
                        )

        # Rule 2: Humidity optimization for ALL zone controllers with humidity setpoint
        if humidity < 50.0:
            for zone_controller in zone_controllers:
                if "humidity_setpoint" in zone_controller.points:
                    current_humidity_sp = zone_controller.points.get("humidity_setpoint")
                    current_value = current_humidity_sp.default_value if current_humidity_sp else 55.0
                    new_humidity = min(current_value + 3.0, 60.0)

                    add_recommendation(
                        zone_controller,
                        "humidity_setpoint",
                        current_value,
                        new_humidity,
                        f"Allow humidity to rise 3% as outdoor humidity drops - reduces dehumidification energy",
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
                        f"Increase CHW temp 1.5°C for higher chiller efficiency with rising outdoor temps",
                    )

        # Rule 4: FCU optimization for ALL FCUs (ZONE-AWARE)
        # Optimize fan speed and setpoints based on conditions and zone type
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
                            f"Increase FCU setpoint {adjusted_change:.1f}°C{zone_info}{exposure_info} to reduce cooling load during high outdoor temps ({outdoor_temp}°C)",
                        )

                # Optimize fan speed if available and conditions warrant
                # Don't reduce fan speed in executive zones (comfort priority)
                if "fan_speed" in fcu.points and temp_diff < 5.0 and zone_type not in [ZoneType.EXECUTIVE, ZoneType.SERVER_ROOM]:
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
                            f"Reduce fan speed 10% for energy savings - moderate temperature differential allows lower airflow",
                        )

        # ============================================================
        # DALI Lighting Optimization Rules
        # ============================================================
        lighting_recommendations = []
        cross_system_recommendations = []
        lighting_savings_kw = 0.0

        if dali_zones:
            for zone_id, zone in dali_zones.items():
                occupancy = zone.get("occupancy", {})
                lighting = zone.get("lighting", {})
                is_occupied = zone.get("is_occupied", True)
                has_high_daylight = zone.get("has_high_daylight", False)

                # Skip if no lighting data
                if not lighting:
                    continue

                current_dim = lighting.get("avg_brightness", 0)
                total_power = lighting.get("total_power_watts", 0)
                zone_name = zone.get("zone_name", zone_id)
                is_emergency = "emergency" in zone_name.lower()

                # Rule 5: Unoccupied zone dimming
                # Dim to 20% (level 51) if zone is unoccupied
                if not is_occupied and current_dim > 25:  # 25 = ~10%, 51 = ~20%
                    # Don't dim emergency zones below 70%
                    target_dim = 178 if is_emergency else 51

                    if current_dim > target_dim:
                        power_saved = total_power * (1 - target_dim / 254)
                        lighting_savings_kw += power_saved / 1000

                        lighting_recommendations.append({
                            "equipment_id": zone_id,
                            "equipment_name": zone_name,
                            "point_name": "dim_level",
                            "current_value": int(current_dim * 254 / 100),  # Convert % to DALI level
                            "recommended_value": target_dim,
                            "unit": "level",
                            "reason": f"Zone unoccupied ({occupancy.get('occupancy_percent', 0):.0f}% sensors active) - dim to {target_dim * 100 // 254}% for safety lighting",
                            "system": "lighting",
                        })

                        # Add cross-system recommendation for coordinated action
                        cross_system_recommendations.append({
                            "zone_id": zone_id,
                            "zone_name": zone_name,
                            "hvac_action": "Raise setpoint +2°C",
                            "lighting_action": f"Dim to {target_dim * 100 // 254}%",
                            "reason": "Zone unoccupied - coordinated energy savings",
                            "combined_savings_kw": round(power_saved / 1000 + 0.5, 2),  # Estimate HVAC savings
                        })

                # Rule 6: Daylight harvesting
                # If lux > setpoint (500), dim proportionally
                elif is_occupied and has_high_daylight and current_dim > 50:
                    avg_lux = occupancy.get("avg_lux_level", 0)
                    daylight_excess = (avg_lux - 500) / 500  # How much over setpoint
                    dim_reduction = min(daylight_excess * 30, 40)  # Max 40% reduction

                    target_dim = max(current_dim - dim_reduction, 30)  # Never below 30%

                    if current_dim - target_dim > 10:  # Only recommend if meaningful
                        power_saved = total_power * dim_reduction / 100
                        lighting_savings_kw += power_saved / 1000

                        lighting_recommendations.append({
                            "equipment_id": zone_id,
                            "equipment_name": zone_name,
                            "point_name": "dim_level",
                            "current_value": int(current_dim * 254 / 100),
                            "recommended_value": int(target_dim * 254 / 100),
                            "unit": "level",
                            "reason": f"Daylight harvesting - avg lux {avg_lux:.0f} exceeds setpoint 500, dim to {target_dim:.0f}%",
                            "system": "lighting",
                        })

        # Merge lighting recommendations with HVAC recommendations
        for rec in lighting_recommendations:
            recommendations.append(rec)

        # Sort recommendations by zone priority (critical zones first)
        recommendations = self._sort_recommendations_by_priority(recommendations, hvac_devices)

        # Calculate projected savings based on number and type of recommendations
        hvac_recs = [r for r in recommendations if r.get("system") != "lighting"]
        lighting_recs = [r for r in recommendations if r.get("system") == "lighting"]

        hvac_savings = 5.0 + (len(hvac_recs) * 4.5)  # kWh base for HVAC
        lighting_savings = lighting_savings_kw  # Calculated above for lighting

        energy_savings = hvac_savings + lighting_savings
        energy_rate = energy_prices.get("current_rate", 2.50)
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

        # Add zone-aware context to reasoning
        zone_context = []
        for rec in recommendations:
            device = next((d for d in hvac_devices if d.id == rec["equipment_id"]), None)
            if device:
                zone_type = self._get_zone_type(device)
                if zone_type and zone_type.value not in zone_context:
                    zone_context.append(zone_type.value)

        reasoning = f"Rising outdoor temperatures ({outdoor_temp}°C) with current conditions require proactive optimization. "
        if reasoning_parts:
            reasoning += f"Recommendations include: {', '.join(reasoning_parts)}. "
        if zone_context:
            reasoning += f"Zone-aware adjustments applied for: {', '.join(zone_context)} zones. "
        if cross_system_recommendations:
            reasoning += f"Coordinated {len(cross_system_recommendations)} cross-system optimizations. "
        reasoning += f"All recommendations within safety limits and sorted by zone priority."

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

        return OptimizationRecommendation(
            site_id=site_id,
            timestamp=datetime.now().isoformat(),
            recommendations=recommendations,
            projected_savings={
                "hvac_kwh": round(hvac_savings, 1),
                "lighting_kwh": round(lighting_savings, 1),
                "energy_kwh": round(energy_savings, 1),
                "cost_zar_per_hour": round(cost_savings, 2),
                "percentage_improvement": round(percentage, 1),
            },
            confidence=confidence + (0.05 * len(recommendations)),  # Higher confidence with more recommendations
            reasoning=reasoning,
            cross_system_recommendations=cross_system_recommendations if cross_system_recommendations else None,
            lighting_summary=lighting_summary,
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
        adjusted_savings["cost_zar_per_hour"] = round(adjusted_savings.get("cost_zar_per_hour", 0) * savings_multiplier, 2)
        adjusted_savings["percentage_improvement"] = round(
            min(adjusted_savings.get("percentage_improvement", 0) * savings_multiplier, 25.0), 1
        )

        return OptimizationRecommendation(
            site_id=site_id,
            timestamp=datetime.now().isoformat(),
            recommendations=filtered_recs,
            projected_savings=adjusted_savings,
            confidence=recommendation.confidence,
            reasoning=f"Load shedding Stage {load_shedding_stage}: Maintaining P1-P{max_priority_to_maintain} zones at normal comfort. "
                      f"Lower priority zones (P{max_priority_to_maintain + 1}-P5) receive more aggressive optimization. "
                      f"{recommendation.reasoning}",
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
                    validation_results.append({
                        "equipment_id": equipment_id,
                        "point_name": point_name,
                        "allowed": False,
                        "reason": f"Device {equipment_id} not found",
                    })
                    all_allowed = False
                    continue

                # Validate against safety rules
                if not safety_engine._initialized:
                    await safety_engine.initialize()

                safety_result = await safety_engine.validate_control(device, point_name, value)

                validation_results.append({
                    "equipment_id": equipment_id,
                    "point_name": point_name,
                    "allowed": safety_result["allowed"],
                    "reason": safety_result.get("message", ""),
                    "warnings": safety_result.get("warnings", []),
                })

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


# Global service instance
ai_optimizer_service = AIOptimizerService()
