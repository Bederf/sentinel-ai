"""
Shadow Mode Bridge Polling — feeds live BMS data to the ML pipeline.

Polls the site bridge (http://10.99.0.1:8080) for:
  1. /api/sites/{site_id}/zones        — per-zone temperature / CO2 readings
  2. /api/sites/{site_id}/telemetry   — aggregated power / water / equipment summary
  3. /api/sites/{site_id}/alarms       — BACnet alarm events (Fault Classifier buffer)
  4. /api/sites/{site_id}/objects     — 410-point BACnet catalog (cached once)
  5. /api/sites/{site_id}/trends/{id} — per-sensor history (richer LSTM sequences)

Architecture:
  Bridge → ShadowModePollingService.poll() → SentinelDataSync.ingest_equipment_states()
         → SentinelMLFeeder.ingest(data_source="bridge_poll")
         → SentinelMLFeeder.ingest_fault_events(data_source="bms_event")

Fault events from /alarms accumulate in SentinelMLFeeder._fault_events buffer.
When 500+ events are buffered → train Fault Classifier.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("sentinel.shadow_mode")


class ShadowModePollingService:
    """Polls the site bridge and feeds live data to the ML pipeline."""

    def __init__(self, site_id: str = "site-002"):
        self.site_id = site_id
        self._poll_count = 0
        # Cached BACnet object catalog: maps object_id → metadata
        # Loaded once on first poll, refreshed weekly.
        self._object_catalog: dict[str, dict[str, Any]] = {}
        self._catalog_loaded_at: datetime | None = None
        # Zone number → AHU equipment code mapping built from catalog
        self._zone_to_ahu: dict[str, str] = {}
        # Sensor codes for trends polling (built from catalog)
        self._trends_sensor_codes: list[str] = []
        # Energy accumulation state (kWh, accumulated since last DB write)
        self._energy_accumulator: dict[str, float] = {
            "hvac_kwh": 0.0,
            "lighting_kwh": 0.0,
            "other_kwh": 0.0,
            "total_kwh": 0.0,
        }
        self._energy_accum_start: datetime | None = None  # Start of current accumulation period
        self._energy_last_poll: datetime | None = None  # Last poll timestamp for kWh calc

    def _get_bridge_credentials(self) -> tuple[str, str]:
        """Return (base_url, api_token) from settings."""
        from app.config.settings import settings

        base = getattr(settings, "simbiot_api_url", None) or getattr(settings, "bridge_base_url", None)
        if not base:
            raise RuntimeError("Bridge URL not configured — set SIMBIOT_API_URL or BRIDGE_BASE_URL")
        token = getattr(settings, "simbiot_api_key", None) or getattr(settings, "bridge_api_token", None)
        if not token:
            raise RuntimeError("Bridge API token not configured — set SIMBIOT_API_KEY or BRIDGE_API_TOKEN")
        return base.rstrip("/"), token

    async def _load_object_catalog(self, base: str, headers: dict[str, str]) -> None:
        """Load and cache the BACnet object catalog. Called once on first poll."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{base}/api/sites/{self.site_id}/objects",
                    headers=headers,
                    params={"limit": 500},
                )
                resp.raise_for_status()
                data = resp.json()

            objs = data.get("objects", [])
            self._object_catalog = {o["object_id"]: o for o in objs}
            self._catalog_loaded_at = datetime.now(tz=timezone.utc)

            # Build zone → AHU mapping from catalog
            # e.g. zone "Zone-001" (floor B1) → AHU "S002-AHU-B1-001"
            self._zone_to_ahu = {}
            for obj in objs:
                equip_id = obj.get("equipment_id", "")
                equip_type = obj.get("equipment_type", "")
                # Find zone from AHU equipment IDs
                # e.g. "S002-AHU-B1-001" → floor "B1", zone "001"
                if equip_type == "ahu":
                    # Parse "S002-AHU-B1-001" → (site, type, floor, seq)
                    parts = equip_id.split("-")
                    if len(parts) >= 4:
                        _, _typ, floor, seq = parts[0], parts[1], parts[2], parts[3]
                        zone_num = seq
                        zone_id = f"Zone-{zone_num}"
                        if zone_id not in self._zone_to_ahu:
                            self._zone_to_ahu[zone_id] = equip_id

            # Build trends sensor code list — prioritize ML-relevant sensors
            sensor_codes = set()
            for obj in objs:
                equip_type = obj.get("equipment_type", "")
                point_type = obj.get("point_type", "")
                obj_id = obj.get("object_id", "")
                equip_id = obj.get("equipment_id", "")

                if point_type != "sensor":
                    continue

                # Zone temperatures (already covered by /zones, but trends gives history)
                if equip_type == "fcu" and "room_temp" in obj_id.lower():
                    # Already from /zones, skip duplicate
                    pass
                # Chiller supply temp — key for LSTM
                elif equip_type == "chiller" and "chws" in obj_id.lower():
                    # Convert "CH-1.ChwSupplyTemp" → "CH-1-ChwSupplyTemp" for trends
                    sensor_codes.add(obj_id.replace(".", "-"))
                # AHU supply air temp
                elif equip_type == "ahu" and "supply_air_temp" in obj_id:
                    sensor_codes.add(obj_id.replace(".", "-"))
                # AHU fan speed
                elif equip_type == "ahu" and "fan_speed_pct" in obj_id:
                    sensor_codes.add(obj_id.replace(".", "-"))
                # Outdoor conditions
                elif "WEATHER" in obj_id and "outdoor_temp" in obj_id.lower():
                    sensor_codes.add(obj_id.replace(".", "-"))
                elif "WEATHER" in obj_id and "outdoor_humidity" in obj_id.lower():
                    sensor_codes.add(obj_id.replace(".", "-"))

            # Build floor→AHU map from AHU equipment IDs in catalog
            floor_to_ahu: dict[str, str] = {}
            for obj in objs:
                if obj.get("equipment_type") == "ahu":
                    equip_id = obj.get("equipment_id", "")
                    # "S002-AHU-B1-001" → floor "B1"
                    parts = equip_id.split("-")
                    if len(parts) >= 3:
                        floor = parts[2]  # "B1", "L1", "L2", "L3"
                        if floor not in floor_to_ahu:
                            floor_to_ahu[floor] = equip_id

            # Add explicit zone temp trends
            for i in range(1, 21):
                sensor_codes.add(f"Zone-{i:03d}-temp")

            # Add AHU trends for each known floor
            for floor, ahu_id in floor_to_ahu.items():
                sensor_codes.add(f"{ahu_id}-supply_air_temp")
                sensor_codes.add(f"{ahu_id}-fan_speed_pct")

            self._trends_sensor_codes = sorted(sensor_codes)
            logger.info(
                f"[SHADOW] Object catalog loaded: {len(objs)} objects, "
                f"{len(self._object_catalog)} indexed, {len(self._zone_to_ahu)} zone→AHU mappings, "
                f"{len(self._trends_sensor_codes)} trend sensors"
            )

        except Exception as e:
            logger.warning(f"[SHADOW] Failed to load object catalog: {e}")

    async def poll(self) -> dict[str, Any]:
        """Poll bridge and feed data to ML pipeline. Call this on each poll cycle."""
        self._poll_count += 1
        now = datetime.now(tz=timezone.utc)
        result: dict[str, Any] = {"poll_count": self._poll_count, "errors": []}

        try:
            base, token = self._get_bridge_credentials()
        except Exception as e:
            logger.error(f"[SHADOW] Bridge credentials error: {e}")
            result["errors"].append(str(e))
            return result

        headers = {"Authorization": f"Bearer {token}"}

        # ── 1. Load object catalog on first poll ──────────────────────────────
        if not self._object_catalog:
            await self._load_object_catalog(base, headers)

        errors: list[str] = []

        # ── 2. Fetch zone readings ────────────────────────────────────────────
        zone_states: dict[str, dict[str, Any]] = {}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{base}/api/sites/{self.site_id}/zones",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            zones = data.get("zones", [])
            logger.debug(f"[SHADOW] Got {len(zones)} zone readings")

            for z in zones:
                zone_id: str = z.get("zone_id", "")
                parts = zone_id.split("-")
                zone_num = parts[1] if len(parts) == 2 else zone_id
                equip_code = f"S002-FCU-{zone_num}"

                temp = z.get("temperature_c")
                co2 = z.get("co2_ppm")

                readings: dict[str, float] = {}
                if temp is not None:
                    readings["room_temp"] = float(temp)
                if co2 is not None:
                    readings["co2_ppm"] = float(co2)

                if readings:
                    zone_states[equip_code] = {
                        "type": "fcu",
                        "sensor_readings": readings,
                    }

            result["zones_polled"] = len(zones)

        except httpx.HTTPStatusError as e:
            logger.warning(f"[SHADOW] Zone poll HTTP {e.response.status_code}: {e.response.text[:200]}")
            errors.append(f"zones: HTTP {e.response.status_code}")
        except Exception as e:
            logger.warning(f"[SHADOW] Zone poll error: {e}")
            errors.append(f"zones: {e}")

        # ── 3. Fetch aggregated telemetry ────────────────────────────────────
        agg_states: dict[str, dict[str, Any]] = {}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{base}/api/sites/{self.site_id}/telemetry",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            power = data.get("power", {})
            water = data.get("water", {})
            equip_summary = data.get("equipment_summary", {})

            hvac_kw = power.get("hvac_kw")
            lighting_kw = power.get("lighting_kw")
            total_kw = power.get("total_kw")
            flow_lpm = water.get("flow_lpm")
            pressure_bar = water.get("pressure_bar")

            agg_readings: dict[str, float] = {}
            if hvac_kw is not None:
                agg_readings["hvac_kw"] = float(hvac_kw)
            if lighting_kw is not None:
                agg_readings["lighting_kw"] = float(lighting_kw)
            if total_kw is not None:
                agg_readings["total_kw"] = float(total_kw)
            # Accumulate energy from power readings (kW → kWh)
            if hvac_kw is not None and lighting_kw is not None and total_kw is not None:
                self._accumulate_energy(float(hvac_kw), float(lighting_kw), float(total_kw), now)
            if flow_lpm is not None:
                agg_readings["flow_lpm"] = float(flow_lpm)
            if pressure_bar is not None:
                agg_readings["pressure_bar"] = float(pressure_bar)

            if agg_readings:
                agg_states["S002-CHILLER-AGG"] = {
                    "type": "chiller",
                    "sensor_readings": agg_readings,
                }

            zone_count = data.get("zone_count", 0)
            equip_online = equip_summary.get("online", 0)
            if zone_count or equip_online:
                agg_states["S002-SITE-AGG"] = {
                    "type": "ahu",
                    "sensor_readings": {
                        "zone_count": float(zone_count),
                        "equip_online": float(equip_online),
                    },
                }

            result["telemetry_fetched"] = True

        except httpx.HTTPStatusError as e:
            logger.warning(f"[SHADOW] Telemetry poll HTTP {e.response.status_code}: {e.response.text[:200]}")
            errors.append(f"telemetry: HTTP {e.response.status_code}")
        except Exception as e:
            logger.warning(f"[SHADOW] Telemetry poll error: {e}")
            errors.append(f"telemetry: {e}")

        # ── 4. Fetch fault alarms (Fault Classifier buffer) ──────────────────
        fault_count = 0
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{base}/api/sites/{self.site_id}/alarms",
                    headers=headers,
                    params={"active_only": False},
                )
                resp.raise_for_status()
                alarm_data = resp.json()

            alarms = alarm_data.get("alarms", [])
            if alarms:
                # Feed alarm events to ML feeder fault buffer
                from app.services.sentinel_data_sync import get_sentinel_data_sync

                sync = get_sentinel_data_sync(site_id=self.site_id.replace("site-", "S"))
                for alarm in alarms:
                    sync.ml_feeder.ingest_fault_event(alarm)
                fault_count = len(alarms)
                logger.info(f"[SHADOW] {fault_count} alarms → Fault Classifier buffer")

            result["faults_polled"] = fault_count

        except httpx.HTTPStatusError as e:
            logger.warning(f"[SHADOW] Alarms poll HTTP {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            logger.warning(f"[SHADOW] Alarms poll error: {e}")

        # ── 5. Fetch trends for richer LSTM sequences (async batch) ───────────
        # Poll the most ML-relevant sensor trends. History accumulates in bridge;
        # once populated, these give LSTM sequences for chiller + AHU + outdoor.
        trends_states: dict[str, dict[str, Any]] = {}
        if self._trends_sensor_codes:
            # Poll up to 20 sensors per cycle to stay within time budget
            sensor_batch = self._trends_sensor_codes[:20]
            try:

                async def fetch_trend(sensor_code: str) -> tuple[str, dict[str, Any] | None]:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            r = await client.get(
                                f"{base}/api/sites/{self.site_id}/trends/{sensor_code}",
                                headers=headers,
                                params={"limit": 100},
                            )
                            r.raise_for_status()
                            d = r.json()
                            samples = d.get("samples", [])
                            if samples:
                                # Use most recent sample
                                latest = samples[-1]
                                return sensor_code, {
                                    "timestamp": latest.get("ts"),
                                    "value": latest.get("value"),
                                    "unit": d.get("unit"),
                                }
                            return sensor_code, None
                    except Exception:
                        return sensor_code, None

                import asyncio

                trend_results = await asyncio.gather(
                    *[fetch_trend(sc) for sc in sensor_batch],
                    return_exceptions=True,
                )

                for tr in trend_results:
                    if isinstance(tr, Exception):
                        continue
                    sensor_code, sample = tr
                    if sample and sample.get("value") is not None:
                        # Map sensor_code → equipment + reading name
                        equip_code, reading_name = self._resolve_sensor(sensor_code)
                        if equip_code and reading_name:
                            if equip_code not in trends_states:
                                trends_states[equip_code] = {"type": "", "sensor_readings": {}}
                            equip_type = trends_states[equip_code]["type"]
                            if not equip_type:
                                trends_states[equip_code]["type"] = self._equip_type_from_sensor(sensor_code)
                            trends_states[equip_code]["sensor_readings"][reading_name] = float(sample["value"])

                result["trends_polled"] = len(sensor_batch)
                result["trends_with_data"] = sum(
                    1
                    for code, s in zip(sensor_batch, trend_results)
                    if not isinstance(s, Exception) and s[1] is not None
                )

            except Exception as e:
                logger.warning(f"[SHADOW] Trends poll error: {e}")

        # ── 6. Merge all states ───────────────────────────────────────────────
        # Trends states have higher fidelity (chiller supply temp from BACnet
        # vs aggregated HVAC_kW from /telemetry), so they take priority over
        # the aggregated entries for the same equipment code.
        equipment_states: dict[str, dict[str, Any]] = {**agg_states, **zone_states}
        for code, state in trends_states.items():
            if state["sensor_readings"]:
                equipment_states[code] = state

        if not equipment_states:
            logger.warning(f"[SHADOW] Poll {self._poll_count}: no data — errors={errors}")
            result["errors"] = errors
            return result

        # ── 7. Feed SentinelDataSync (Supabase + ML pipeline) ─────────────────
        try:
            from app.services.sentinel_data_sync import get_sentinel_data_sync

            sync = get_sentinel_data_sync(site_id=self.site_id.replace("site-", "S"))
            await sync.ingest_equipment_states(equipment_states, now, data_source="bridge_poll")
            result["equipment_states"] = len(equipment_states)
            result["ml_hours_ingested"] = sync.ml_feeder.hours_ingested
            result["fault_buffer_size"] = sync.ml_feeder.fault_event_count
        except Exception as e:
            logger.warning(f"[SHADOW] SentinelDataSync error: {e}")
            errors.append(f"sync: {e}")

        result["errors"] = errors
        logger.info(
            f"[SHADOW] Poll {self._poll_count}: {len(equipment_states)} states, "
            f"zones={result.get('zones_polled', 0)}, faults={fault_count}, "
            f"trends={result.get('trends_with_data', 0)}, "
            f"ml_hours={result.get('ml_hours_ingested', '?')}, "
            f"fault_buf={result.get('fault_buffer_size', '?')}, "
            f"errors={errors or 'none'}"
        )
        return result

    def _accumulate_energy(self, hvac_kw: float, lighting_kw: float, total_kw: float, now: datetime) -> None:
        """Accumulate energy from instantaneous power readings.

        Accumulates kWh based on time elapsed since last poll.
        Flushes to DB when day changes (new UTC date).
        """
        if self._energy_last_poll is None:
            self._energy_accum_start = now
            self._energy_last_poll = now
            return

        elapsed_seconds = (now - self._energy_last_poll).total_seconds()
        elapsed_hours = elapsed_seconds / 3600.0

        # Cap at 1 hour max between polls (avoid huge jumps after gaps)
        elapsed_hours = min(elapsed_hours, 1.0)

        self._energy_accumulator["hvac_kwh"] += hvac_kw * elapsed_hours
        self._energy_accumulator["lighting_kwh"] += lighting_kw * elapsed_hours
        self._energy_accumulator["other_kwh"] += (total_kw - hvac_kw - lighting_kw) * elapsed_hours
        self._energy_accumulator["total_kwh"] += total_kw * elapsed_hours
        self._energy_last_poll = now

        # Check if day changed (UTC midnight)
        current_date = now.date()
        accum_date = self._energy_accum_start.date() if self._energy_accum_start else None

        if accum_date and current_date > accum_date:
            # New day — flush yesterday's accumulated energy to DB
            self._flush_energy_to_db(accum_date)
            # Reset accumulator for new day
            self._energy_accumulator = {"hvac_kwh": 0.0, "lighting_kwh": 0.0, "other_kwh": 0.0, "total_kwh": 0.0}
            self._energy_accum_start = now

    def _flush_energy_to_db(self, accum_date, force: bool = False) -> None:
        """Write accumulated energy to energy_consumption_history table."""
        from app.database.repositories.energy_consumption_repository import get_energy_consumption_repository

        total = self._energy_accumulator["total_kwh"]
        # Only write if meaningful (at least 0.01 kWh — avoids spurious zero writes)
        if not force and total < 0.01:
            return

        try:
            repo = get_energy_consumption_repository()
            repo.upsert(
                site_id=self.site_id,
                consumption_date=accum_date,
                hvac_kwh=round(self._energy_accumulator["hvac_kwh"], 3),
                lighting_kwh=round(self._energy_accumulator["lighting_kwh"], 3),
                other_kwh=round(self._energy_accumulator["other_kwh"], 3),
            )
            logger.info(
                f"[SHADOW] Energy flushed to DB: {accum_date} — "
                f"total={total:.2f} kWh (hvac={self._energy_accumulator['hvac_kwh']:.2f}, "
                f"lighting={self._energy_accumulator['lighting_kwh']:.2f})"
            )
        except Exception as e:
            logger.warning(f"[SHADOW] Energy flush failed: {e}")

    def _resolve_sensor(self, sensor_code: str) -> tuple[str | None, str | None]:
        """Resolve a sensor_code to (equipment_code, reading_name).

        Maps bridge sensor codes to SENTINEL equipment codes using the cached
        object catalog and zone→AHU mapping.

        Examples:
          "Zone-001-temp"     → "S002-FCU-001", "room_temp"
          "CH-1-ChwSupplyTemp" → "S002-CHILLER-B1-001", "chw_supply_temp"
          "S002-AHU-B1-001-supply_air_temp" → "S002-AHU-B1-001", "supply_temp"
        """
        # Zone temperature: Zone-001-temp → S002-FCU-001
        if sensor_code.startswith("Zone-") and "-temp" in sensor_code:
            parts = sensor_code.replace("-temp", "").split("-")
            if len(parts) == 2:
                zone_num = parts[1]
                return f"S002-FCU-{zone_num}", "room_temp"
            return None, None

        # Chiller supply temp: CH-1-ChwSupplyTemp → S002-CHILLER-B1-001
        if "ChwSupplyTemp" in sensor_code:
            # "CH-1-ChwSupplyTemp" → rsplit gives ["CH-1", "ChwSupplyTemp"]
            chiller_id = sensor_code.rsplit("-", 1)[0]  # "CH-1"
            chiller_map = {
                "CH-1": "S002-CHILLER-B1-001",
                "CH-2": "S002-CHILLER-B1-002",
            }
            equip_code = chiller_map.get(chiller_id, f"S002-CHILLER-B1-{chiller_id}")
            return equip_code, "chw_supply_temp"

        # AHU sensors: S002-AHU-B1-001-supply_air_temp
        if "AHU-" in sensor_code:
            parts = sensor_code.split("-")
            if len(parts) >= 5:
                site, typ, floor, seq, point = parts[0], parts[1], parts[2], parts[3], "-".join(parts[4:])
                equip_code = f"{site}-{typ}-{floor}-{seq}"
                reading_name = self._ahu_point_to_reading(point)
                return equip_code, reading_name

        # Weather: SITE002-WEATHER-outdoor_temperature
        if "WEATHER" in sensor_code and "outdoor_temp" in sensor_code.lower():
            return "S002-SITE-AGG", "outdoor_temp"
        if "WEATHER" in sensor_code and "humidity" in sensor_code.lower():
            return "S002-SITE-AGG", "outdoor_humidity"

        return None, None

    def _ahu_point_to_reading(self, point: str) -> str:
        """Map BACnet AHU point names to SENTINEL reading names."""
        mapping = {
            "supply_air_temp": "supply_temp",
            "fan_speed_pct": "fan_current",
            "return_air_temp": "return_temp",
            "filter_dp": "filter_dp",
            "damper_position": "damper_position",
        }
        return mapping.get(point, point)

    def _equip_type_from_sensor(self, sensor_code: str) -> str:
        """Infer equipment type from sensor code string."""
        if "AHU" in sensor_code:
            return "ahu"
        if "CH-" in sensor_code:
            return "chiller"
        if "FCU" in sensor_code or "Zone-" in sensor_code:
            return "fcu"
        if "WEATHER" in sensor_code:
            return "ahu"
        return "unknown"


_shadow_polling_service: ShadowModePollingService | None = None


def get_shadow_mode_polling_service(site_id: str = "site-002") -> ShadowModePollingService:
    global _shadow_polling_service
    if _shadow_polling_service is None:
        _shadow_polling_service = ShadowModePollingService(site_id=site_id)
    return _shadow_polling_service
