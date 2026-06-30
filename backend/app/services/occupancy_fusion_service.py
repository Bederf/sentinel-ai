"""Multi-signal occupancy fusion service.

Fuses all available occupancy signals into a single verdict with confidence
and conflict detection. Every consumer of occupancy data uses this service
instead of reading from whatever single source was convenient.

Available signals (per-site availability varies):
- SIMBIOT bridge aggregate (total_occupancy, occupied_zones, zone_count)
- Lighting/PIR motion sensors (occupancy_percent per zone; protocol-neutral)
- CO2 ppm elevation above 420ppm baseline (presence proxy)
- Security badge entry/exit balance
- AHU return-temp vs outdoor-temp differential (human heat load)
- Potable water consumption delta (flow increase → people present)

Consumption rule: on signal conflict, gates err toward "occupied". False
suppression (shutting off HVAC with people present) is worse than false
non-suppression (running a bit longer than ideal).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger("sentinel.occupancy_fusion")

# ── Fresness thresholds per signal (minutes) ──────────────────────────────
FRESHNESS_THRESHOLDS: dict[str, float] = {
    "simbiot_aggregate": 15.0,
    "lighting_pir": 5.0,
    "co2_elevation": 30.0,
    "security_badges": 15.0,
    "ahu_heat_load": 30.0,
    "water_consumption": 30.0,
}

# ── Water consumption thresholds ──────────────────────────────────────────
WATER_SENSOR_TYPES = ("total_consumption_m3", "flow_rate_lpm")
WATER_METER_EQUIPMENT_SUFFIX = "WATER-MTR"
WATER_MIN_DELTA_M3_PER_HOUR = 0.3  # below this = no meaningful consumption
WATER_MAX_DELTA_M3_PER_HOUR = 200.0  # above this = counter reset artifact, ignore

# ── CO2 baseline and elevation thresholds ─────────────────────────────────
CO2_BASELINE_PPM = 420.0
CO2_ELEVATED_PPM = 500.0  # above this = potentially occupied (but check trend)
CO2_STRONGLY_ELEVATED_PPM = 800.0  # above this = definitely occupied (trend irrelevant)
CO2_TREND_WINDOW_MINUTES = 30.0  # look back for rate-of-change check
CO2_RISING_THRESHOLD_PPM = 10.0  # minimum increase over window to count as rising

# ── AHU heat load thresholds ──────────────────────────────────────────────
AHU_RETURN_OAT_MIN_DELTA = 2.0  # return > outdoor by this much suggests people
AHU_RETURN_OAT_STRONG_DELTA = 5.0

# ── Default fusion weights (redistributed when signals unavailable) ───────
_BASE_WEIGHTS: dict[str, float] = {
    "simbiot_aggregate": 0.30,
    "lighting_pir": 0.27,
    "co2_elevation": 0.15,
    "security_badges": 0.10,
    "ahu_heat_load": 0.10,
    "water_consumption": 0.08,
}

SIGNAL_CONFIDENCE_MAX = 0.95
SIGNAL_CONFIDENCE_STALE = 0.30
FUSED_CONFIDENCE_HIGH = 0.80
CONFLICT_OCCUPANCY_DELTA = 30.0  # percentage points → conflict
GATE_UNCERTAIN_THRESHOLD = 0.70  # below this + conflict → occupied (fail-safe)

# ── Dataclasses ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OccupancySignalVerdict:
    source: str
    normalized_pct: float
    confidence: float
    freshness_minutes: float
    is_available: bool
    raw_value: Any = None


@dataclass(frozen=True)
class OccupancyConflict:
    signals: tuple[str, str]
    delta_pct: float
    description: str


@dataclass(frozen=True)
class FusedOccupancyVerdict:
    occupancy_percent: float
    occupancy_count: int
    confidence: float
    is_occupied: bool
    signals: dict[str, OccupancySignalVerdict]
    conflicts: tuple[OccupancyConflict, ...]
    gate_override: str  # "none" | "conflict_uncertain" | "presence_signal"

    @property
    def is_uncertain(self) -> bool:
        return self.gate_override != "none"

    @property
    def may_suppress(self) -> bool:
        return not self.is_uncertain and self.confidence >= GATE_UNCERTAIN_THRESHOLD and not self.is_occupied

    def to_prompt_detail(self) -> str:
        """Format for inclusion in the Claude prompt."""
        parts: list[str] = []
        # Fused verdict
        if self.is_uncertain:
            parts.append(
                f"⚠ FUSED: uncertain (conflict) — treating as occupied. {self.occupancy_percent:.0f}% estimated"
            )
        elif self.is_occupied:
            parts.append(f"FUSED: occupied — {self.occupancy_percent:.0f}% ({self.occupancy_count} people)")
        else:
            parts.append(f"FUSED: unoccupied — {self.occupancy_percent:.0f}% ({self.occupancy_count} people)")
        # Per-signal breakdown
        for src in (
            "simbiot_aggregate",
            "lighting_pir",
            "co2_elevation",
            "security_badges",
            "ahu_heat_load",
            "water_consumption",
        ):
            sv = self.signals.get(src)
            if sv and sv.is_available:
                parts.append(f"  {src}: {sv.normalized_pct:.0f}% (confidence {sv.confidence:.2f})")
        # Conflicts
        if self.conflicts:
            parts.append("  SIGNAL CONFLICTS:")
            for c in self.conflicts:
                parts.append(f"    {c.description}")
        # Gate instruction
        parts.append("  Gate rule: when signals conflict, do NOT suppress — treat as occupied")
        return "\n".join(parts)

    def to_gate_context(self) -> dict[str, Any]:
        """Compact dict for quality gate and scheduler consumers."""
        return {
            "occupancy_percent": self.occupancy_percent,
            "occupancy_count": self.occupancy_count,
            "confidence": self.confidence,
            "is_occupied": self.is_occupied,
            "is_uncertain": self.is_uncertain,
            "may_suppress": self.may_suppress,
            "num_signals": sum(1 for s in self.signals.values() if s.is_available),
            "num_conflicts": len(self.conflicts),
            "gate_override": self.gate_override,
        }


# ── Service ───────────────────────────────────────────────────────────────


class OccupancyFusionService:
    def __init__(self, supabase_client: Any | None = None):
        self._sb = supabase_client or get_supabase_client()
        self._last_site_cache: dict[str, tuple[FusedOccupancyVerdict, datetime]] = {}

    async def get_fused_occupancy(
        self,
        site_id: str,
        zone_id: str | None = None,
        *,
        force_refresh: bool = False,
    ) -> FusedOccupancyVerdict:
        site_id = self._canonical_site_id(site_id)
        cache_key = f"{site_id}:{zone_id or '*'}"
        if not force_refresh and cache_key in self._last_site_cache:
            verdict, cached_at = self._last_site_cache[cache_key]
            if (datetime.now(UTC) - cached_at).total_seconds() < 60:
                return verdict

        signals: dict[str, OccupancySignalVerdict] = {}

        simbiot = await self._get_simbiot_aggregate(site_id)
        if simbiot:
            signals["simbiot_aggregate"] = simbiot

        lighting = await self._get_lighting_pir_occupancy(site_id, zone_id)
        if lighting:
            signals["lighting_pir"] = lighting

        co2 = await self._get_co2_elevation(site_id, zone_id)
        if co2:
            signals["co2_elevation"] = co2

        security = await self._get_security_occupancy(site_id, zone_id)
        if security:
            signals["security_badges"] = security

        ahu = await self._get_ahu_heat_load(site_id)
        if ahu:
            signals["ahu_heat_load"] = ahu

        water = await self._get_water_consumption(site_id)
        if water:
            signals["water_consumption"] = water

        verdict = self._fuse(signals)
        self._last_site_cache[cache_key] = (verdict, datetime.now(UTC))
        return verdict

    # ── Signal collectors ─────────────────────────────────────────────

    async def _get_simbiot_aggregate(self, site_id: str) -> OccupancySignalVerdict | None:
        try:
            resp = (
                self._sb.table("equipment_sensor_readings")
                .select("sensor_type,value,recorded_at")
                .eq("site_id", site_id)
                .eq("equipment_id", self._site_agg_equipment(site_id))
                .in_("sensor_type", ["total_occupancy", "occupied_zones", "zone_count"])
                .order("recorded_at", desc=True)
                .limit(10)
                .execute()
            )
        except Exception as e:
            logger.warning("SIMBIOT aggregate query failed for %s: %s", site_id, e)
            return None

        rows = resp.data or []
        if not rows:
            return None

        latest: dict[str, Any] = {}
        for row in rows:
            st = row.get("sensor_type")
            if st and st not in latest and row.get("value") is not None:
                latest[st] = row

        total_occ = latest.get("total_occupancy")
        occupied_zones = latest.get("occupied_zones")
        zone_count = latest.get("zone_count")

        timestamp_source = occupied_zones or total_occ
        if timestamp_source:
            recorded_at_str = timestamp_source.get("recorded_at", "")
            freshness = self._freshness_minutes(recorded_at_str)
            threshold = FRESHNESS_THRESHOLDS["simbiot_aggregate"]
            confidence = self._freshness_confidence(freshness, threshold)

            occ_count = int(float(total_occ.get("value"))) if total_occ else 0
            occupied_zone_count = None
            total_zone_count = None
            if occupied_zones and zone_count:
                occupied_zone_count = int(float(occupied_zones.get("value")))
                total_zone_count = int(float(zone_count.get("value")))
                occ_pct = (occupied_zone_count / total_zone_count * 100) if total_zone_count > 0 else 0.0
            else:
                occ_pct = 0.0

            return OccupancySignalVerdict(
                source="simbiot_aggregate",
                normalized_pct=occ_pct,
                confidence=min(confidence, SIGNAL_CONFIDENCE_MAX),
                freshness_minutes=freshness,
                is_available=True,
                raw_value={
                    "total_occupancy": occ_count,
                    "occupied_zones": occupied_zone_count,
                    "zone_count": total_zone_count,
                },
            )
        return None

    async def _get_lighting_pir_occupancy(self, site_id: str, zone_id: str | None) -> OccupancySignalVerdict | None:
        try:
            from app.services.lighting_service import get_lighting_service

            svc = get_lighting_service()
            live_data = await svc.get_live_lighting_data(site_id)
            zones = live_data.get("zones") or []
            if zone_id:
                zone = next((z for z in zones if z.get("zone_id") == zone_id), None)
                if not zone:
                    return None
                total_sensors = int(zone.get("total_sensors") or 0)
                occupied_sensors = int(zone.get("occupied_sensors") or 0)
                occ_pct = float(zone.get("occupancy_percent") or 0)
                return OccupancySignalVerdict(
                    source="lighting_pir",
                    normalized_pct=occ_pct,
                    confidence=min(0.55 + (occ_pct / 100.0 * 0.35), SIGNAL_CONFIDENCE_MAX)
                    if total_sensors > 0
                    else 0.0,
                    freshness_minutes=self._freshness_minutes(
                        str(zone.get("last_updated") or live_data.get("timestamp") or "")
                    ),
                    is_available=True,
                    raw_value={
                        "zone_id": zone_id,
                        "occupied_sensors": occupied_sensors,
                        "total_sensors": total_sensors,
                    },
                )

            occupied_sensors = 0
            total_sensors = 0
            freshest = ""
            for zone in zones:
                total_sensors += int(zone.get("total_sensors") or 0)
                occupied_sensors += int(zone.get("occupied_sensors") or 0)
                last_updated = str(zone.get("last_updated") or "")
                if last_updated > freshest:
                    freshest = last_updated
            if total_sensors == 0:
                return None
            occ_pct = occupied_sensors / total_sensors * 100
            return OccupancySignalVerdict(
                source="lighting_pir",
                normalized_pct=occ_pct,
                confidence=min(0.55 + (occ_pct / 100.0 * 0.35), SIGNAL_CONFIDENCE_MAX),
                freshness_minutes=self._freshness_minutes(freshest or str(live_data.get("timestamp") or "")),
                is_available=True,
                raw_value={"occupied_sensors": occupied_sensors, "total_sensors": total_sensors},
            )
        except Exception as e:
            logger.debug("Lighting PIR occupancy unavailable for %s: %s", site_id, e)
            return None

    async def _get_co2_elevation(self, site_id: str, zone_id: str | None = None) -> OccupancySignalVerdict | None:
        if zone_id:
            direct = await self._get_direct_zone_co2_elevation(site_id, zone_id)
            if direct:
                return direct
        return await self._get_site_aggregate_co2_elevation(site_id)

    async def _get_direct_zone_co2_elevation(self, site_id: str, zone_id: str) -> OccupancySignalVerdict | None:
        try:
            equipment_id = self._zone_co2_equipment_id(site_id, zone_id)
            resp = (
                self._sb.table("equipment_sensor_readings")
                .select("equipment_id,sensor_type,value,recorded_at")
                .eq("site_id", site_id)
                .eq("sensor_type", "co2_ppm")
                .eq("equipment_id", equipment_id)
                .order("recorded_at", desc=True)
                .limit(2)
                .execute()
            )
        except Exception as e:
            logger.debug("Direct zone CO2 query failed for %s/%s: %s", site_id, zone_id, e)
            return None

        readings = resp.data or []
        if not readings:
            return None
        return self._co2_signal_from_device_readings({equipment_id: readings}, source_scope="direct_zone_sensor")

    async def _get_site_aggregate_co2_elevation(self, site_id: str) -> OccupancySignalVerdict | None:
        try:
            prefix = self._site_eq_prefix(site_id)
            resp = (
                self._sb.table("equipment_sensor_readings")
                .select("equipment_id,sensor_type,value,recorded_at")
                .eq("site_id", site_id)
                .eq("sensor_type", "co2_ppm")
                .gte("equipment_id", f"{prefix}-FCU-")
                .lt("equipment_id", f"{prefix}-FCX-")
                .order("recorded_at", desc=True)
                .limit(100)
                .execute()
            )
        except Exception as e:
            logger.debug("CO2 query failed for %s: %s", site_id, e)
            return None

        readings = resp.data or []
        if not readings:
            return None

        # Build per-device time series (latest 2 readings per FCU)
        per_device: dict[str, list[dict]] = {}
        for r in readings:
            eid = r.get("equipment_id", "")
            if r.get("value") is None:
                continue
            per_device.setdefault(eid, [])
            if len(per_device[eid]) < 2:
                per_device[eid].append(r)

        if not per_device:
            return None
        return self._co2_signal_from_device_readings(per_device, source_scope="site_fcu_aggregate")

    def _co2_signal_from_device_readings(
        self,
        per_device: dict[str, list[dict[str, Any]]],
        *,
        source_scope: str,
    ) -> OccupancySignalVerdict | None:
        most_recent_ts = ""

        elevated_count = 0
        rising_count = 0
        total_count = len(per_device)

        for eid, readings_list in per_device.items():
            latest = readings_list[0]
            current_val = float(latest["value"])
            if latest.get("recorded_at", "") > most_recent_ts:
                most_recent_ts = latest.get("recorded_at", "")

            if current_val >= CO2_ELEVATED_PPM:
                elevated_count += 1

            if len(readings_list) >= 2:
                prev = readings_list[1]
                prev_val = float(prev["value"])
                delta = current_val - prev_val
                time_diff = self._freshness_delta(prev.get("recorded_at", ""), latest.get("recorded_at", ""))
                if delta >= CO2_RISING_THRESHOLD_PPM and 0 < time_diff <= CO2_TREND_WINDOW_MINUTES:
                    rising_count += 1

        occ_pct = elevated_count / total_count * 100

        freshness = self._freshness_minutes(most_recent_ts)
        threshold = FRESHNESS_THRESHOLDS["co2_elevation"]
        base_confidence = self._freshness_confidence(freshness, threshold)

        avg_co2 = sum(float(readings_list[0]["value"]) for readings_list in per_device.values()) / total_count
        rising_ratio = rising_count / total_count if total_count else 0

        # CO2 confidence tiers (trend-sensitive at all levels)
        #   <500ppm:   background, minimal confidence
        #   500-600:   stale decay unless rising (people leaving/left)
        #   600-800:   occupied stable or rising (likely people present)
        #   800+:      rising = definitely occupied; flat = could be stale recirculation
        #              (a chiller running all day in a closed building recirculates
        #               Friday's CO2 to 1000+ ppm with zero people present)
        if avg_co2 >= CO2_STRONGLY_ELEVATED_PPM:
            if rising_ratio > 0.3:
                co2_confidence = 0.9  # actively rising at high level = definitely occupied
            else:
                co2_confidence = 0.60  # flat/stable at 800+ = high but not conclusive
        elif avg_co2 >= 600.0:
            if rising_ratio > 0.3:
                co2_confidence = 0.85  # rising above 600 = strong occupancy signal
            else:
                co2_confidence = 0.55  # stable at 600+ = occupied, not decaying
        elif avg_co2 >= CO2_ELEVATED_PPM:
            if rising_ratio > 0.3:
                co2_confidence = 0.75  # rising = people entering
            else:
                co2_confidence = 0.25  # stable/declining at 500-600 = stale air
        else:
            co2_confidence = 0.1

        confidence = min(base_confidence * co2_confidence, SIGNAL_CONFIDENCE_MAX)

        return OccupancySignalVerdict(
            source="co2_elevation",
            normalized_pct=occ_pct,
            confidence=confidence,
            freshness_minutes=freshness,
            is_available=True,
            raw_value={
                "elevated_count": elevated_count,
                "total_count": total_count,
                "avg_co2": avg_co2,
                "rising_count": rising_count,
                "rising_ratio": rising_ratio,
                "source_scope": source_scope,
            },
        )

    async def _get_security_occupancy(self, site_id: str, zone_id: str | None) -> OccupancySignalVerdict | None:
        try:
            from app.services.security_occupancy_service import get_security_occupancy_service

            svc = get_security_occupancy_service()
            if zone_id:
                occ = svc.get_zone_occupancy(zone_id)
                if not occ:
                    return None
                return OccupancySignalVerdict(
                    source="security_badges",
                    normalized_pct=min(float(occ.occupancy_count) / 20.0 * 100, 100.0),
                    confidence=0.7 if occ.occupancy_count > 0 else 0.5,
                    freshness_minutes=0.5,
                    is_available=True,
                    raw_value={"zone_id": zone_id, "occupancy_count": occ.occupancy_count},
                )
            building_occ = svc.get_building_occupancy(site_id=site_id)
            if not building_occ or building_occ.get("data_available") is False:
                return None
            total_people = building_occ.get("total_occupancy", 0) if isinstance(building_occ, dict) else 0
            occ_pct = min(total_people / 100.0 * 100, 100.0)  # assume 100-person capacity baseline
            return OccupancySignalVerdict(
                source="security_badges",
                normalized_pct=occ_pct,
                # CCURE zero is a definitive count — badge-in without badge-out (tailgating)
                # is possible but rare. 0.75 confidence for empty vs 0.7 for occupied reflects
                # that ACS reports empty more reliably than it tracks every person present.
                confidence=0.7 if total_people > 0 else 0.75,
                freshness_minutes=0.5,
                is_available=True,
                raw_value={"total_occupancy": total_people},
            )
        except Exception as e:
            logger.debug("Security occupancy unavailable for %s: %s", site_id, e)
            return None

    async def _get_ahu_heat_load(self, site_id: str) -> OccupancySignalVerdict | None:
        try:
            prefix = self._site_eq_prefix(site_id)
            resp = (
                self._sb.table("equipment_sensor_readings")
                .select("equipment_id,sensor_type,value,recorded_at")
                .eq("site_id", site_id)
                .in_(
                    "sensor_type", ["return_air_temp", "supply_air_temp", "outdoor_temp", "outside_air_temp", "oa_temp"]
                )
                .gte("equipment_id", f"{prefix}-AHU-")
                .lt("equipment_id", f"{prefix}-AHZ-")
                .order("recorded_at", desc=True)
                .limit(30)
                .execute()
            )
        except Exception as e:
            logger.debug("AHU heat load query failed for %s: %s", site_id, e)
            return None

        readings = resp.data or []
        if not readings:
            return None

        latest: dict[str, float] = {}
        most_recent_ts = ""
        for r in readings:
            eid = r.get("equipment_id", "")
            st = r.get("sensor_type", "")
            key = f"{eid}:{st}"
            if key not in latest and r.get("value") is not None:
                latest[key] = float(r["value"])
                if not most_recent_ts or r.get("recorded_at", "") > most_recent_ts:
                    most_recent_ts = r.get("recorded_at", "")

        return_temps = [v for k, v in latest.items() if "return_air_temp" in k]
        outdoor_temps = [
            v
            for k, v in latest.items()
            if k.endswith("outdoor_temp") or k.endswith("outside_air_temp") or k.endswith("oa_temp")
        ]
        oat = outdoor_temps[0] if outdoor_temps else None
        if not return_temps or oat is None:
            return None

        avg_return = sum(return_temps) / len(return_temps)
        delta = avg_return - oat
        freshness = self._freshness_minutes(most_recent_ts)
        threshold = FRESHNESS_THRESHOLDS["ahu_heat_load"]
        base_confidence = self._freshness_confidence(freshness, threshold)

        if delta >= AHU_RETURN_OAT_STRONG_DELTA:
            occ_pct = 90.0
            signal_confidence = 0.8
        elif delta >= AHU_RETURN_OAT_MIN_DELTA:
            occ_pct = max(delta / AHU_RETURN_OAT_STRONG_DELTA * 90.0, 10.0)
            signal_confidence = 0.5
        else:
            occ_pct = 0.0
            signal_confidence = 0.3

        return OccupancySignalVerdict(
            source="ahu_heat_load",
            normalized_pct=occ_pct,
            confidence=min(base_confidence * signal_confidence, SIGNAL_CONFIDENCE_MAX),
            freshness_minutes=freshness,
            is_available=True,
            raw_value={"avg_return_temp": avg_return, "outdoor_temp": oat, "delta": delta},
        )

    async def _get_water_consumption(self, site_id: str) -> OccupancySignalVerdict | None:
        """Detect occupancy from potable water consumption rate.

        Queries the 4 most recent total_consumption_m3 readings and computes
        a per-hour delta. A positive, plausible delta means someone is consuming
        water → building is occupied. Zero delta over ≥30 minutes is a moderate
        absence signal. Counter resets (negative or huge deltas) are rejected.
        """
        try:
            prefix = self._site_eq_prefix(site_id)
            resp = (
                self._sb.table("equipment_sensor_readings")
                .select("equipment_id,sensor_type,value,recorded_at")
                .eq("site_id", site_id)
                .eq("sensor_type", "total_consumption_m3")
                .gte("equipment_id", f"{prefix}-WATER-")
                .lt("equipment_id", f"{prefix}-WATERZ-")
                .order("recorded_at", desc=True)
                .limit(4)
                .execute()
            )
        except Exception as e:
            logger.debug("Water consumption query failed for %s: %s", site_id, e)
            return None

        rows = resp.data or []
        if len(rows) < 2:
            return None

        try:
            newest = rows[0]
            oldest = rows[-1]
            v_new = float(newest["value"])
            v_old = float(oldest["value"])
            delta_m3 = v_new - v_old
            t_new = datetime.fromisoformat(newest["recorded_at"].replace("Z", "+00:00"))
            t_old = datetime.fromisoformat(oldest["recorded_at"].replace("Z", "+00:00"))
            elapsed_hours = max((t_new - t_old).total_seconds() / 3600.0, 1e-6)
        except (ValueError, TypeError, KeyError):
            return None

        rate_m3_per_hour = delta_m3 / elapsed_hours

        # Reject counter resets (negative delta) and implausible spikes.
        if rate_m3_per_hour < 0 or rate_m3_per_hour > WATER_MAX_DELTA_M3_PER_HOUR:
            return None

        freshness = self._freshness_minutes(newest.get("recorded_at", ""))
        threshold = FRESHNESS_THRESHOLDS["water_consumption"]
        base_confidence = self._freshness_confidence(freshness, threshold)

        if rate_m3_per_hour >= WATER_MIN_DELTA_M3_PER_HOUR:
            # Positive consumption: someone is using water → occupied.
            # Confidence scales with rate up to ~10 m3/h (active workday level).
            rate_confidence = min(rate_m3_per_hour / 10.0, 0.85)
            confidence = min(base_confidence * rate_confidence, SIGNAL_CONFIDENCE_MAX)
            occ_pct = min(rate_m3_per_hour / 10.0 * 100, 100.0)
        else:
            # Zero consumption over the observation window: weak absence signal.
            # Only meaningful when window is ≥15 min (otherwise too short to tell).
            if elapsed_hours * 60 < 15:
                return None
            occ_pct = 0.0
            confidence = min(base_confidence * 0.45, SIGNAL_CONFIDENCE_MAX)

        return OccupancySignalVerdict(
            source="water_consumption",
            normalized_pct=occ_pct,
            confidence=confidence,
            freshness_minutes=freshness,
            is_available=True,
            raw_value={
                "rate_m3_per_hour": round(rate_m3_per_hour, 3),
                "delta_m3": round(delta_m3, 3),
                "elapsed_hours": round(elapsed_hours, 2),
                "newest_value": v_new,
            },
        )

    # ── Fusion engine ─────────────────────────────────────────────────

    def _fuse(self, signals: dict[str, OccupancySignalVerdict]) -> FusedOccupancyVerdict:
        if not signals:
            return FusedOccupancyVerdict(
                occupancy_percent=0.0,
                occupancy_count=0,
                confidence=0.0,
                is_occupied=False,
                signals={},
                conflicts=(),
                gate_override="none",
            )

        available = {k: v for k, v in signals.items() if v.is_available}
        if not available:
            return FusedOccupancyVerdict(
                occupancy_percent=0.0,
                occupancy_count=0,
                confidence=0.0,
                is_occupied=False,
                signals=signals,
                conflicts=(),
                gate_override="none",
            )

        available_weights = {k: _BASE_WEIGHTS[k] for k in available if k in _BASE_WEIGHTS}
        unaccounted_weight = sum(_BASE_WEIGHTS[k] for k in _BASE_WEIGHTS if k not in available_weights)
        if available_weights and unaccounted_weight > 0:
            factor = 1.0 / (1.0 - unaccounted_weight)
            available_weights = {k: w * factor for k, w in available_weights.items()}
        total_w = sum(available_weights.values())
        if total_w > 0:
            available_weights = {k: w / total_w for k, w in available_weights.items()}

        fused_pct = 0.0
        fused_confidence = 0.0
        total_effective_weight = 0.0
        for src, verdict in available.items():
            w = available_weights.get(src, 0)
            effective_w = w * verdict.confidence
            fused_pct += verdict.normalized_pct * effective_w
            fused_confidence += verdict.confidence * w
            total_effective_weight += effective_w
        if total_effective_weight > 0:
            fused_pct /= total_effective_weight

        conflicts = self._detect_conflicts(available)
        credible_presence = any(
            (
                source == "lighting_pir"
                and isinstance(v.raw_value, dict)
                and int(v.raw_value.get("occupied_sensors") or 0) > 0
                and v.confidence >= 0.50
            )
            or (source != "lighting_pir" and v.normalized_pct >= 10.0 and v.confidence >= 0.50)
            for source, v in available.items()
            if source in {"simbiot_aggregate", "lighting_pir", "security_badges", "ahu_heat_load", "water_consumption"}
        )
        is_occupied = fused_pct > 10.0 or credible_presence
        gate_override = "none"

        # When signals agree (no conflict), trust the highest-confidence signal.
        # When signals conflict, the weighted average already reflects disagreement.
        if not conflicts:
            fused_confidence = max(v.confidence for v in available.values())

        if conflicts and fused_confidence < GATE_UNCERTAIN_THRESHOLD:
            gate_override = "conflict_uncertain"
            is_occupied = True
        elif credible_presence and fused_pct <= 10.0:
            gate_override = "presence_signal"
            is_occupied = True

        occ_counts = []
        for v in available.values():
            if isinstance(v.raw_value, dict):
                for key in ("total_occupancy", "occupancy_count", "total_people"):
                    val = v.raw_value.get(key)
                    if isinstance(val, (int, float)):
                        occ_counts.append(val)
        fused_count = max(occ_counts) if occ_counts else 0

        return FusedOccupancyVerdict(
            occupancy_percent=round(fused_pct, 1),
            occupancy_count=int(fused_count),
            confidence=round(fused_confidence, 3),
            is_occupied=is_occupied,
            signals=signals,
            conflicts=tuple(conflicts),
            gate_override=gate_override,
        )

    @staticmethod
    def _detect_conflicts(available: dict[str, OccupancySignalVerdict]) -> list[OccupancyConflict]:
        conflicts: list[OccupancyConflict] = []
        sources = list(available.keys())
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                a = available[sources[i]]
                b = available[sources[j]]
                if not a.is_available or not b.is_available:
                    continue
                delta = abs(a.normalized_pct - b.normalized_pct)
                if delta >= CONFLICT_OCCUPANCY_DELTA:
                    conflicts.append(
                        OccupancyConflict(
                            signals=(sources[i], sources[j]),
                            delta_pct=round(delta, 1),
                            description=f"{sources[i]} ({a.normalized_pct:.0f}%) vs {sources[j]} ({b.normalized_pct:.0f}%) — Δ{delta:.0f}pp",
                        )
                    )
        return conflicts

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _freshness_minutes(recorded_at_str: str) -> float:
        if not recorded_at_str:
            return 9999.0
        try:
            recorded = datetime.fromisoformat(recorded_at_str.replace("Z", "+00:00"))
            return (datetime.now(UTC) - recorded).total_seconds() / 60.0
        except (ValueError, TypeError):
            return 9999.0

    @staticmethod
    def _freshness_delta(older_ts: str, newer_ts: str) -> float:
        if not older_ts or not newer_ts:
            return 9999.0
        try:
            t1 = datetime.fromisoformat(older_ts.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(newer_ts.replace("Z", "+00:00"))
            return abs((t2 - t1).total_seconds()) / 60.0
        except (ValueError, TypeError):
            return 9999.0

    @staticmethod
    def _freshness_confidence(freshness_minutes: float, threshold: float) -> float:
        if freshness_minutes <= threshold * 0.5:
            return 1.0
        if freshness_minutes >= threshold * 3:
            return SIGNAL_CONFIDENCE_STALE
        ratio = (threshold * 3 - freshness_minutes) / (threshold * 3 - threshold * 0.5)
        return SIGNAL_CONFIDENCE_STALE + ratio * (1.0 - SIGNAL_CONFIDENCE_STALE)

    @staticmethod
    def _site_agg_equipment(site_id: str) -> str:
        prefix = site_id.replace("site-", "S").upper()
        return f"{prefix}-SITE-AGG"

    @staticmethod
    def _site_eq_prefix(site_id: str) -> str:
        return site_id.replace("site-", "S").upper()

    @classmethod
    def _zone_co2_equipment_id(cls, site_id: str, zone_id: str) -> str:
        prefix = cls._site_eq_prefix(site_id)
        raw = str(zone_id or "").strip().upper()
        if raw.startswith(f"{prefix}-ZONE-"):
            return raw
        if raw.startswith("ZONE-"):
            return f"{prefix}-ZONE-{raw.rsplit('-', 1)[-1]}"
        return f"{prefix}-ZONE-{raw}"

    @staticmethod
    def _canonical_site_id(site_id: str) -> str:
        if site_id.upper().startswith("S") and site_id[1:].isdigit():
            return f"site-{site_id[1:]}"
        return site_id


# ── Module-level singleton accessor ───────────────────────────────────────

_service_instance: OccupancyFusionService | None = None


def get_occupancy_fusion_service() -> OccupancyFusionService:
    global _service_instance
    if _service_instance is None:
        _service_instance = OccupancyFusionService()
    return _service_instance


def reset_occupancy_fusion_service() -> None:
    global _service_instance
    _service_instance = None
