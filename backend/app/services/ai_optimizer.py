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
from app.models.device import Device, DeviceType
from app.services.claude_service import claude_service
from app.services.device_abstraction import device_manager
from app.services.safety_interlocks import safety_engine

logger = logging.getLogger(__name__)

# Data directory for sites
DATA_DIR = Path(__file__).parent.parent / "data"


def load_sites() -> List[Dict[str, Any]]:
    """Load sites data from JSON file."""
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

**HVAC Equipment on Site:**
{len(hvac_devices)} devices available

**Building Constraints (SAFETY LIMITS - MUST NOT EXCEED):**
- CHW temperature: 5-15°C (minimum 5°C to prevent freeze damage)
- Zone temperature setpoints: 20-26°C (comfort range)
- Humidity: 30-65% RH

**Your Task:**
1. Analyze the current conditions vs outdoor weather
2. Consider energy pricing (higher rates = more aggressive optimization)
3. Recommend specific HVAC setpoint changes
4. Project energy savings in ZAR per hour
5. Ensure all recommendations are within safety limits

**Response Format (JSON):**
```json
{{
  "recommendations": [
    {{
      "device_id": "device-id",
      "device_name": "Device Name",
      "point_name": "setpoint",
      "current_value": 22.0,
      "recommended_value": 23.0,
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
        temp_diff = outdoor_temp - indoor_temp

        recommendations = []
        confidence = 0.7  # Lower confidence for rule-based

        # Simple rule: if outdoor > indoor + 3°C, recommend increasing setpoint slightly
        if temp_diff > 3.0 and indoor_temp < 24.0:
            new_setpoint = min(indoor_temp + 1.0, 24.0)
            recommendations.append({
                "device_id": hvac_devices[0].id if hvac_devices else "hvac-main",
                "device_name": hvac_devices[0].name if hvac_devices else "Main HVAC",
                "point_name": "cooling_setpoint",
                "current_value": indoor_temp,
                "recommended_value": new_setpoint,
                "reason": f"Outdoor temp {outdoor_temp}°C is {temp_diff:.1f}°C higher than indoor. Raising setpoint reduces cooling load while maintaining comfort.",
            })

        # Calculate projected savings
        energy_savings = len(recommendations) * 2.5  # kWh
        cost_savings = energy_savings * energy_prices.get("current_rate", 2.50)

        return OptimizationRecommendation(
            site_id=site_id,
            timestamp=datetime.now().isoformat(),
            recommendations=recommendations,
            projected_savings={
                "energy_kwh": energy_savings,
                "cost_zar_per_hour": cost_savings,
                "percentage_improvement": 5.0,
            },
            confidence=confidence,
            reasoning=f"Rule-based optimization: {len(recommendations)} recommendations based on temperature differential.",
        )

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
                device_id = rec.get("device_id")
                point_name = rec.get("point_name")
                value = rec.get("recommended_value")

                # Find device
                device = next((d for d in devices if d.id == device_id), None)
                if not device:
                    validation_results.append({
                        "device_id": device_id,
                        "point_name": point_name,
                        "allowed": False,
                        "reason": f"Device {device_id} not found",
                    })
                    all_allowed = False
                    continue

                # Validate against safety rules
                if not safety_engine._initialized:
                    await safety_engine.initialize()

                safety_result = await safety_engine.validate_control(device, point_name, value)

                validation_results.append({
                    "device_id": device_id,
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
