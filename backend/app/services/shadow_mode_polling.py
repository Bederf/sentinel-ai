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
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger("sentinel.shadow_mode")


class ShadowModePollingService:
    """Polls the site bridge and feeds live data to the ML pipeline."""

    def __init__(self, site_id: str = "site-002"):
        self.site_id = site_id
        self._poll_count = 0
        self._last_poll_result: dict[str, Any] | None = None  # Cached result of last poll
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
            self._catalog_loaded_at = datetime.now(tz=UTC)

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

            # Build trends sensor code list — ALL sensors from the catalog.
            # LSTM/autoencoder train on whatever is available; more sensors = better
            # coverage. The poll loop batches to 20 per cycle to stay within time
            # budget, so we don't need to filter here — queue everything.
            sensor_codes: set[str] = set()
            for obj in objs:
                point_type = obj.get("point_type", "")
                obj_id = obj.get("object_id", "")

                if point_type == "sensor" and obj_id:
                    # Convert "CH-1.ChwSupplyTemp" → "CH-1-ChwSupplyTemp" for bridge API
                    sensor_codes.add(obj_id.replace(".", "-"))

            # Add explicit zone temp trends (pre-emptive, in case catalog lacks these)
            for i in range(1, 21):
                sensor_codes.add(f"Zone-{i:03d}-temp")

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
        now = datetime.now(tz=UTC)
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

        # ── 6. Sync equipment online/offline status from /points ─────────────
        points_result = await self._sync_equipment_status(base, headers)
        result["equipment_updated"] = points_result["updated"]
        result["equipment_created"] = points_result.get("created", 0)
        result["equipment_missing_from_bridge"] = points_result["missing_from_bridge"]

        # ── 7. Merge all states ───────────────────────────────────────────────
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
        self._last_poll_result = result

        # Upsert log_sources so monitoring dashboard reflects bridge activity
        if equipment_states:
            self._upsert_log_source(len(equipment_states))

        logger.info(
            f"[SHADOW] Poll {self._poll_count}: {len(equipment_states)} states, "
            f"zones={result.get('zones_polled', 0)}, faults={fault_count}, "
            f"trends={result.get('trends_with_data', 0)}, "
            f"ml_hours={result.get('ml_hours_ingested', '?')}, "
            f"fault_buf={result.get('fault_buffer_size', '?')}, "
            f"equip_updated={result.get('equipment_updated', 0)}, "
            f"equip_created={result.get('equipment_created', 0)}, "
            f"errors={errors or 'none'}"
        )
        return result

    @property
    def status(self) -> dict:
        """Return bridge connection status for API reporting.

        Connected if we have successfully polled at least once AND the last poll
        reported telemetry_fetched=True.
        """
        if self._poll_count == 0:
            return {"connected": False, "reason": "not_polled", "poll_count": 0, "last_poll": None}

        last = self._last_poll_result or {}
        connected = last.get("telemetry_fetched", False) and not last.get("errors")
        reason = None if connected else last.get("errors", ["unknown"])[0] if last.get("errors") else "poll_failed"

        return {
            "connected": connected,
            "reason": reason,
            "poll_count": self._poll_count,
            "last_poll": self._energy_last_poll.isoformat() if self._energy_last_poll else None,
            "ml_hours_ingested": last.get("ml_hours_ingested"),
            "bridge_data_source": "remote_bridge",
        }

    def _upsert_log_source(self, equipment_state_count: int) -> None:
        """Create or update a log_sources entry reflecting bridge polling activity.

        This keeps the System Health monitoring page in sync with shadow mode operation,
        which bypasses the commissioning flow and doesn't write to log_sources directly.
        """
        try:
            from app.database.repositories.integration_repository import IntegrationRepository

            repo = IntegrationRepository()
            source_name = f"Shadow Bridge ({self.site_id})"

            existing = repo.get_log_source_by_name(source_name)
            now_iso = datetime.utcnow().isoformat()

            if existing:
                repo.update_log_source(
                    existing["id"],
                    {
                        "is_active": True,
                        "last_sync_at": now_iso,
                        "last_sync_status": "success",
                        "last_sync_records": equipment_state_count,
                    },
                )
            else:
                # Resolve site code (e.g. "site-002") to UUID for DB
                from app.database.repositories.site_repository import SiteRepository

                site_repo = SiteRepository()
                site_record = site_repo.client.table("sites").select("id").eq("code", self.site_id).execute()
                site_uuid = site_record.data[0]["id"] if site_record.data else self.site_id
                repo.create_log_source(
                    {
                        "site_id": site_uuid,
                        "name": source_name,
                        "source_type": "shadow_polling",
                        "connection_type": "api",
                        "is_active": True,
                        "sync_frequency_minutes": 5,
                        "last_sync_at": now_iso,
                        "last_sync_status": "success",
                        "last_sync_records": equipment_state_count,
                    }
                )
            logger.debug(f"[SHADOW] log_sources upserted: {source_name}")
        except Exception as e:
            logger.warning(f"[SHADOW] Failed to upsert log_sources: {e}")

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

    def _parse_equipment_code(self, code: str) -> tuple[str, str]:
        """Parse equipment code into (type, display_name).

        Code format: S002-{TYPE}-{rest} where TYPE is HVAC category
        e.g. S002-CHILLER-B1-001 → type=chiller, name=S002 Chiller B1-001
             S002-FCU-101         → type=fcu,    name=S002 FCU 101
             S002-MTR-B1-MAIN     → type=meter,  name=S002 Meter B1 Main
        """
        parts = code.split("-")
        if len(parts) >= 2:
            raw_type = parts[1].upper()
        else:
            raw_type = "UNKNOWN"

        # Normalise equipment type labels
        type_map = {
            "CHILLER": "chiller",
            "AHU": "ahu",
            "FCU": "fcu",
            "VAV": "vav",
            "SPLIT": "split",
            "CT": "cooling_tower",
            "CRAC": "crac",
            "DALI": "dali",
            "GEN": "generator",
            "TX": "transformer",
            "UPS": "ups",
            "ATS": "ats",
            "MSB": "msb",
            "MTR": "meter",
            "PFC": "pfc",
            "FDR": "feeder",
            "MV": "mv",
            "DB": "distribution_board",
            "BESS": "bess",
            "INV": "inverter",
            "PUMP": "pump",
            "FIRE": "fire",
            "ACC": "access_control",
            "CCTV": "cctv",
            "LUM": "luminaire",
            "ZONE": "zone",
            "UNKNOWN": "unknown",
        }
        eq_type = type_map.get(raw_type, "unknown")
        # Build human-readable name: "S002 Chiller B1-001"
        name_parts = code.split("-")
        if len(name_parts) >= 3:
            name = code.replace("-", " ", 1)  # "S002-CHILLER..." → "S002 CHILLER..."
            name = name.replace("-", " ", 1)  # "S002 CHILLER-B1..." → "S002 CHILLER B1..."
        else:
            name = code
        return eq_type, name

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

    async def _sync_equipment_status(self, base: str, headers: dict[str, str]) -> dict[str, Any]:
        """Sync equipment online/offline status from bridge /points endpoint.

        Updates the status field in Supabase equipment table for all equipment
        that appears in the bridge /points response. Equipment not in the bridge
        are marked offline. Equipment on the bridge but not in DB are auto-created.

        Returns:
            Dict with 'updated' count, 'missing_from_bridge' list, and 'created' count.
        """
        result = {"updated": 0, "missing_from_bridge": [], "created": 0}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{base}/api/sites/{self.site_id}/points",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            # /points returns {"equipment": [{"code": {"status": "online", ...}}, ...]}
            # The response is a list containing one dict with ALL equipment codes as keys.
            equip_list = data.get("equipment", [])
            if isinstance(equip_list, list) and len(equip_list) > 0:
                equip_status_map = equip_list[0] if isinstance(equip_list[0], dict) else {}
            else:
                equip_status_map = {}

            if not equip_status_map:
                return result

            # Get all equipment from DB for this site
            from app.database.repositories.equipment_repository import EquipmentRepository
            from app.database.repositories.site_repository import SiteRepository

            site_repo = SiteRepository()
            site = site_repo.get_by_id(self.site_id)
            site_uuid = site.get("id") if site else None

            if not site_uuid:
                logger.warning(f"[SHADOW] Cannot sync equipment status — site {self.site_id} not found in DB")
                return result

            eq_repo = EquipmentRepository()
            all_equipment = eq_repo.get_all(site_id=site_uuid)

            # Build code sets and a truncated-to-full mapping.
            # Bridge returns truncated codes (up to 15 chars) that may cut mid-word
            # (e.g. "S002-MTR-B1-MAI" = DB "S002-MTR-B1-MAIN", "S002-MTR-R-SOL" = DB "S002-MTR-R-SOLAR").
            # We match by checking if the bridge code is a prefix of the DB code.
            db_full_codes = [eq.get("code") for eq in all_equipment]

            # Build sets for membership tests
            db_full_set = set(db_full_codes)
            bridge_codes = set(equip_status_map.keys())
            bridge_lum_codes = {c for c in bridge_codes if "-LUM-" in c}
            # Map bridge codes → full DB codes.
            # Strategy: exact match first, then prefix match (bridge code is prefix of DB code).
            bridge_to_db: dict[str, str] = {}
            for bcode in bridge_codes:
                if bcode in db_full_set:
                    bridge_to_db[bcode] = bcode  # exact match
                else:
                    # Try prefix match: bridge code as prefix of DB code
                    matched = None
                    for db_code in db_full_codes:
                        if db_code.startswith(bcode):
                            if matched is None or len(db_code) < len(matched):
                                matched = db_code
                    if matched:
                        bridge_to_db[bcode] = matched

            mapped_db_codes = set(bridge_to_db.values())

            # Equipment in DB but not on bridge → mark offline
            missing = db_full_set - mapped_db_codes - bridge_lum_codes
            result["missing_from_bridge"] = sorted(missing)

            # Update each equipment found on bridge (using mapped DB codes)
            updated = 0
            for bcode, bridge_status_data in equip_status_map.items():
                if "-LUM-" in bcode and bcode not in bridge_to_db:
                    continue

                db_code = bridge_to_db.get(bcode)
                if not db_code:
                    continue

                bridge_status = bridge_status_data.get("status", "offline")
                # Normalise: bridge returns "online"/"offline" or "normal"/etc.
                # Map to DB status values — 'normal' for online, 'offline' for offline
                db_status = "normal" if bridge_status in ("online", "normal", "ok") else bridge_status

                try:
                    eq_repo.update(db_code, {"status": db_status})
                    updated += 1
                except Exception as e:
                    logger.warning(f"[SHADOW] Failed to update {db_code} ({bcode}): {e}")

            # Mark equipment not present on bridge as offline
            for db_code in missing:
                try:
                    eq_repo.update(db_code, {"status": "offline"})
                    updated += 1
                except Exception as e:
                    logger.warning(f"[SHADOW] Failed to mark {db_code} offline: {e}")

            # Auto-create equipment that exists on bridge but not in DB
            bridge_all_codes = set(equip_status_map.keys())
            new_codes = bridge_all_codes - set(bridge_to_db.keys()) - bridge_lum_codes
            created = 0
            if new_codes:
                for bcode in sorted(new_codes):
                    bridge_status_data = equip_status_map.get(bcode, {})
                    bridge_status = bridge_status_data.get("status", "offline")
                    db_status = "normal" if bridge_status in ("online", "normal", "ok") else bridge_status
                    eq_type, eq_name = self._parse_equipment_code(bcode)
                    # Skip luminaries
                    if "-LUM-" in bcode:
                        continue
                    try:
                        eq_repo.create(
                            {
                                "code": bcode,
                                "name": eq_name,
                                "type": eq_type,
                                "status": db_status,
                                "site_id": site_uuid,
                                "health_score": 100,
                            }
                        )
                        created += 1
                    except Exception as e:
                        logger.warning(f"[SHADOW] Failed to create {bcode}: {e}")

                if created > 0:
                    logger.info(f"[SHADOW] Auto-created {created} equipment from bridge")

            result["updated"] = updated
            result["created"] = created
            if updated > 0 or missing or created > 0:
                logger.info(
                    f"[SHADOW] Equipment status sync: {updated} updated, "
                    f"{len(missing)} missing from bridge, {created} created"
                )

        except Exception as e:
            logger.warning(f"[SHADOW] Equipment status sync failed: {e}")

        return result


_shadow_polling_service: ShadowModePollingService | None = None


def get_shadow_mode_polling_service(site_id: str = "site-002") -> ShadowModePollingService:
    global _shadow_polling_service
    if _shadow_polling_service is None:
        _shadow_polling_service = ShadowModePollingService(site_id=site_id)
    return _shadow_polling_service
