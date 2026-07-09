"""Data Freshness Monitor — SLI Tier 2: Data Freshness Pipeline.

Runs every 5 minutes (300s) via BackgroundSchedulerService.
Calculates age of normalized data per source, updates SLI pass/fail,
detects new breaches, auto-resolves resolved ones.

Wired into BackgroundSchedulerService via add_data_freshness_monitor_job().
"""

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from app.config.settings import settings

logger = logging.getLogger("data-freshness-monitor")


@dataclass
class FreshnessResult:
    site_id: str
    data_source: str
    age_seconds: int | None
    target_seconds: int
    sli_pass: bool
    breach_started: bool = False
    breach_resolved: bool = False
    breach_duration_seconds: int | None = None


class DataFreshnessMonitor:
    """5-minute interval freshness checks for all registered data sources per site."""

    # High-priority sources that trigger Telegram alerts on breach
    _CRITICAL_SOURCES: ClassVar[set[str]] = {"bms_telemetry", "anomalies", "telemetry_streams"}
    _TELEMETRY_STREAM_SOURCE: ClassVar[str] = "telemetry_streams"
    _TELEMETRY_STREAM_TARGET_SECONDS: ClassVar[int] = 900
    _TELEMETRY_STREAM_SAMPLE_LIMIT: ClassVar[int] = 12
    _DERIVED_TELEMETRY_SENSOR_TYPES: ClassVar[set[str]] = {
        "anomaly_score",
        "autoencoder_anomaly_score",
        "lstm_anomaly_score",
    }
    _NON_FRESHNESS_SENSOR_TYPES: ClassVar[set[str]] = {
        "color_temp_k",
        "device_type",
        "gear_operating_hours",
        "group_0_7",
        "group_8_15",
        "group_command",
        "lamp_failure_count",
        "lamp_on_time_total",
        "lamp_operating_hours",
        "lamp_wattage_rated",
        "last_diagnostic_code",
        "max_level",
        "min_level",
        "physical_min_level",
        "scene_0_7",
        "scene_8_15",
    }

    # Standard data sources and their SLI targets (seconds)
    _STANDARD_SOURCES: ClassVar[dict[str, int]] = {
        "bms_telemetry": 300,
        "anomalies": 300,
        "documents": 7200,
        "recommendations": 900,
    }

    async def run_freshness_cycle(self) -> dict[str, dict[str, FreshnessResult]]:
        """Run one complete freshness check cycle across all sites and sources.

        Returns:
            {site_id: {data_source: FreshnessResult}}
        """
        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()
        results: dict[str, dict[str, FreshnessResult]] = {}

        try:
            # Get all unique sites registered in data_freshness table
            sites_result = supabase.table("data_freshness").select("site_id").execute()
            sites = set(row["site_id"] for row in sites_result.data)

            # Also discover sites from active bridge adapters — handles sites that
            # haven't been seeded into data_freshness yet (new site deployments).
            adapter_result = supabase.table("site_adapter_config").select("site_id").eq("enabled", True).execute()
            for row in adapter_result.data or []:
                if row.get("site_id"):
                    sites.add(row["site_id"])

            # Finally include all registered site codes. This keeps freshness
            # coverage from depending on a pre-existing data_freshness row or
            # adapter registration timing during onboarding.
            all_sites_result = supabase.table("sites").select("code").execute()
            for row in all_sites_result.data or []:
                if row.get("code"):
                    sites.add(row["code"])

            if not sites:
                logger.warning("Freshness cycle: no sites found in data_freshness, bridge adapters, or sites")
                return {}

            sites = sorted(sites)

            logger.debug(f"Freshness cycle: {len(sites)} sites → {sites}")

            for site_id in sites:
                results[site_id] = {}
                try:
                    results[site_id] = await self._check_site_freshness(supabase, site_id)
                except Exception as e:
                    logger.exception(f"Freshness check failed for {site_id}: {e}")

            logger.info(f"✓ Freshness cycle complete: {len(sites)} sites checked")
            return results

        except Exception as e:
            logger.error(f"Freshness monitor cycle failed: {e}", exc_info=True)
            return {}

    async def _check_site_freshness(self, supabase, site_id: str) -> dict[str, FreshnessResult]:
        """Check all data sources at one site; update age and SLI in DB."""
        freshness_rows = supabase.table("data_freshness").select("*").eq("site_id", site_id).execute()

        results: dict[str, FreshnessResult] = {}
        now = datetime.now(UTC)

        # Fetch the latest sync time from log_sources to derive current freshness.
        # Shadow bridge polling upserts log_sources on every poll cycle, so this
        # reflects actual bridge activity even though data_freshness.last_updated
        # is never written by the bridge itself.
        log_sources = (
            supabase.table("log_sources")
            .select("last_sync_at")
            .like("name", f"%{self._site_code(site_id)}%")
            .eq("is_active", True)
            .order("last_sync_at", desc=True)
            .limit(1)
            .execute()
        )
        latest_sync = log_sources.data[0]["last_sync_at"] if log_sources.data and log_sources.data[0] else None
        latest_sync_dt = datetime.fromisoformat(latest_sync.replace("Z", "+00:00")) if latest_sync else None

        # Seed standard sources if no rows exist for this site but bridge has polled.
        # This handles first-run: monitor discovers bridge has polled but data_freshness
        # has no rows yet, so we create them with the correct sync time as baseline.
        if not freshness_rows.data and latest_sync_dt is not None:
            for data_source, sli_target in self._STANDARD_SOURCES.items():
                supabase.table("data_freshness").insert(
                    {
                        "site_id": site_id,
                        "data_source": data_source,
                        "sli_target_seconds": sli_target,
                        "last_updated": latest_sync_dt.isoformat(),
                        "age_seconds": int((now - latest_sync_dt).total_seconds()),
                        "sli_pass": True,
                        "updated_at": now.isoformat(),
                    }
                ).execute()
            freshness_rows = supabase.table("data_freshness").select("*").eq("site_id", site_id).execute()
            logger.info(f"Seeded data_freshness for {site_id} with {len(self._STANDARD_SOURCES)} sources")

        for row in freshness_rows.data:
            data_source = row["data_source"]
            if data_source == self._TELEMETRY_STREAM_SOURCE:
                continue

            last_updated_str = row["last_updated"]
            sli_target = row["sli_target_seconds"]

            # Derive age from log_sources (actual bridge sync time) when available.
            # Fall back to data_freshness.last_updated when log_sources has no entry.
            if latest_sync_dt is not None:
                effective_last_updated = latest_sync_dt
            elif last_updated_str:
                effective_last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
            else:
                effective_last_updated = None

            if effective_last_updated is not None:
                age_seconds = int((now - effective_last_updated).total_seconds())
            else:
                age_seconds = None

            # Determine SLI pass/fail
            sli_pass = age_seconds is not None and age_seconds <= sli_target

            # Sync SLI target from code in case it changed since seeding
            code_target = self._STANDARD_SOURCES.get(data_source)
            if code_target is not None and code_target != sli_target:
                sli_target = code_target

            # Update age, SLI, and derived last_updated in data_freshness so the
            # column stays current even when the bridge bypasses it directly.
            update_payload = {
                "age_seconds": age_seconds,
                "sli_pass": sli_pass,
                "sli_target_seconds": sli_target,
                "updated_at": now.isoformat(),
            }
            if effective_last_updated is not None:
                update_payload["last_updated"] = effective_last_updated.isoformat()
            supabase.table("data_freshness").update(update_payload).eq("site_id", site_id).eq(
                "data_source", data_source
            ).execute()

            result = FreshnessResult(
                site_id=site_id,
                data_source=data_source,
                age_seconds=age_seconds,
                target_seconds=sli_target,
                sli_pass=sli_pass,
            )

            # Handle breach transitions
            breach_result = await self._handle_breach_logic(
                supabase, site_id, data_source, age_seconds, sli_target, sli_pass
            )
            result.breach_started = breach_result["breach_started"]
            result.breach_resolved = breach_result["breach_resolved"]
            result.breach_duration_seconds = breach_result.get("breach_duration_seconds")

            results[data_source] = result

            # Log transitions
            if breach_result["breach_started"]:
                logger.warning(f"⚠️ Freshness BREACH: {data_source}@{site_id} ({age_seconds}s > {sli_target}s target)")
            elif breach_result["breach_resolved"]:
                logger.info(
                    f"✅ Freshness resolved: {data_source}@{site_id} "
                    f"(was stale for {breach_result['breach_duration_seconds']}s)"
                )

        telemetry_result = await self._check_telemetry_stream_freshness(supabase, site_id, now)
        if telemetry_result is not None:
            results[self._TELEMETRY_STREAM_SOURCE] = telemetry_result

        return results

    async def _check_telemetry_stream_freshness(self, supabase, site_id: str, now: datetime) -> FreshnessResult | None:
        """Check every telemetry stream and every equipment record for freshness.

        The standard `bms_telemetry` source only proves the bridge is syncing.
        It can stay green while individual FCUs, VAVs, meters, or aliases are
        stale. This grouped stream check is the operator-facing guardrail: if
        any telemetry stream or equipment record is stale/missing, the site has
        a freshness breach and SENTRY gets one grouped message after the normal
        auto-recovery window.
        """
        try:
            snapshot = self._load_telemetry_stream_snapshot(site_id, now)
        except Exception as exc:
            logger.exception("[FRESHNESS] Telemetry stream freshness failed for %s: %s", site_id, exc)
            return None

        if snapshot is None:
            return None

        target = self._TELEMETRY_STREAM_TARGET_SECONDS
        stale_streams = snapshot.get("stale_streams", [])
        missing_equipment = snapshot.get("missing_equipment", [])
        missing_streams = snapshot.get("missing_streams", [])
        stale_stream_count = int(snapshot.get("stale_stream_count", len(stale_streams)) or 0)
        missing_equipment_count = int(snapshot.get("missing_equipment_count", len(missing_equipment)) or 0)
        missing_stream_count = int(snapshot.get("missing_stream_count", len(missing_streams)) or 0)
        max_age_seconds = snapshot.get("max_age_seconds")
        oldest_latest = snapshot.get("oldest_latest")
        sli_pass = stale_stream_count == 0 and missing_stream_count == 0 and missing_equipment_count == 0
        age_seconds = int(max_age_seconds) if max_age_seconds is not None else (target + 1 if not sli_pass else 0)

        details = {
            "target_seconds": target,
            "stream_count": snapshot.get("stream_count", 0),
            "equipment_count": snapshot.get("equipment_count", 0),
            "stale_stream_count": stale_stream_count,
            "missing_stream_count": missing_stream_count,
            "missing_equipment_count": missing_equipment_count,
            "stale_stream_samples": stale_streams[: self._TELEMETRY_STREAM_SAMPLE_LIMIT],
            "missing_stream_samples": missing_streams[: self._TELEMETRY_STREAM_SAMPLE_LIMIT],
            "missing_equipment_samples": missing_equipment[: self._TELEMETRY_STREAM_SAMPLE_LIMIT],
        }

        update_payload = {
            "site_id": site_id,
            "data_source": self._TELEMETRY_STREAM_SOURCE,
            "last_updated": oldest_latest.isoformat() if oldest_latest else None,
            "age_seconds": age_seconds,
            "sli_target_seconds": target,
            "sli_pass": sli_pass,
            "updated_at": now.isoformat(),
        }
        supabase.table("data_freshness").upsert(update_payload, on_conflict="site_id,data_source").execute()

        breach_result = await self._handle_breach_logic(
            supabase,
            site_id,
            self._TELEMETRY_STREAM_SOURCE,
            age_seconds,
            target,
            sli_pass,
            details=details,
            severity="high" if not sli_pass else "medium",
        )

        if breach_result["breach_started"]:
            logger.warning(
                "[FRESHNESS] Telemetry stream breach for %s: %d stale streams, %d missing mapped streams, %d missing equipment",
                site_id,
                details["stale_stream_count"],
                details["missing_stream_count"],
                details["missing_equipment_count"],
            )
        elif breach_result["breach_resolved"]:
            logger.info("[FRESHNESS] Telemetry stream freshness recovered for %s", site_id)

        return FreshnessResult(
            site_id=site_id,
            data_source=self._TELEMETRY_STREAM_SOURCE,
            age_seconds=age_seconds,
            target_seconds=target,
            sli_pass=sli_pass,
            breach_started=breach_result["breach_started"],
            breach_resolved=breach_result["breach_resolved"],
            breach_duration_seconds=breach_result.get("breach_duration_seconds"),
        )

    def _load_telemetry_stream_snapshot(self, site_id: str, now: datetime) -> dict[str, Any] | None:
        """Return stale stream and missing-equipment samples using direct SQL aggregation."""
        import psycopg2
        import psycopg2.extras

        database_url = self._database_url()
        if not database_url:
            logger.warning(
                "[FRESHNESS] DATABASE_URL not configured; telemetry stream freshness skipped for %s", site_id
            )
            return None

        target = self._TELEMETRY_STREAM_TARGET_SECONDS
        sql = """
            with site_row as (
                select id, code
                from public.sites
                where code = %(site_id)s
                   or id::text = %(site_id)s
                limit 1
            ),
            equipment_rows as (
                select
                    e.code,
                    e.type,
                    e.status,
                    e.location,
                    e.zone_key,
                    e.canonical_zone_id,
                    e.canonicalization_status,
                    e.canonicalization_source,
                    s.code as site_code
                from public.equipment e
                join site_row s on e.site_id = s.id
            ),
            site_scoped_equipment_rows as (
                select e.*
                from equipment_rows e
                where coalesce(e.status, '') not in ('decommissioned', 'out_of_scope')
                  and coalesce(e.canonicalization_status, '') <> 'out_of_scope'
                  and coalesce(e.canonicalization_source, '') <> 'site_scope_excluded_l3'
                  and not (
                      e.site_code = 'site-002'
                      and (
                          coalesce(e.canonical_zone_id, '') ~ '^Zone-3[0-9]{2}$'
                          or coalesce(e.location, '') ~* '(^|[^A-Za-z0-9])L3([^A-Za-z0-9]|$)|Level[[:space:]]*3'
                          or e.code ~ '^S002-(FCU|VAV|DALI|LUM)-3[0-9]{2}$'
                          or e.code ~ '^S002-LTG(-G)?-0?3[0-9]{2}$'
                          or e.code ~ '^S002-ZONE-L3-'
                      )
                  )
            ),
            zone_inventory as (
                select z.zone_id
                from public.zones z
                join site_row s on z.site_id = s.id
                where z.zone_id is not null
                  and not (s.code = 'site-002' and z.zone_id ~ '^Zone-3[0-9]{2}$')
                union
                select hz.zone_id
                from public.hvac_zones hz
                join site_row s on hz.site_id = s.id
                where hz.zone_id is not null
                  and not (s.code = 'site-002' and hz.zone_id ~ '^Zone-3[0-9]{2}$')
            ),
            valid_zone_ids as (
                select zone_id
                from zone_inventory
                union
                select
                    'Zone-'
                    || substring(zone_id from '^Zone-L([0-9]+)-[0-9]+$')
                    || lpad(substring(zone_id from '^Zone-L[0-9]+-([0-9]+)$'), 2, '0') as zone_id
                from zone_inventory
                where zone_id ~ '^Zone-L[0-9]+-[0-9]+$'
            ),
            freshness_equipment_rows as (
                select e.*
                from site_scoped_equipment_rows e
                where not (
                    e.code ~ ('^' || upper(replace(e.site_code, 'site-', 'S')) || '-(FCU|VAV|DALI|LTG|LUM)-[0-9]{3}$')
                    and not exists (
                        select 1
                        from valid_zone_ids vz
                        where vz.zone_id = 'Zone-' || substring(e.code from '([0-9]{3})$')
                    )
                )
            ),
            raw_latest_streams as (
                select equipment_id, sensor_type, max(recorded_at) as latest
                from public.equipment_sensor_readings
                where site_id in (
                    %(site_id)s,
                    (select code from site_row),
                    (select id::text from site_row)
                )
                group by equipment_id, sensor_type
            ),
            raw_active_streams as (
                select
                    r.equipment_id,
                    r.sensor_type,
                    r.latest,
                    e.type,
                    e.status
                from raw_latest_streams r
                join freshness_equipment_rows e on e.code = r.equipment_id
                where not (r.sensor_type = any(%(derived_sensor_types)s::text[]))
            ),
            mapped_streams as (
                select distinct
                    pam.extracted_asset_id as equipment_id,
                    case
                        when upper(pam.bms_point_id) like '%%ROOMTEMP%%' then 'room_temp'
                        when upper(pam.bms_point_id) like '%%DAMPER%%' then 'damper_position'
                        when upper(pam.bms_point_id) like '%%RUN_STATE%%' then 'equipment_online'
                        when upper(pam.bms_point_id) like '%%FAN_SPEED%%' then 'fan_speed'
                        when upper(pam.bms_point_id) like '%%FILTER_DP%%' then 'filter_dp'
                        when upper(pam.bms_point_id) like '%%SUPPLY_AIR_TEMP%%' then 'supply_air_temp'
                        when upper(pam.bms_point_id) like '%%RETURN_AIR_TEMP%%' then 'return_air_temp'
                        when trim(coalesce(pam.parameter_name, '')) = 'room_temperature' then 'room_temp'
                        when trim(coalesce(pam.parameter_name, '')) = 'zone_temperature' then 'zone_temp'
                        when trim(coalesce(pam.parameter_name, '')) in ('fan_speed_hz', 'fan_current') then 'fan_speed'
                        when trim(coalesce(pam.parameter_name, '')) = 'outlet_water_temp_c' then 'outlet_water_temp'
                        when trim(coalesce(pam.parameter_name, '')) = 'temperature_setpoint' then 'setpoint_temp'
                        when trim(coalesce(pam.parameter_name, '')) = 'comp_current' then 'compressor_current_1'
                        else nullif(trim(coalesce(pam.parameter_name, '')), '')
                    end as sensor_type
                from public.point_asset_mappings pam
                join site_row s on pam.site_id = s.id
                join freshness_equipment_rows e on e.code = pam.extracted_asset_id
                where pam.mapping_source in (
                    'bridge_objects',
                    'simbiot_manual'
                )
                  and coalesce(pam.is_verified, false) = true
                  and pam.bms_point_id !~* '(health_score|updated_at)'
                  and coalesce(pam.parameter_type, '') !~* '^config:'
                  and coalesce(pam.parameter_type, '') !~* '^command:'
                  and coalesce(pam.parameter_type, '') !~* '^control:'
                  and coalesce(pam.parameter_type, '') !~* '^writable:'
                  and coalesce(pam.parameter_type, '') !~* 'characterString'
                  and not (
                      trim(coalesce(pam.parameter_name, '')) = 'status'
                      and pam.bms_point_id ~* '\\.status$'
                  )
            ),
            expected_streams as (
                select equipment_id, sensor_type
                from mapped_streams
                where sensor_type is not null
                  and sensor_type not in ('unknown', 'unknown_sensor')
                  and not (sensor_type = any(%(derived_sensor_types)s::text[]))
                  and not (sensor_type = any(%(non_freshness_sensor_types)s::text[]))
                union
                select equipment_id, sensor_type
                from raw_active_streams
                where latest >= (%(now)s::timestamptz - (%(target)s || ' seconds')::interval)
            ),
            expected_equipment as (
                select distinct equipment_id
                from expected_streams
            ),
            stream_latest as (
                select
                    es.equipment_id,
                    es.sensor_type,
                    max(ras.latest) as latest
                from expected_streams es
                left join raw_active_streams ras
                    on ras.equipment_id = es.equipment_id
                   and (
                       ras.sensor_type = es.sensor_type
                       or (
                           es.equipment_id = 'S002-DALI-101'
                           and (
                               (es.sensor_type = 'lux' and ras.sensor_type = 'A_Lux')
                               or (es.sensor_type = 'occupancy' and ras.sensor_type = 'A_Occupancy')
                           )
                       )
                       or (
                           es.equipment_id = 'S002-DALI-202'
                           and (
                               (es.sensor_type = 'lux' and ras.sensor_type = 'B_Lux')
                               or (es.sensor_type = 'occupancy' and ras.sensor_type = 'B_Occupancy')
                           )
                       )
                   )
                group by es.equipment_id, es.sensor_type
            ),
            latest_streams as (
                select
                    sl.equipment_id,
                    sl.sensor_type,
                    sl.latest,
                    e.type,
                    e.status
                from stream_latest sl
                join freshness_equipment_rows e on e.code = sl.equipment_id
            ),
            latest_equipment as (
                select equipment_id, max(latest) as latest
                from raw_active_streams
                group by equipment_id
            )
            select
                (select count(*) from latest_streams) as stream_count,
                (select count(*) from freshness_equipment_rows) as equipment_count,
                (select max(extract(epoch from (%(now)s::timestamptz - latest))) from latest_streams) as max_age_seconds,
                (select min(latest) from latest_streams) as oldest_latest,
                (
                    select count(*)
                    from latest_streams
                    where latest < (%(now)s::timestamptz - (%(target)s || ' seconds')::interval)
                ) as stale_stream_count,
                (
                    select count(*)
                    from latest_streams
                    where latest is null
                ) as missing_stream_count,
                coalesce(
                    (
                        select jsonb_agg(row_to_json(x) order by x.age_seconds desc)
                        from (
                            select
                                equipment_id,
                                sensor_type,
                                type,
                                status,
                                latest,
                                extract(epoch from (%(now)s::timestamptz - latest))::int as age_seconds
                            from latest_streams
                            where latest < (%(now)s::timestamptz - (%(target)s || ' seconds')::interval)
                            order by age_seconds desc, equipment_id, sensor_type
                            limit %(sample_limit)s
                        ) x
                    ),
                    '[]'::jsonb
                ) as stale_streams,
                coalesce(
                    (
                        select jsonb_agg(row_to_json(x) order by x.equipment_id, x.sensor_type)
                        from (
                            select
                                equipment_id,
                                sensor_type,
                                type,
                                status
                            from latest_streams
                            where latest is null
                            order by equipment_id, sensor_type
                            limit %(sample_limit)s
                        ) x
                    ),
                    '[]'::jsonb
                ) as missing_streams,
                (
                    select count(*)
                    from expected_equipment ee
                    join freshness_equipment_rows e on e.code = ee.equipment_id
                    left join latest_equipment le on le.equipment_id = e.code
                    where le.latest is null
                ) as missing_equipment_count,
                coalesce(
                    (
                        select jsonb_agg(row_to_json(x) order by x.code)
                        from (
                            select e.code, e.type, e.status
                            from expected_equipment ee
                            join freshness_equipment_rows e on e.code = ee.equipment_id
                            left join latest_equipment le on le.equipment_id = e.code
                            where le.latest is null
                            order by e.type, e.code
                            limit %(sample_limit)s
                        ) x
                    ),
                    '[]'::jsonb
                ) as missing_equipment
        """
        params = {
            "site_id": site_id,
            "now": now.isoformat(),
            "target": target,
            "sample_limit": self._TELEMETRY_STREAM_SAMPLE_LIMIT,
            "derived_sensor_types": list(self._DERIVED_TELEMETRY_SENSOR_TYPES),
            "non_freshness_sensor_types": list(self._NON_FRESHNESS_SENSOR_TYPES),
        }
        with psycopg2.connect(database_url) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()

        if not row:
            return None

        oldest_latest = row.get("oldest_latest")
        if isinstance(oldest_latest, str):
            oldest_latest = datetime.fromisoformat(oldest_latest.replace("Z", "+00:00"))

        return {
            "stream_count": int(row.get("stream_count") or 0),
            "equipment_count": int(row.get("equipment_count") or 0),
            "max_age_seconds": int(row["max_age_seconds"]) if row.get("max_age_seconds") is not None else None,
            "oldest_latest": oldest_latest,
            "stale_stream_count": int(row.get("stale_stream_count") or 0),
            "missing_stream_count": int(row.get("missing_stream_count") or 0),
            "missing_equipment_count": int(row.get("missing_equipment_count") or 0),
            "stale_streams": list(row.get("stale_streams") or []),
            "missing_streams": list(row.get("missing_streams") or []),
            "missing_equipment": list(row.get("missing_equipment") or []),
        }

    def _database_url(self) -> str:
        return (
            settings.database_url
            or os.getenv("DATABASE_URL")
            or os.getenv("DATABASE_URL_DIRECT")
            or "postgresql://postgres:postgres@127.0.0.1:55322/postgres"
        )

    async def _handle_breach_logic(
        self,
        supabase,
        site_id: str,
        data_source: str,
        age_seconds: int | None,
        target: int,
        sli_pass: bool,
        details: dict[str, Any] | None = None,
        severity: str = "medium",
    ) -> dict[str, Any]:
        """Detect new breaches and resolve active ones.

        Alert policy:
        - Auto-recovery window: 10 minutes (600s)
        - Only alert if breach persists beyond auto-recovery window (unrecoverable)
        - Alert once per breach via Sentry Telegram bot to manager
        """
        # Check for active (unresolved) breach
        active_breach_result = (
            supabase.table("data_freshness_breaches")
            .select("id, breach_time, alert_sent")
            .eq("site_id", site_id)
            .eq("data_source", data_source)
            .is_("resolved_at", None)
            .order("breach_time", desc=True)
            .limit(1)
            .execute()
        )

        active_breach = active_breach_result.data
        now = datetime.now(UTC)
        AUTO_RECOVERY_WINDOW_SECONDS = 600  # 10 minutes

        if sli_pass and active_breach:
            # Breach is resolved
            breach_id = active_breach[0]["id"]
            raw_breach_time = active_breach[0].get("breach_time")
            if raw_breach_time:
                breach_time = datetime.fromisoformat(raw_breach_time.replace("Z", "+00:00"))
                duration = int((now - breach_time).total_seconds())
            else:
                breach_time = now
                duration = 0

            supabase.table("data_freshness_breaches").update(
                {"resolved_at": now.isoformat(), "duration_seconds": duration}
            ).eq("id", breach_id).execute()

            # Send recovery notification if alert was previously sent
            if active_breach[0].get("alert_sent"):
                await self._send_recovery_notification(site_id, data_source, duration)

            return {"breach_started": False, "breach_resolved": True, "breach_duration_seconds": duration}

        elif not sli_pass and not active_breach:
            # New breach detected
            supabase.table("data_freshness_breaches").insert(
                {
                    "site_id": site_id,
                    "metric_name": data_source,
                    "breach_type": "data_freshness",
                    "severity": severity,
                    "detected_at": now.isoformat(),
                    "breach_time": now.isoformat(),
                    "data_source": data_source,
                    "age_seconds": age_seconds,
                    "sli_target": target,
                    "alert_sent": False,
                    "details": details or {},
                }
            ).execute()

            # Don't alert immediately - wait for auto-recovery window
            logger.info(
                f"[FRESHNESS] Breach started for {data_source}@{site_id} - "
                f"waiting {AUTO_RECOVERY_WINDOW_SECONDS}s auto-recovery window before alerting"
            )

            return {"breach_started": True, "breach_resolved": False}

        elif not sli_pass and active_breach:
            # Ongoing breach — check if we've exceeded auto-recovery window
            raw_breach_time = active_breach[0].get("breach_time")
            if raw_breach_time:
                breach_time = datetime.fromisoformat(raw_breach_time.replace("Z", "+00:00"))
                breach_duration = int((now - breach_time).total_seconds())
            else:
                breach_time = now
                breach_duration = 0
            alert_sent = active_breach[0].get("alert_sent", False)
            supabase.table("data_freshness_breaches").update(
                {
                    "age_seconds": age_seconds,
                    "sli_target": target,
                    "severity": severity,
                    "details": details or {},
                }
            ).eq("id", active_breach[0]["id"]).execute()

            # Alert only if:
            # 1. Breach has persisted beyond auto-recovery window
            # 2. Alert hasn't been sent yet for this breach
            if (
                breach_duration > AUTO_RECOVERY_WINDOW_SECONDS
                and not alert_sent
                and data_source in self._CRITICAL_SOURCES
            ):
                alert_sent = await self._send_unrecoverable_alert(
                    site_id,
                    data_source,
                    age_seconds,
                    target,
                    breach_duration,
                    details=details,
                )

                if alert_sent:
                    supabase.table("data_freshness_breaches").update({"alert_sent": True}).eq(
                        "id", active_breach[0]["id"]
                    ).execute()

            return {"breach_started": False, "breach_resolved": False}

        # No breach state change
        return {"breach_started": False, "breach_resolved": False}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _site_code(site_id: str) -> str:
        """Convert S002 → 'site-002', leave 'site-002' unchanged."""
        if site_id.startswith("site-"):
            return site_id
        if site_id.startswith("S") and len(site_id) == 4:
            return f"site-{site_id[1:]}"  # S002[1:] = '002' → site-002
        return site_id

    async def _send_unrecoverable_alert(
        self,
        site_id: str,
        data_source: str,
        age_seconds: int | None,
        target: int,
        breach_duration: int,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """Send a grouped SENTRY Telegram alert for unrecovered freshness breaches."""
        message = self._format_unrecoverable_alert(site_id, data_source, age_seconds, target, breach_duration, details)
        return await self._send_freshness_telegram(site_id, message, severity="high")

    async def _send_recovery_notification(self, site_id: str, data_source: str, duration_seconds: int) -> None:
        """Send a SENTRY Telegram recovery notice after a previously-alerted breach recovers."""
        message = (
            "SENTINEL Data Freshness Recovered\n"
            f"Site: {site_id}\n"
            f"Source: {data_source}\n"
            f"Stale duration: {self._format_duration(duration_seconds)}"
        )
        await self._send_freshness_telegram(site_id, message, severity="info")

    async def _send_freshness_telegram(self, site_id: str, message: str, severity: str) -> bool:
        from app.services.telegram_message_sender import TelegramMessageSender

        bot_token = settings.sentry_manager_bot_token or settings.telegram_bot_token
        chat_id = self._resolve_site_manager_chat_id(site_id)

        result: dict[str, Any] | None = None
        error_message = None
        if not bot_token or not chat_id:
            error_message = "Missing Telegram bot token or active site manager chat id"
            self._fallback_log(site_id, "telegram", None, 0, error_message)
        else:
            try:
                result = await TelegramMessageSender(bot_token).send_text(str(chat_id), message, parse_mode=None)
                if not result.get("ok"):
                    error_message = str(result)
                    self._fallback_log(site_id, "telegram", None, 0, error_message)
            except Exception as exc:
                error_message = str(exc)
                self._fallback_log(site_id, "telegram", None, 0, error_message)

        try:
            from app.database.supabase_client import get_supabase_client

            telegram_message_id = None
            if result and result.get("ok"):
                telegram_message_id = (result.get("result") or {}).get("message_id")

            get_supabase_client().table("notification_delivery_log").insert(
                {
                    "id": str(uuid.uuid4()),
                    "notification_type": "data_freshness",
                    "channel_type": "telegram",
                    "recipient_identifier": str(chat_id or ""),
                    "status": "sent" if result and result.get("ok") else "failed",
                    "provider": "telegram",
                    "sent_at": datetime.now(UTC).isoformat() if result and result.get("ok") else None,
                    "error_message": error_message,
                    "created_at": datetime.now(UTC).isoformat(),
                    "site_id": site_id,
                    "message_text": message,
                    "delivery_status": "sent" if result and result.get("ok") else "failed",
                    "telegram_message_id": telegram_message_id,
                    "severity": severity,
                    "reference_type": "data_freshness",
                }
            ).execute()
        except Exception as exc:
            logger.warning("[FRESHNESS] Failed to write notification_delivery_log: %s", exc)
            return False

        return bool(result and result.get("ok"))

    def _resolve_site_manager_chat_id(self, site_id: str) -> str:
        """Return the active manager Telegram chat for this site only.

        Freshness alerts are operational site messages. They must not fall back
        to a global manager chat because that can leak Site 005 issues to a
        Site 002 manager. If no same-site manager is configured, the delivery is
        logged as failed and the breach remains unsent for retry after config is
        fixed.
        """
        try:
            from app.database.supabase_client import get_supabase_client

            result = (
                get_supabase_client()
                .table("bot_users")
                .select("telegram_id")
                .eq("site_id", site_id)
                .eq("bot_role", "manager")
                .eq("active", True)
                .order("created_at", desc=False)
                .limit(1)
                .execute()
            )
            if result.data and result.data[0].get("telegram_id"):
                return str(result.data[0]["telegram_id"])
        except Exception as exc:
            logger.warning("[FRESHNESS] Failed to resolve site manager chat for %s: %s", site_id, exc)
        return ""

    def _format_unrecoverable_alert(
        self,
        site_id: str,
        data_source: str,
        age_seconds: int | None,
        target: int,
        breach_duration: int,
        details: dict[str, Any] | None,
    ) -> str:
        lines = [
            "SENTINEL Data Freshness Alert",
            f"Site: {site_id}",
            f"Source: {data_source}",
            f"Age: {self._format_duration(age_seconds)}",
            f"Target: {self._format_duration(target)}",
            f"Breach duration: {self._format_duration(breach_duration)}",
        ]
        if details and data_source == self._TELEMETRY_STREAM_SOURCE:
            lines.extend(
                [
                    "",
                    f"Telemetry streams checked: {details.get('stream_count', 0)}",
                    f"Stale streams: {details.get('stale_stream_count', 0)}",
                    f"Mapped streams with no telemetry: {details.get('missing_stream_count', 0)}",
                    f"Equipment with no telemetry: {details.get('missing_equipment_count', 0)}",
                ]
            )
            stale_samples = details.get("stale_stream_samples") or []
            if stale_samples:
                lines.append("")
                lines.append("Oldest stale streams:")
                for item in stale_samples[:5]:
                    equipment_context = " ".join(part for part in [item.get("type"), item.get("status")] if part)
                    equipment_context = f" ({equipment_context})" if equipment_context else ""
                    lines.append(
                        "- "
                        f"{item.get('equipment_id')}.{item.get('sensor_type')} "
                        f"age {self._format_duration(item.get('age_seconds'))}{equipment_context}"
                    )
            missing_stream_samples = details.get("missing_stream_samples") or []
            if missing_stream_samples:
                lines.append("")
                lines.append("Mapped streams with no telemetry:")
                for item in missing_stream_samples[:5]:
                    equipment_context = " ".join(part for part in [item.get("type"), item.get("status")] if part)
                    equipment_context = f" ({equipment_context})" if equipment_context else ""
                    lines.append(f"- {item.get('equipment_id')}.{item.get('sensor_type')}{equipment_context}")
            missing_samples = details.get("missing_equipment_samples") or []
            if missing_samples:
                lines.append("")
                lines.append("No telemetry examples:")
                for item in missing_samples[:5]:
                    equipment_context = " ".join(part for part in [item.get("type"), item.get("status")] if part)
                    equipment_context = equipment_context or "unknown"
                    lines.append(f"- {item.get('code')} ({equipment_context})")
        return "\n".join(lines)

    @staticmethod
    def _format_duration(seconds: int | float | None) -> str:
        if seconds is None:
            return "unknown"
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes / 60
        if hours < 48:
            return f"{hours:.1f}h"
        return f"{hours / 24:.1f}d"

    def _fallback_log(self, site_id: str, data_source: str, age_seconds: int | None, target: int, error: Any) -> None:
        """Write failed alert to fallback file for manual recovery."""
        import json
        from pathlib import Path

        fallback_path = Path("/tmp/sentinel_freshness_alert_fallback.json")
        entry = {
            "site_id": site_id,
            "data_source": data_source,
            "age_seconds": age_seconds,
            "target": target,
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            existing = []
            if fallback_path.exists():
                existing = json.loads(fallback_path.read_text())
            existing.append(entry)
            fallback_path.write_text(json.dumps(existing, indent=2))
            logger.info(f"[FRESHNESS] Alert written to fallback file: {fallback_path}")
        except Exception as e:
            logger.error(f"[FRESHNESS] Failed to write fallback log: {e}")
