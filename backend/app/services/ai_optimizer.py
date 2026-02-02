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
from app.services.claude_service import claude_service
from app.services.device_abstraction import device_manager
from app.services.safety_interlocks import safety_engine

logger = logging.getLogger(__name__)

# Data directory for sites
DATA_DIR = Path(__file__).parent.parent / "data"


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

        # Build optimization prompt for Claude
        prompt = self._build_optimization_prompt(
            site, current_conditions, weather_forecast, energy_prices, hvac_devices
        )

        try:
            # Try to use Claude for analysis
            if self._claude_service.is_configured():
                recommendation = await self._analyze_with_claude(
                    site_id, prompt, current_conditions, hvac_devices
                )
            else:
                # Fall back to rule-based optimization
                recommendation = self._analyze_with_rules(
                    site_id, current_conditions, weather_forecast, energy_prices, hvac_devices
                )

            return recommendation

        except Exception as e:
            logger.error(f"Error analyzing building {site_id}: {e}")
            # Fall back to rule-based optimization
            return self._analyze_with_rules(
                site_id, current_conditions, weather_forecast, energy_prices, hvac_devices
            )

    async def _gather_current_conditions(self, site_id: str) -> Dict[str, Any]:
        """Gather current building conditions from devices."""
        try:
            devices = await device_manager.list_devices_by_site(site_id)

            conditions = {
                "indoor_temp": 22.0,
                "outdoor_temp": 28.0,
                "humidity": 55.0,
                "occupancy": "high",
                "equipment_status": "normal",
                "timestamp": datetime.now().isoformat(),
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
    ) -> str:
        """Build optimization prompt for Claude."""
        prompt = f"""You are an expert HVAC optimization engineer. Analyze the following building data and recommend optimal setpoints for energy efficiency and occupant comfort.

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

**Your Task:**
1. Analyze the current conditions vs outdoor weather
2. Consider energy pricing (higher rates = more aggressive optimization)
3. Apply zone-aware rules based on zone_type and exposure
4. Recommend specific HVAC setpoint changes
5. IMPORTANT: Use the EXACT point_name from the "Available Control Points" list above
6. Project energy savings in ZAR per hour
7. Ensure all recommendations are within safety limits for each zone type

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
      "reason": "Brief explanation"
    }}
  ],
  "projected_savings": {{
    "energy_kwh": 12.5,
    "cost_zar_per_hour": 31.25,
    "percentage_improvement": 8.5
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
    ) -> OptimizationRecommendation:
        """Fallback rule-based optimization."""
        logger.info(f"Using rule-based optimization for site {site_id}")

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

        # Sort recommendations by zone priority (critical zones first)
        recommendations = self._sort_recommendations_by_priority(recommendations, hvac_devices)

        # Calculate projected savings based on number and type of recommendations
        base_savings = 5.0  # kWh base
        energy_savings = base_savings + (len(recommendations) * 4.5)
        energy_rate = energy_prices.get("current_rate", 2.50)
        cost_savings = energy_savings * energy_rate
        percentage = min(8.0 + (len(recommendations) * 2.0), 15.0)

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
        reasoning += f"All recommendations within safety limits and sorted by zone priority."

        return OptimizationRecommendation(
            site_id=site_id,
            timestamp=datetime.now().isoformat(),
            recommendations=recommendations,
            projected_savings={
                "energy_kwh": round(energy_savings, 1),
                "cost_zar_per_hour": round(cost_savings, 2),
                "percentage_improvement": round(percentage, 1),
            },
            confidence=confidence + (0.05 * len(recommendations)),  # Higher confidence with more recommendations
            reasoning=reasoning,
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
