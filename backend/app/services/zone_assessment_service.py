"""
Zone Assessment Service
======================
Produces a complete ZoneAssessment for a comfort complaint.

Desk → Zone → All equipment in zone → Equipment health (Supabase)
  + VAV live readings (BMS) + Contextual factors → Assessment + Recommendations

Only generates actionable control recommendations when the site's
control module is active and the onboarding phase permits writes.
"""

import asyncio
import logging
import uuid as uuid_lib
from datetime import datetime
from typing import Any

from app.database.repositories.alert_repository import AlertRepository
from app.database.repositories.desk_repository import DeskRepository
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.hvac_zone_repository import HVACZoneRepository
from app.database.repositories.prediction_repository import PredictionRepository
from app.models.complaint_assessment import (
    EquipmentAlert,
    EquipmentPrediction,
    EquipmentStatus,
    Recommendation,
    VAVLiveReadings,
    ZoneAssessment,
)
from app.models.onboarding_phase import phase_allows
from app.services.lighting_service import get_lighting_service

logger = logging.getLogger(__name__)

# Health score thresholds
_HEALTHY_THRESHOLD = 80
_WARNING_THRESHOLD = 50


class ZoneAssessmentService:
    """
    Assesses a zone for a comfort complaint.

    Produces a ZoneAssessment with:
    - Equipment health (health score, alerts, predictions)
    - VAV live readings (damper, airflow, discharge, reheat)
    - Contextual factors (solar, occupancy, outdoor temp, etc.)
    - Status + root causes
    - Recommendations (gated by control module + phase)
    """

    def __init__(self):
        self._eq_repo = EquipmentRepository()
        self._alert_repo = AlertRepository()
        self._pred_repo = PredictionRepository()
        self._desk_repo = DeskRepository()
        self._hvac_zone_repo = HVACZoneRepository()
        self._lighting = get_lighting_service()

    # -------------------------------------------------------------------------
    # Entry point
    # -------------------------------------------------------------------------

    def assess_zone(
        self,
        zone_id: str,
        complaint_type: str,
        desk_id: str | None = None,
        site_id: str | None = None,
    ) -> ZoneAssessment:
        """
        Produce a full zone assessment for a comfort complaint.

        Args:
            zone_id: The HVAC zone being assessed (e.g. "Zone-L2-A")
            complaint_type: "too_hot", "too_cold", "stuffy", "drafty", "noise"
            desk_id: Optional desk ID for desk-level context
            site_id: Optional site_id for phase gating

        Returns:
            ZoneAssessment with equipment health, contextual factors, and recommendations
        """
        # 1. Load zone data
        zone_data = self._hvac_zone_repo.get_by_zone_id(zone_id)
        if not zone_data:
            return self._empty_assessment(zone_id, desk_id, complaint_type, site_id, error="Zone not found")

        # Get desk data if provided
        desk_data = self._get_desk_data(desk_id) if desk_id else {}

        # 2. Resolve all equipment IDs in this zone
        # site_code sourced from zone_data (zone records carry site_id from bridge-processed BMS data,
        # so the SENTINEL naming convention is already applied by the bridge)
        equipment_ids = self._resolve_zone_equipment(zone_data, site_code=zone_data.get("site_id"))

        # 3. Fetch equipment health + alerts + predictions in parallel
        equipment_statuses = self._fetch_equipment_statuses(equipment_ids)

        # 4. VAV live readings
        vav_id = zone_data.get("vav_id")
        vav_readings = self._fetch_vav_live(vav_id) if vav_id else None

        # 5. Zone readings
        zone_temp = zone_data.get("current_temp")
        zone_setpoint = zone_data.get("setpoint")
        zone_status = zone_data.get("status", "unknown")
        occupancy_data = self._lighting.get_zone_occupancy(zone_id)
        lighting_data = self._lighting.get_zone_lighting(zone_id)

        # 6. Contextual factors
        contextual = self._assess_contextual_factors(
            complaint_type=complaint_type,
            desk_data=desk_data,
            zone_data=zone_data,
            occupancy_pct=(occupancy_data.occupancy_percent if occupancy_data else 0),
            lighting_level=(lighting_data.avg_dim_level if lighting_data else 0),
            vav=vav_readings,
            ahu_id=equipment_ids.get("ahu_id"),
        )

        # 7. Determine assessment status + confidence
        status, root_causes, confidence = self._determine_status(
            complaint_type=complaint_type,
            equipment_statuses=equipment_statuses,
            vav=vav_readings,
            contextual=contextual,
        )

        # 8. Control gating
        effective_site_id = site_id or zone_data.get("site_id") or ""
        phase = self._get_site_phase(effective_site_id)
        hvac_control_active = phase_allows(effective_site_id, "control_writes", "hvac_control")
        lighting_control_active = phase_allows(effective_site_id, "control_writes", "lighting_control")
        control_module_active = hvac_control_active or lighting_control_active

        # 9. Generate recommendations
        recommendations = self._generate_recommendations(
            complaint_type=complaint_type,
            equipment_statuses=equipment_statuses,
            vav=vav_readings,
            contextual=contextual,
            zone_data=zone_data,
            zone_temp=zone_temp,
            zone_setpoint=zone_setpoint,
            phase=phase,
            hvac_control_active=hvac_control_active,
            lighting_control_active=lighting_control_active,
            status=status,
        )

        return ZoneAssessment(
            zone_id=zone_id,
            zone_name=zone_data.get("zone_name", zone_id),
            desk_id=desk_id or "",
            desk_floor=desk_data.get("floor", zone_data.get("floor", "")),
            complaint_type=complaint_type,
            site_id=effective_site_id,
            equipment_statuses=equipment_statuses,
            vav=vav_readings,
            zone_temp=zone_temp or 0,
            zone_setpoint=zone_setpoint or 22,
            zone_status=zone_status,
            occupancy_pct=occupancy_data.occupancy_percent if occupancy_data else 0,
            co2_level=zone_data.get("current_co2"),
            lighting_level=lighting_data.avg_dim_level if lighting_data else 0,
            outdoor_temp=contextual.get("outdoor_temp"),
            near_window=bool(desk_data.get("near_window")),
            near_diffuser=bool(desk_data.get("near_diffuser")),
            near_printer=bool(desk_data.get("near_printer")),
            orientation=desk_data.get("orientation"),
            solar_factor=contextual.get("solar_factor"),
            outdoor_extreme=contextual.get("outdoor_extreme", False),
            low_occupancy=contextual.get("low_occupancy", False),
            high_lighting_load=contextual.get("high_lighting_load", False),
            after_hours=contextual.get("after_hours", False),
            status=status,
            root_causes=root_causes,
            confidence=confidence,
            recommendations=recommendations,
            control_module_active=control_module_active,
            phase=phase,
        )

    # -------------------------------------------------------------------------
    # Step 1: Desk data
    # -------------------------------------------------------------------------

    def _get_desk_data(self, desk_id: str) -> dict[str, Any]:
        """Get desk record using DeskRepository.find_desk()."""
        try:
            desk = self._desk_repo.find_desk(desk_id)
            if desk:
                return desk
        except Exception as e:
            logger.warning(f"Could not load desk {desk_id}: {e}")
        return {}

    # -------------------------------------------------------------------------
    # Step 2: Resolve zone → equipment IDs
    # -------------------------------------------------------------------------

    def _resolve_zone_equipment(
        self, zone_data: dict[str, Any], site_code: str | None = None
    ) -> dict[str, str | None]:
        """Extract equipment IDs from zone record, deriving from naming convention if not stored.

        Equipment naming convention: S{site_prefix}-{TYPE}-{ZONE_CODE}
        e.g. Zone-203 -> S002-FCU-203, S002-VAV-203, S002-AHU-203
        """
        # First try stored values
        fcu_id = zone_data.get("fcu_id")
        vav_id = zone_data.get("vav_id")
        ahu_id = zone_data.get("ahu_id")
        lighting_id = zone_data.get("lighting_id")
        temp_sensor = zone_data.get("temp_sensor")
        co2_sensor = zone_data.get("co2_sensor")
        stored_site_id = zone_data.get("site_id")

        # Derive from naming convention if not stored
        if site_code and not (fcu_id and vav_id and ahu_id):
            # zone_id format: "Zone-NNN" e.g. "Zone-203"
            zone_id = zone_data.get("zone_id", "")
            zone_code = zone_id.replace("Zone-", "") if zone_id.startswith("Zone-") else zone_id

            # site_code format: "site-002" -> extract numeric suffix "002"
            site_num = site_code.replace("site-", "") if site_code.startswith("site-") else site_code
            prefix = f"S{site_num.upper()}"

            if not fcu_id:
                fcu_id = f"{prefix}-FCU-{zone_code}"
            if not vav_id:
                vav_id = f"{prefix}-VAV-{zone_code}"
            if not ahu_id:
                ahu_id = f"{prefix}-AHU-{zone_code}"

        return {
            "fcu_id": fcu_id,
            "vav_id": vav_id,
            "ahu_id": ahu_id,
            "lighting_id": lighting_id,
            "temp_sensor": temp_sensor,
            "co2_sensor": co2_sensor,
            "site_id": stored_site_id,
        }

    # -------------------------------------------------------------------------
    # Step 3: Fetch equipment health + alerts + predictions
    # -------------------------------------------------------------------------

    def _fetch_equipment_statuses(self, equipment_ids: dict[str, str | None]) -> list[EquipmentStatus]:
        """Fetch health, active alerts, and active predictions for each equipment."""
        statuses: list[EquipmentStatus] = []

        for eq_type, eq_code in [
            ("fcu", equipment_ids.get("fcu_id")),
            ("vav", equipment_ids.get("vav_id")),
            ("ahu", equipment_ids.get("ahu_id")),
            ("lighting", equipment_ids.get("lighting_id")),
        ]:
            if not eq_code:
                continue

            # Get equipment record (try UUID format, fall back to code lookup)
            eq = None
            try:
                uuid_lib.UUID(eq_code)
                eq = self._eq_repo.get_by_uuid(eq_code)
            except (ValueError, TypeError):
                pass
            if not eq:
                eq = self._eq_repo.get_by_id(eq_code)
            if not eq:
                # Try zone-based lookup (some zone records store short codes)
                eq = self._eq_repo.get_by_id(eq_code)
                if not eq:
                    # Last resort: search by code pattern
                    eq = self._try_lookup_by_code_pattern(eq_code)

            if not eq:
                statuses.append(
                    EquipmentStatus(
                        equipment_id=eq_code,
                        code=eq_code,
                        name=eq_code,
                        type=eq_type,
                        health_score=100,
                        status="unknown",
                    )
                )
                continue

            eq_uuid = eq.get("id", "")
            eq_code_final = eq.get("code", eq_code)

            # Fetch alerts
            alerts: list[EquipmentAlert] = []
            try:
                active_alerts = self._alert_repo.get_active_by_equipment(eq_uuid)
                for a in active_alerts:
                    alerts.append(
                        EquipmentAlert(
                            alert_id=a.get("id", ""),
                            title=a.get("title", ""),
                            severity=a.get("severity", "warning"),
                            message=a.get("message", ""),
                            created_at=a.get("created_at", ""),
                        )
                    )
            except Exception as e:
                logger.warning(f"Could not fetch alerts for {eq_code_final}: {e}")

            # Fetch predictions
            predictions: list[EquipmentPrediction] = []
            try:
                active_preds = self._pred_repo.get_active_by_equipment(eq_uuid)
                for p in active_preds:
                    predictions.append(
                        EquipmentPrediction(
                            prediction_id=p.get("id", ""),
                            severity=p.get("severity", "warning"),
                            prediction_type=p.get("prediction_type", ""),
                            probability_percent=p.get("probability_percent", 0),
                            timeframe_days=p.get("timeframe_days"),
                            description=p.get("description", ""),
                        )
                    )
            except Exception as e:
                logger.warning(f"Could not fetch predictions for {eq_code_final}: {e}")

            statuses.append(
                EquipmentStatus(
                    equipment_id=eq_uuid,
                    code=eq_code_final,
                    name=eq.get("name", eq_code_final),
                    type=eq_type,
                    health_score=eq.get("health_score", 100) or 100,
                    status=eq.get("status", "normal"),
                    alerts=alerts,
                    predictions=predictions,
                )
            )

        return statuses

    def _try_lookup_by_code_pattern(self, code: str) -> dict[str, Any] | None:
        """Try to find equipment by doing a contains search on code."""
        try:
            all_eq = self._eq_repo.get_all()
            for eq in all_eq:
                if eq.get("code") == code:
                    return eq
        except Exception:
            pass
        return None

    # -------------------------------------------------------------------------
    # Step 4: VAV live readings from BMS
    # -------------------------------------------------------------------------

    def _fetch_vav_live(self, vav_id: str | None) -> VAVLiveReadings | None:
        """Read VAV live data from device_manager."""
        if not vav_id:
            return None

        try:
            loop = asyncio.new_event_loop()
            try:
                device_data = loop.run_until_complete(self._get_vav_device_data(vav_id))
            finally:
                loop.close()
        except Exception as e:
            logger.warning(f"Could not fetch VAV live data for {vav_id}: {e}")
            return VAVLiveReadings(
                vav_id=vav_id,
                damper_position=None,
                airflow_actual=None,
                airflow_setpoint=None,
                discharge_temp=None,
                reheat_valve=None,
            )

        if not device_data:
            return VAVLiveReadings(
                vav_id=vav_id,
                damper_position=None,
                airflow_actual=None,
                airflow_setpoint=None,
                discharge_temp=None,
                reheat_valve=None,
            )

        dp = device_data.get("damper_position")
        af = device_data.get("airflow_actual")
        sp = device_data.get("airflow_setpoint")
        dt = device_data.get("discharge_temp")
        rv = device_data.get("reheat_valve")

        # Fault detection
        has_stuck = dp is not None and dp > 90
        has_mismatch = af is not None and sp is not None and abs(af - sp) > 100
        has_conflict = rv is not None and rv > 30  # reheat while zone is too hot

        return VAVLiveReadings(
            vav_id=vav_id,
            damper_position=dp,
            airflow_actual=af,
            airflow_setpoint=sp,
            discharge_temp=dt,
            reheat_valve=rv,
            has_stuck_damper=has_stuck,
            has_airflow_mismatch=has_mismatch,
            has_reheat_conflict=has_conflict,
        )

    async def _get_vav_device_data(self, vav_id: str) -> dict[str, Any]:
        """Async fetch from device_manager."""
        from app.services.device_abstraction import device_manager

        dm = device_manager
        if dm is None:
            return {}

        device = await dm.get_device(vav_id)
        if not device:
            return {}

        points = device.points or {}

        def _val(key: str):
            p = points.get(key)
            if p is None:
                return None
            if hasattr(p, "value"):
                return p.value
            if isinstance(p, dict):
                return p.get("value")
            return None

        return {
            "damper_position": _val("damper_position"),
            "airflow_actual": _val("airflow_actual"),
            "airflow_setpoint": _val("airflow_setpoint"),
            "discharge_temp": _val("discharge_air_temp"),
            "reheat_valve": _val("heating_valve"),
        }

    # -------------------------------------------------------------------------
    # Step 5: Contextual factors
    # -------------------------------------------------------------------------

    def _assess_contextual_factors(
        self,
        complaint_type: str,
        desk_data: dict[str, Any],
        zone_data: dict[str, Any],
        occupancy_pct: float,
        lighting_level: float,
        vav: VAVLiveReadings | None,
        ahu_id: str | None,
    ) -> dict[str, Any]:
        """
        Assess contributing contextual factors (not faults — contributing conditions).

        Returns dict with:
            solar_factor: str | None
            outdoor_temp: float | None
            outdoor_extreme: bool
            low_occupancy: bool
            high_lighting_load: bool
            after_hours: bool
        """
        now = datetime.now()
        hour = now.hour
        result: dict[str, Any] = {}

        # Solar heat gain (near window + time of day + orientation)
        if desk_data.get("near_window"):
            orientation = (desk_data.get("orientation") or "").upper()
            # Morning sun (E/NE/SE) 6-11am
            if orientation in ("E", "NE", "SE") and 6 <= hour <= 11:
                result["solar_factor"] = "morning_sun"
            # Afternoon sun (W/NW/SW) 12-6pm
            elif orientation in ("W", "NW", "SW") and 12 <= hour <= 18:
                result["solar_factor"] = "afternoon_sun"
            # North-facing gets sun most of day (Southern Hemisphere)
            elif orientation == "N" and 9 <= hour <= 16:
                result["solar_factor"] = "north_facing"
            elif not orientation and 12 <= hour <= 18:
                result["solar_factor"] = "afternoon_sun"

        # Outdoor temperature from AHU telemetry
        outdoor_temp = self._fetch_outdoor_temp(ahu_id)
        if outdoor_temp is not None:
            result["outdoor_temp"] = outdoor_temp
            result["outdoor_extreme"] = outdoor_temp > 35 or outdoor_temp < 10

        # Occupancy
        result["occupancy_pct"] = occupancy_pct
        result["low_occupancy"] = occupancy_pct < 20

        # Lighting heat load
        result["high_lighting_load"] = lighting_level > 70

        # Building hours (Mon-Fri 8am-6pm = occupied)
        result["after_hours"] = now.weekday() >= 5 or hour < 8 or hour > 18

        return result

    def _fetch_outdoor_temp(self, ahu_id: str | None) -> float | None:
        """Read outdoor air temp from AHU telemetry if available."""
        if not ahu_id:
            return None
        try:
            loop = asyncio.new_event_loop()
            try:
                temp = loop.run_until_complete(self._read_device_point(ahu_id, "outdoor_air_temp"))
            finally:
                loop.close()
            return temp
        except Exception:
            # Try alternate point names
            for point in ("oa_temp", "outside_air_temp", "ambient_temp"):
                try:
                    loop = asyncio.new_event_loop()
                    try:
                        temp = loop.run_until_complete(self._read_device_point(ahu_id, point))
                    finally:
                        loop.close()
                    if temp is not None:
                        return temp
                except Exception:
                    pass
            return None

    async def _read_device_point(self, equipment_id: str, point_name: str) -> float | None:
        """Read a single point from device_manager."""
        from app.services.device_abstraction import device_manager

        dm = device_manager
        if dm is None:
            return None
        try:
            result = await dm.read_device_value(equipment_id, point_name)
            return result.value if result else None
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Step 6: Determine status + root causes + confidence
    # -------------------------------------------------------------------------

    def _determine_status(
        self,
        complaint_type: str,
        equipment_statuses: list[EquipmentStatus],
        vav: VAVLiveReadings | None,
        contextual: dict[str, Any],
    ) -> tuple[str, list[str], str]:
        """
        Determine assessment status and root causes.

        Returns (status, root_causes, confidence)
        """
        has_equipment_issues = any(eq.has_issues for eq in equipment_statuses)
        has_contextual = any(
            [
                contextual.get("solar_factor"),
                contextual.get("outdoor_extreme"),
                contextual.get("low_occupancy"),
                contextual.get("high_lighting_load"),
                contextual.get("after_hours"),
            ]
        )
        root_causes: list[str] = []

        # Critical equipment faults always dominate
        if any(eq.has_critical_issues for eq in equipment_statuses):
            status = "equipment_fault"
            confidence = "high"
            for eq in equipment_statuses:
                if eq.has_critical_issues:
                    if eq.alerts:
                        root_causes.append(f"{eq.name}: {eq.alerts[0].title}")
                    elif eq.predictions:
                        root_causes.append(
                            f"{eq.name}: {eq.predictions[0].prediction_type} "
                            f"({eq.predictions[0].probability_percent}% probability)"
                        )
                    else:
                        root_causes.append(f"{eq.name}: {eq.status} — requires attention")
            return status, root_causes, confidence

        # VAV-specific faults
        if vav and complaint_type in ("too_hot", "too_cold", "drafty"):
            if vav.has_stuck_damper:
                return (
                    "equipment_fault",
                    [f"VAV damper stuck open at {vav.damper_position:.0f}% — insufficient airflow control"],
                    "high",
                )
            if vav.has_reheat_conflict:
                return (
                    "equipment_fault",
                    [f"Reheat valve active at {vav.reheat_valve:.0f}% while zone reports too hot — control conflict"],
                    "high",
                )
            if vav.has_airflow_mismatch:
                return (
                    "equipment_fault",
                    [f"VAV airflow mismatch: {vav.airflow_actual:.0f} L/s vs {vav.airflow_setpoint:.0f} L/s setpoint"],
                    "medium",
                )

        # Equipment issues (non-critical)
        if has_equipment_issues:
            status = "equipment_fault"
            confidence = "high"
            for eq in equipment_statuses:
                if eq.has_issues and not eq.has_critical_issues:
                    if eq.alerts:
                        root_causes.append(f"{eq.name}: {eq.alerts[0].title}")
                    elif eq.predictions:
                        root_causes.append(f"{eq.name}: predicted {eq.predictions[0].prediction_type}")
                    elif eq.health_score < _WARNING_THRESHOLD:
                        root_causes.append(f"{eq.name}: low health ({eq.health_score}%)")
            return status, root_causes, confidence

        # Contextual factors only
        if has_contextual:
            status = "contextual_factor"
            confidence = "medium"
            sf = contextual.get("solar_factor")
            if sf == "morning_sun":
                root_causes.append("Morning sun (east-facing windows) heating your area")
            elif sf == "afternoon_sun":
                root_causes.append("Afternoon sun (west-facing windows) heating your area")
            elif sf == "north_facing":
                root_causes.append("Direct sunlight (north-facing windows) — HVAC unable to fully offset")
            if contextual.get("outdoor_extreme"):
                t = contextual.get("outdoor_temp")
                if t and t > 35:
                    root_causes.append(f"Outdoor temperature {t:.0f}°C — HVAC under extreme load")
                elif t and t < 10:
                    root_causes.append(f"Outdoor temperature {t:.0f}°C — HVAC struggling to maintain warmth")
            if contextual.get("low_occupancy"):
                root_causes.append(
                    f"Low zone occupancy ({contextual.get('occupancy_pct', 0):.0f}%) — reduced internal heat load"
                )
            if contextual.get("high_lighting_load"):
                root_causes.append(f"Lighting at {contextual.get('lighting_level', 0):.0f}% — contributes to heat load")
            if contextual.get("after_hours"):
                root_causes.append("Outside building hours — reduced HVAC capacity")
            return status, root_causes, confidence

        # No issues found
        return "no_issues", [], "high"

    # -------------------------------------------------------------------------
    # Step 7: Generate recommendations
    # -------------------------------------------------------------------------

    def _generate_recommendations(
        self,
        complaint_type: str,
        equipment_statuses: list[EquipmentStatus],
        vav: VAVLiveReadings | None,
        contextual: dict[str, Any],
        zone_data: dict[str, Any],
        zone_temp: float | None,
        zone_setpoint: float | None,
        phase: str,
        hvac_control_active: bool,
        lighting_control_active: bool,
        status: str,
    ) -> list[Recommendation]:
        """
        Generate recommendations gated by control module + phase.

        supervised + control active: can_supervised_adjust=True, can_auto_adjust=False
        auto + control active:       can_supervised_adjust=True, can_auto_adjust=True
        shadow/advisory:              both False (recommendations only)
        """
        recommendations: list[Recommendation] = []
        can_supervised = phase in ("supervised", "auto") and (hvac_control_active or lighting_control_active)
        can_auto = phase == "auto" and (hvac_control_active or lighting_control_active)

        # Only generate control recommendations for non-fault cases
        # For equipment faults: dispatch technician instead
        if status == "equipment_fault":
            # Recommend technician dispatch for faults
            faulty = [eq for eq in equipment_statuses if eq.has_issues]
            for eq in faulty[:2]:
                recommendations.append(
                    Recommendation(
                        action=f"Dispatch technician to inspect {eq.name}",
                        equipment_code=eq.code,
                        parameter="dispatch",
                        current_value=None,
                        suggested_value=None,
                        reason=f"{eq.name} has {eq.status} status — requires on-site inspection",
                        can_supervised_adjust=can_supervised,
                        can_auto_adjust=False,
                    )
                )
            return recommendations

        # Solar heat gain → dim lights + boost HVAC
        sf = contextual.get("solar_factor")
        if sf and complaint_type == "too_hot":
            # Lighting dim recommendation
            if lighting_control_active:
                current_lighting = contextual.get("lighting_level", 50)
                if current_lighting > 30:
                    recommendations.append(
                        Recommendation(
                            action="Dim zone lighting to 30% to reduce heat load",
                            equipment_code=equipment_statuses[0].code if equipment_statuses else "",
                            parameter="brightness",
                            current_value=current_lighting,
                            suggested_value=30,
                            reason="Reducing lighting reduces heat output from luminaires",
                            can_supervised_adjust=can_supervised,
                            can_auto_adjust=can_auto,
                        )
                    )
            # HVAC boost
            if hvac_control_active and zone_setpoint:
                new_setpoint = max(zone_setpoint - 2, 20)  # Don't go below 20°C
                recommendations.append(
                    Recommendation(
                        action=f"Lower zone setpoint to {new_setpoint:.0f}°C (from {zone_setpoint:.0f}°C) for 2 hours",
                        equipment_code="",
                        parameter="temperature_setpoint",
                        current_value=zone_setpoint,
                        suggested_value=new_setpoint,
                        reason="Boost cooling to offset solar heat gain",
                        can_supervised_adjust=can_supervised,
                        can_auto_adjust=can_auto,
                    )
                )

        # Outdoor extreme heat → reduce setpoint
        if contextual.get("outdoor_extreme") and complaint_type == "too_hot" and hvac_control_active:
            t = contextual.get("outdoor_temp", 0)
            if t > 35 and zone_setpoint:
                new_setpoint = max(zone_setpoint - 1, 21)
                if not any(r.parameter == "temperature_setpoint" for r in recommendations):
                    recommendations.append(
                        Recommendation(
                            action=f"Lower setpoint to {new_setpoint:.0f}°C due to extreme outdoor heat ({t:.0f}°C)",
                            equipment_code="",
                            parameter="temperature_setpoint",
                            current_value=zone_setpoint,
                            suggested_value=new_setpoint,
                            reason=f"Outdoor {t:.0f}°C is reducing HVAC effectiveness",
                            can_supervised_adjust=can_supervised,
                            can_auto_adjust=can_auto,
                        )
                    )

        # VAV airflow boost
        if vav and complaint_type in ("too_hot", "too_cold") and hvac_control_active:
            dp = vav.damper_position
            if dp is not None and dp < 80:
                recommendations.append(
                    Recommendation(
                        action=f"Increase VAV airflow to maximum (damper at {dp:.0f}%)",
                        equipment_code=vav.vav_id,
                        parameter="airflow_setpoint",
                        current_value=dp,
                        suggested_value=100,
                        reason="Boost airflow to improve temperature uniformity",
                        can_supervised_adjust=can_supervised,
                        can_auto_adjust=can_auto,
                    )
                )

        # Low occupancy
        if contextual.get("low_occupancy") and complaint_type == "too_hot":
            recommendations.append(
                Recommendation(
                    action="Verify VAV box position appropriate for low occupancy",
                    equipment_code=vav.vav_id if vav else "",
                    parameter="check",
                    current_value=None,
                    suggested_value=None,
                    reason="Low occupancy zone may need reduced airflow",
                    can_supervised_adjust=can_supervised,
                    can_auto_adjust=False,
                )
            )

        # Generic HVAC
        if status == "contextual_factor" and not recommendations:
            recommendations.append(
                Recommendation(
                    action="Monitor zone for 30 minutes — conditions may be transient",
                    equipment_code="",
                    parameter="monitor",
                    current_value=None,
                    suggested_value=None,
                    reason="All systems within parameters — issue may be temporary",
                    can_supervised_adjust=False,
                    can_auto_adjust=False,
                )
            )

        return recommendations

    # -------------------------------------------------------------------------
    # Step 8: Site phase
    # -------------------------------------------------------------------------

    def _get_site_phase(self, site_id: str) -> str:
        """Get site's onboarding phase."""
        if not site_id:
            return "shadow"
        try:
            from app.database.repositories.site_repository import SiteRepository

            repo = SiteRepository()
            site = repo.get_by_id(site_id)
            if site:
                return site.get("onboarding_phase", "shadow")
        except Exception as e:
            logger.warning(f"Could not get site phase for {site_id}: {e}")
        return "shadow"

    # -------------------------------------------------------------------------
    # Fallback
    # -------------------------------------------------------------------------

    def _empty_assessment(
        self,
        zone_id: str,
        desk_id: str | None,
        complaint_type: str,
        site_id: str | None,
        error: str = "",
    ) -> ZoneAssessment:
        """Return an empty assessment when zone lookup fails."""
        return ZoneAssessment(
            zone_id=zone_id,
            zone_name=zone_id,
            desk_id=desk_id or "",
            desk_floor="",
            complaint_type=complaint_type,
            site_id=site_id or "",
            equipment_statuses=[],
            vav=None,
            zone_temp=0,
            zone_setpoint=22,
            zone_status="unknown",
            occupancy_pct=0,
            co2_level=None,
            lighting_level=0,
            outdoor_temp=None,
            near_window=False,
            near_diffuser=False,
            near_printer=False,
            orientation=None,
            solar_factor=None,
            outdoor_extreme=False,
            low_occupancy=False,
            high_lighting_load=False,
            after_hours=False,
            status="no_issues",
            root_causes=[error] if error else [],
            confidence="low",
            recommendations=[],
            control_module_active=False,
            phase="shadow",
        )


# Singleton
_service: ZoneAssessmentService | None = None


def get_zone_assessment_service() -> ZoneAssessmentService:
    global _service
    if _service is None:
        _service = ZoneAssessmentService()
    return _service
