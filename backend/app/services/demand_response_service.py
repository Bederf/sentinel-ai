"""Demand Response Service for calculating curtailable HVAC load.

This service assembles a real-time signal for how much HVAC load can be safely
curtailed, for how long, and with what confidence. Used by BESS controllers
and demand response aggregators (IES, LTM Energy / eSUMS).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from app.database.supabase_client import get_supabase_client
from app.models.demand_response_models import (
    CurtailableLoadResponse,
    ZoneCurtailableLoad,
)
from app.services.eskomsepush_service import eskomsepush_service
from app.services.thermal_model import calculate_thermal_runway

logger = logging.getLogger(__name__)

# Constants
MAX_DATA_AGE_SECONDS = 360  # 6 minutes — shadow mode polls every 5 min, allow 60s margin
DDMP_MIN_LOAD_KW = 200.0  # 0.2 MW minimum for Commercial/Industrial Load Management (Eskom DDMP)
DDMP_MIN_DURATION_MINUTES = 60  # 1 hour minimum


class DemandResponseService:
    """Service for calculating curtailable load signals."""

    async def get_curtailable_load(
        self,
        site_id: str,
        min_priority: int = 3,
        include_zones: bool = True,
    ) -> CurtailableLoadResponse:
        """Assemble curtailable load signal from existing Sentinel building blocks.

        Algorithm:
        1. Validate site exists
        2. Get thermal runway minutes
        3. Get current HVAC load from energy centre
        4. Get zones with priority >= min_priority
        5. Calculate per-zone curtailable load
        6. Sum and calculate confidence
        7. Return assembled response
        """
        # Step 1: Validate site exists
        site = await self._get_site(site_id)
        if not site:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        # Step 2: Get thermal runway (safe duration)
        thermal_runway_minutes = await self._get_thermal_runway(site_id)

        # Step 3: Get current HVAC load from power summary
        power_summary = await self._get_power_summary(site_id)
        total_hvac_kw = power_summary.get("hvac_kw", 0.0)

        # Step 4: Get zones and calculate curtailable load
        zones = await self._get_zones(site_id, min_priority)
        zone_breakdown: list[ZoneCurtailableLoad] = []

        # For real buildings: use aggregate HVAC load and estimate curtailment
        # based on which zones have equipment that can be reduced
        total_zones_with_equipment = sum(1 for z in zones if z.get("equipment_count", 0) > 0)

        if total_zones_with_equipment > 0 and total_hvac_kw > 0:
            # Estimate: 60% of HVAC load is curtailable (fans, pumps, non-critical cooling)
            # This is a conservative estimate for real buildings
            total_curtailable_kw = total_hvac_kw * 0.60

            # Distribute across zones proportionally by equipment count
            total_equipment = sum(z.get("equipment_count", 0) for z in zones)

            for zone in zones:
                zone_equipment = zone.get("equipment_count", 0)
                zone_temp_c = zone.get("current_temp_c")
                zone_setpoint_c = zone.get("setpoint_c")

                # Zone's share of curtailable load
                if total_equipment > 0:
                    total_hvac_kw * (zone_equipment / total_equipment)
                    zone_curtailable_kw = total_curtailable_kw * (zone_equipment / total_equipment)
                else:
                    zone_curtailable_kw = 0.0

                if include_zones:
                    zone_breakdown.append(
                        ZoneCurtailableLoad(
                            zone_id=zone["id"],
                            zone_name=zone.get("name", zone["id"]),
                            priority=zone.get("priority", 3),
                            curtailable_kw=round(zone_curtailable_kw, 1),
                            current_temp_c=zone_temp_c,
                            setpoint_c=zone_setpoint_c,
                            headroom_c=None,
                            equipment_count=zone_equipment,
                        )
                    )
        else:
            total_curtailable_kw = 0.0

        # No temperature headroom data available for real building
        min_headroom_c = 2.0  # Assume safe headroom
        zones_at_boundary = 0
        zones_with_live_data = len([z for z in zones if z.get("equipment_count", 0) > 0])

        # Step 5: Get BESS SOC
        bess_soc_pct = await self._get_bess_soc(site_id)

        # Step 6: Get Eskom status
        eskom_stage = 0
        is_load_shedding_active = False
        try:
            if eskomsepush_service.is_configured:
                status = await eskomsepush_service.get_combined_status()
                eskom_stage = status.eskom.stage
                is_load_shedding_active = eskom_stage > 0
        except Exception as e:
            logger.warning(f"Failed to get Eskom status: {e}")

        # Step 7: Calculate data freshness
        data_freshness_seconds = await self._get_data_freshness_seconds(site_id)

        # Guard: fail if data is stale
        if data_freshness_seconds > MAX_DATA_AGE_SECONDS:
            raise HTTPException(
                status_code=503,
                detail=f"Insufficient live sensor data for site {site_id}. "
                f"Last reading: {data_freshness_seconds} seconds ago.",
            )

        # Step 8: Calculate confidence and zone coverage
        total_zones = len(zones) if zones else 1
        zone_coverage_ratio = zones_with_live_data / total_zones if total_zones > 0 else 0.0
        confidence = self._calculate_confidence(
            data_freshness_seconds=data_freshness_seconds,
            zones_with_live_data=zones_with_live_data,
            total_zones=total_zones,
            thermal_runway_confidence=0.85,  # Default from thermal model
        )

        # Step 9: Identify limiting factor
        limiting_factor = self._identify_limiting_factor(
            thermal_runway_minutes=thermal_runway_minutes,
            min_headroom_c=min_headroom_c if min_headroom_c != float("inf") else 2.0,
            bess_soc_pct=bess_soc_pct,
            zones_at_boundary=zones_at_boundary,
        )

        # Step 10: Calculate DDMP eligibility
        ddmp_eligible = self._calculate_ddmp_eligible(
            curtailable_load_kw=total_curtailable_kw,
            safe_duration_minutes=thermal_runway_minutes,
            bess_soc_pct=bess_soc_pct,
        )

        # Update Prometheus metrics (after all calculations are complete)
        try:
            from app.api.metrics import (
                sentinel_bess_soc_percent,
                sentinel_confidence_score,
                sentinel_curtailable_load_kw,
                sentinel_data_freshness_seconds,
                sentinel_ddmp_eligible,
                sentinel_safe_duration_minutes,
                sentinel_thermal_runway_minutes,
                sentinel_zone_coverage_percent,
            )

            sentinel_curtailable_load_kw.labels(site_id=site_id, customer="sentinel-internal").set(total_curtailable_kw)

            sentinel_safe_duration_minutes.labels(site_id=site_id).set(thermal_runway_minutes)

            sentinel_confidence_score.labels(site_id=site_id).set(confidence)

            sentinel_ddmp_eligible.labels(site_id=site_id).set(1 if ddmp_eligible else 0)

            sentinel_data_freshness_seconds.labels(site_id=site_id).set(data_freshness_seconds)

            sentinel_thermal_runway_minutes.labels(site_id=site_id).set(thermal_runway_minutes)

            sentinel_zone_coverage_percent.labels(site_id=site_id).set(zone_coverage_ratio)

            if bess_soc_pct is not None:
                sentinel_bess_soc_percent.labels(site_id=site_id, battery_id="primary").set(bess_soc_pct)
        except Exception:
            pass  # Don't let metrics break the API

        # Step 11: Save to DB for Prometheus metrics (async fire-and-forget)
        await self._save_calculation_to_db(
            site_id=site_id,
            curtailable_load_kw=total_curtailable_kw,
            safe_duration_minutes=thermal_runway_minutes,
            confidence=confidence,
            ddmp_eligible=ddmp_eligible,
            data_freshness_seconds=data_freshness_seconds,
            thermal_runway_minutes=thermal_runway_minutes,
            zone_coverage_percent=zone_coverage_ratio,
            bess_soc_pct=bess_soc_pct,
            limiting_factor=limiting_factor,
        )

        return CurtailableLoadResponse(
            site_id=site_id,
            timestamp=datetime.now(UTC),
            curtailable_load_kw=round(total_curtailable_kw, 1),
            safe_duration_minutes=thermal_runway_minutes,
            confidence=confidence,
            limiting_factor=limiting_factor,
            eskom_stage=eskom_stage,
            is_load_shedding_active=is_load_shedding_active,
            ddmp_eligible=ddmp_eligible,
            bess_soc_pct=bess_soc_pct,
            zone_breakdown=zone_breakdown,
            data_freshness_seconds=data_freshness_seconds,
            calculation_method="thermal_runway_zone_priority",
        )

    async def _get_site(self, site_id: str) -> dict[str, Any] | None:
        """Get site from Supabase."""
        try:
            client = get_supabase_client()
            response = client.table("sites").select("*").eq("code", site_id).limit(1).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to get site {site_id}: {e}")
            return None

    async def _get_thermal_runway(self, site_id: str) -> int:
        """Get thermal runway minutes for the site."""
        try:
            # Use building params from thermal_model defaults
            building_params = {"thermal_mass": 0.8, "insulation_factor": 0.6, "internal_heat_gain": 0.5}
            weather_forecast = {"outside_temp": 32.0, "solar_load": 0.7, "humidity": 65}

            # Get current temperature from telemetry
            current_temp = await self._get_site_temperature(site_id)
            comfort_limit = 26.0

            runway = calculate_thermal_runway(
                current_temp=current_temp,
                comfort_limit=comfort_limit,
                building_params=building_params,
                weather_forecast=weather_forecast,
            )
            return runway
        except Exception as e:
            logger.warning(f"Failed to calculate thermal runway: {e}")
            return 60  # Default fallback

    async def _get_site_temperature(self, site_id: str) -> float:
        """Get current site temperature from sensor readings."""
        try:
            client = get_supabase_client()
            response = (
                client.table("equipment_sensor_readings")
                .select("value, recorded_at")
                .eq("site_id", site_id)
                .ilike("metric_name", "%temp%")
                .order("recorded_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data:
                return float(response.data[0]["value"])
            return 22.0  # Default
        except Exception as e:
            logger.debug(f"Failed to get site temperature: {e}")
            return 22.0

    async def _get_power_summary(self, site_id: str) -> dict[str, float]:
        """Get power summary from Supabase sensor readings."""
        try:
            client = get_supabase_client()

            # Get latest HVAC power reading from aggregate meter
            response = (
                client.table("equipment_sensor_readings")
                .select("value, recorded_at")
                .eq("site_id", site_id)
                .eq("sensor_type", "hvac_kw")
                .order("recorded_at", desc=True)
                .limit(1)
                .execute()
            )

            if response.data:
                hvac_kw = float(response.data[0]["value"])
                return {"hvac_kw": hvac_kw, "total_kw": hvac_kw}

            return {"hvac_kw": 0.0, "total_kw": 0.0}
        except Exception as e:
            logger.warning(f"Failed to get power summary from Supabase: {e}")
            return {"hvac_kw": 0.0, "total_kw": 0.0}

    async def _get_zones(self, site_id: str, min_priority: int) -> list[dict[str, Any]]:
        """Get zones for site with priority >= min_priority.

        Zone codes are derived from equipment IDs: S002-{TYPE}-{ZONE_CODE}
        Zone code format: {FLOOR}{ZONE_NUM} (e.g., 105 = Level 1, Zone 5)
        """
        try:
            client = get_supabase_client()

            # Get site UUID
            site_response = client.table("sites").select("id").eq("code", site_id).limit(1).execute()
            if not site_response.data:
                return []
            site_uuid = site_response.data[0]["id"]

            # Get all HVAC equipment for this site (types are lowercase in DB)
            equip_response = (
                client.table("equipment")
                .select("code, type")
                .eq("site_id", site_uuid)
                .in_("type", ["ahu", "chiller", "fcu", "vav", "vrf", "split_unit", "rtu"])
                .execute()
            )

            # Extract zone codes from equipment IDs
            # Format: S002-AHU-105 -> zone_code = 105
            import re

            zone_equipment = {}  # zone_code -> list of equipment codes

            for equip in equip_response.data or []:
                equip_code = equip.get("code", "")
                # Extract zone code from end of equipment code
                match = re.search(r"-([0-9RBrb][0-9]{2})$", equip_code)
                if match:
                    zone_code = match.group(1).upper()  # e.g., "105", "R01", "B01"
                    if zone_code not in zone_equipment:
                        zone_equipment[zone_code] = []
                    zone_equipment[zone_code].append(equip_code)

            # Build zone list from discovered zone codes
            zones = []
            for zone_code in sorted(zone_equipment.keys()):
                # Parse floor from zone code
                if zone_code.startswith("R"):
                    floor = "Roof"
                    zone_num = zone_code[1:]
                elif zone_code.startswith("B"):
                    floor = "Basement"
                    zone_num = zone_code[1:]
                else:
                    floor_num = zone_code[0]
                    zone_num = zone_code[1:]
                    floor = f"Level {floor_num}"

                # Determine priority (default P3, critical zones can be configured)
                # Server rooms, data centers = P1, Executive = P2, Standard = P3
                # For now, assume all are P3 (standard offices)
                priority = 3

                # Skip if below min_priority
                if priority < min_priority:
                    continue

                zones.append(
                    {
                        "id": zone_code,  # e.g., "105"
                        "name": f"{floor} Zone {zone_num}",
                        "priority": priority,
                        "equipment_count": len(zone_equipment[zone_code]),
                        "equipment_codes": zone_equipment[zone_code],
                        "current_temp_c": None,
                        "setpoint_c": None,
                    }
                )

            logger.info(f"Found {len(zones)} zones with {sum(len(v) for v in zone_equipment.values())} HVAC equipment")
            return zones

        except Exception as e:
            logger.error(f"Failed to get zones: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return []

    async def _get_zone_hvac_load(self, site_id: str, zone: dict[str, Any]) -> float:
        """Get current HVAC load for a zone from sensor readings.

        Uses equipment_codes from zone dict (extracted from asset IDs).
        """
        try:
            client = get_supabase_client()

            equipment_codes = zone.get("equipment_codes", [])
            if not equipment_codes:
                return 0.0

            # Sum power readings for this equipment
            # Normalize to Supabase format: site-002 → S002
            from app.core.site_resolver import normalize_site_id

            supabase_site_id = normalize_site_id(site_id, to_supabase=True)
            power_response = (
                client.table("equipment_sensor_readings")
                .select("value")
                .eq("site_id", supabase_site_id)
                .in_("equipment_id", equipment_codes)
                .ilike("sensor_type", "%power%")
                .gte("recorded_at", (datetime.now(UTC) - timedelta(minutes=5)).isoformat())
                .execute()
            )

            total_kw = sum(float(r["value"]) for r in power_response.data) if power_response.data else 0.0
            return total_kw

        except Exception as e:
            logger.debug(f"Failed to get zone HVAC load: {e}")
            return 0.0

    async def _get_bess_soc(self, site_id: str) -> float | None:
        """Get latest BESS SOC from solar_hourly_snapshots."""
        try:
            client = get_supabase_client()
            response = (
                client.table("solar_hourly_snapshots")
                .select("bess_soc_pct, created_at")
                .eq("site_id", site_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data:
                return float(response.data[0]["bess_soc_pct"])
            return None
        except Exception as e:
            logger.debug(f"Failed to get BESS SOC: {e}")
            return None

    async def _get_data_freshness_seconds(self, site_id: str) -> int:
        """Get seconds since last sensor reading."""
        try:
            client = get_supabase_client()
            response = (
                client.table("equipment_sensor_readings")
                .select("recorded_at")
                .eq("site_id", site_id)
                .order("recorded_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data:
                last_reading = datetime.fromisoformat(response.data[0]["recorded_at"].replace("Z", "+00:00"))
                delta = datetime.now(UTC) - last_reading
                return int(delta.total_seconds())
            return 999999  # No data
        except Exception as e:
            logger.debug(f"Failed to get data freshness: {e}")
            return 999999

    def _calculate_zone_curtailable_kw(
        self,
        zone_current_load_kw: float,
        zone_temp_c: float | None,
        zone_setpoint_c: float | None,
        thermal_runway_minutes: int,
        zone_priority: int,
    ) -> float:
        """Calculate how much of a zone's current HVAC load can be curtailed."""
        # Priority multiplier
        priority_multiplier = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.0, 5: 1.0}.get(zone_priority, 0.0)

        if priority_multiplier == 0.0:
            return 0.0

        # Calculate headroom
        if zone_temp_c is not None and zone_setpoint_c is not None:
            headroom = abs(zone_setpoint_c - zone_temp_c)
        else:
            # No temperature data - assume safe curtailment
            return zone_current_load_kw * 0.5 * priority_multiplier

        # Apply headroom rules
        if headroom >= 2.0:
            # Full curtailment eligible
            curtailable = zone_current_load_kw * 0.85 * priority_multiplier
        elif headroom >= 1.0:
            # Partial curtailment
            curtailable = zone_current_load_kw * (headroom / 2.0) * 0.85 * priority_multiplier
        else:
            # At comfort boundary
            curtailable = 0.0

        return curtailable

    def _calculate_confidence(
        self,
        data_freshness_seconds: int,
        zones_with_live_data: int,
        total_zones: int,
        thermal_runway_confidence: float,
    ) -> float:
        """Calculate systematic confidence metric."""
        # Data freshness score
        if data_freshness_seconds < 60:
            freshness_score = 1.0
        elif data_freshness_seconds < 120:
            freshness_score = 0.8
        elif data_freshness_seconds < 300:
            freshness_score = 0.5
        else:
            freshness_score = 0.2

        # Zone coverage score
        coverage_score = zones_with_live_data / total_zones if total_zones > 0 else 0.0

        # Weighted average
        confidence = freshness_score * 0.3 + coverage_score * 0.4 + thermal_runway_confidence * 0.3

        # Cap at 0.95, floor at 0.0
        return round(max(0.0, min(0.95, confidence)), 2)

    def _identify_limiting_factor(
        self,
        thermal_runway_minutes: int,
        min_headroom_c: float,
        bess_soc_pct: float | None,
        zones_at_boundary: int,
    ) -> str:
        """Identify the primary constraint on curtailment."""
        if thermal_runway_minutes < 30:
            return "chiller_thermal_mass"
        if min_headroom_c < 1.0:
            return "comfort_boundary"
        if bess_soc_pct is not None and bess_soc_pct < 20.0:
            return "bess_low_soc"
        if zones_at_boundary > 0:
            return "zone_temperature_limit"
        if thermal_runway_minutes < 60:
            return "thermal_runway_short"
        return "none"

    def _calculate_ddmp_eligible(
        self,
        curtailable_load_kw: float,
        safe_duration_minutes: int,
        bess_soc_pct: float | None,
    ) -> bool:
        """
        Calculate DDMP Industrial/Commercial Load Management eligibility.

        Based on official Eskom DDMP programme rules:
        https://www.eskom.co.za/distribution/demand-management-programme/

        Requirements:
        - Minimum 0.2 MW (200 kW) load shifting or peak clipping
        - Can aggregate up to 4 sites (same entity) to meet threshold
        - Must sustain reduction during evening peak periods
        - If BESS present: minimum 20% SOC for backup during curtailment

        Incentive: R3 Million per MW of achieved reduction
        Payment: Quarterly over 24-month sustainability period
        Note: Does NOT grant exemption from load shedding

        Returns True if this site meets minimum threshold for standalone
        or portfolio participation.
        """
        if curtailable_load_kw < DDMP_MIN_LOAD_KW:
            return False
        if safe_duration_minutes < DDMP_MIN_DURATION_MINUTES:
            return False
        return not (bess_soc_pct is not None and bess_soc_pct < 20.0)

    async def _save_calculation_to_db(
        self,
        site_id: str,
        curtailable_load_kw: float,
        safe_duration_minutes: int,
        confidence: float,
        ddmp_eligible: bool,
        data_freshness_seconds: int,
        thermal_runway_minutes: int,
        zone_coverage_percent: float,
        bess_soc_pct: float | None,
        limiting_factor: str,
    ) -> None:
        """Save calculation results to Supabase for metrics collection.

        This enables Prometheus/Grafana dashboards to display DDMP metrics
        without recalculating on each scrape.
        """
        try:
            client = get_supabase_client()

            payload = {
                "site_id": site_id,
                "curtailable_load_kw": curtailable_load_kw,
                "safe_duration_minutes": safe_duration_minutes,
                "confidence": confidence,
                "ddmp_eligible": ddmp_eligible,
                "data_freshness_seconds": data_freshness_seconds,
                "thermal_runway_minutes": thermal_runway_minutes,
                "zone_coverage_percent": zone_coverage_percent,
                "bess_soc_pct": bess_soc_pct,
                "limiting_factor": limiting_factor,
                "calculated_at": datetime.now(UTC).isoformat(),
            }

            # Upsert to handle existing entries for same site
            result = client.table("demand_response_calculations").upsert(payload, on_conflict="site_id").execute()

            if hasattr(result, "error") and result.error:
                logger.warning(f"Failed to save DDMP calculation: {result.error}")
            else:
                logger.debug(f"DDMP calculation saved for {site_id}")

        except Exception as e:
            # Don't let DB write failures break the API response
            logger.debug(f"DDMP calculation save failed (non-critical): {e}")


# Global singleton
_demand_response_service: DemandResponseService | None = None


def get_demand_response_service() -> DemandResponseService:
    """Get or create demand response service singleton."""
    global _demand_response_service
    if _demand_response_service is None:
        _demand_response_service = DemandResponseService()
    return _demand_response_service
