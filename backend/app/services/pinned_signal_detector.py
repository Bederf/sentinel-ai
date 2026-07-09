"""Phase 236-02: pinned-signal integrity detection.

Catches the telemetry failure class neither Phase 231 (gate-rejected
impossible values) nor Phase 232 (cross-signal contradictions) covers:
signals that are individually plausible but frozen — bridge defaults,
saturated sensors, dead point mappings. Live S002 examples (2026-07-05
audit): valve_position pinned at exactly 48 for 7 days, supply_air_pressure
at 420 on two AHUs, every point on S002-CHILLER-B1-002 single-valued for
28 days.

Two window tiers over telemetry_hourly (long retention — the 10-day raw
readings retention cannot truncate the window):
  - structural_7d: signal shows almost no variation across a full week
  - frozen_24h:    signal normally varies (7d history proves it) but the
                   last day of hourly buckets is hard-frozen (per-bucket
                   min == max), i.e. the feed started repeating one value

Findings are advisory recommendations (action_type=data_integrity) with
the same dedup/observation/pending-clear semantics as the reflex
reconciliation advisories. Verdicts persist in pinned_signal_state so
downstream inference (FCU running derivation) can treat pinned inputs as
unavailable — per-site, verdict-driven, never hardcoded site knowledge.
Cold start fails open: no verdict row means the signal is trusted until
the first detector cycle.
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config.settings import settings
from app.models.recommendation import ActionRiskLevel, Recommendation, RecommendationStatus

logger = logging.getLogger(__name__)

LONG_WINDOW_HOURS = 168
SHORT_WINDOW_HOURS = 24
MIN_LONG_HOURS = 48  # minimum bucket coverage before judging the 7d window
MIN_SHORT_FROZEN_BUCKETS = 18  # of the last 24 hourly buckets
MIN_DISTINCT_LONG = 2  # fewer distinct rounded hourly means than this (i.e. == 1) → pinned.
# Deliberately 2, not 3: a genuine 2-state signal (status/run 0↔1) has distinct=2 and a
# ~100% relative range, so it is caught by NEITHER branch and correctly not flagged.
# Truly-frozen (distinct=1) still fires; near-constant tight bands fire via RELATIVE_RANGE_PINNED.
RELATIVE_RANGE_PINNED = 0.01  # (max-min)/max(|mean|,1) below 1% over 7d → pinned
VARIES_NORMALLY_DISTINCT = 10  # 7d history needed before frozen_24h may fire
REJECTION_MAJORITY = 0.5  # skip points majority-rejected by the quality gate (Phase 231 territory)
CLEAR_DEBOUNCE_HOURS = 8.0  # one clear cycle stamps, a later cycle past this resolves
VERDICT_CACHE_TTL_SECONDS = 900.0
VERDICT_STALE_HOURS = 18.0  # verdicts not refreshed within this window are ignored (job runs every 6h)
SYSTEMIC_PINNED_RATIO = 0.5  # majority of evaluated points pinned → one site-level finding
SYSTEMIC_MIN_POINTS = 20  # don't call "systemic" on tiny sites

_EXCLUSIONS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "pinned_signal_exclusions.json")


@dataclass
class PinnedVerdict:
    equipment_id: str
    point_name: str
    pinned: bool
    window_kind: str | None = None
    pinned_value: float | None = None
    distinct_values: int | None = None
    relative_range: float | None = None
    hours_evaluated: int | None = None


def evaluate_point(
    *,
    long_hours: int,
    long_distinct: int,
    long_vmin: float,
    long_vmax: float,
    long_vmean: float,
    short_distinct: int,
    short_bucket_count: int,
    short_value: float | None,
) -> PinnedVerdict | None:
    """Pure verdict logic for one (equipment, point). Returns None when the
    point cannot be judged (insufficient coverage).

    ``short_distinct`` is the count of distinct rounded hourly means in the
    last-24h window — a genuine freeze repeats ONE value, whereas a merely
    low-cadence point (one sample per hour) still changes value hour to hour.
    """
    if long_hours < MIN_LONG_HOURS:
        return None

    rel_range = (long_vmax - long_vmin) / max(abs(long_vmean), 1.0)

    # structural_7d: near-zero variation across the week. A constant-zero
    # signal is excluded — that reads as "equipment off" (a knowable state
    # the running inference must keep), not a stuck feed; a dead-at-zero point
    # is Phase 232 cross-signal territory, not a distinct-count finding.
    if (long_distinct < MIN_DISTINCT_LONG or rel_range < RELATIVE_RANGE_PINNED) and abs(long_vmean) > 1e-9:
        return PinnedVerdict(
            equipment_id="",
            point_name="",
            pinned=True,
            window_kind="structural_7d",
            pinned_value=long_vmean,
            distinct_values=long_distinct,
            relative_range=round(rel_range, 6),
            hours_evaluated=long_hours,
        )

    # frozen_24h: signals whose week of history proves they normally vary but
    # whose last day collapsed to a single repeated value. Keyed on the
    # short-window DISTINCT count (== 1), not per-bucket min==max, so a
    # low-cadence-but-changing point is not misread as frozen. Nonzero only
    # (zero constant = off, not stuck).
    if (
        long_distinct >= VARIES_NORMALLY_DISTINCT
        and short_bucket_count >= MIN_SHORT_FROZEN_BUCKETS
        and short_distinct <= 1
        and short_value is not None
        and abs(short_value) > 1e-9
    ):
        return PinnedVerdict(
            equipment_id="",
            point_name="",
            pinned=True,
            window_kind="frozen_24h",
            pinned_value=short_value,
            distinct_values=long_distinct,
            relative_range=round(rel_range, 6),
            hours_evaluated=short_bucket_count,
        )

    return PinnedVerdict(
        equipment_id="",
        point_name="",
        pinned=False,
        distinct_values=long_distinct,
        relative_range=round(rel_range, 6),
        hours_evaluated=long_hours,
    )


class PinnedSignalExclusions:
    """Config-driven exclusion list for constant-by-design points."""

    def __init__(self, path: str = _EXCLUSIONS_PATH):
        self._path = path
        self._points: set[str] = set()
        self._suffixes: tuple[str, ...] = ()
        self._site_overrides: dict[str, dict[str, list[str]]] = {}
        self._load()

    def _load(self) -> None:
        import json

        try:
            with open(self._path) as f:
                cfg = json.load(f)
            self._points = {str(p) for p in cfg.get("global_excluded_points", [])}
            self._suffixes = tuple(str(s) for s in cfg.get("global_excluded_suffixes", []))
            self._site_overrides = cfg.get("site_overrides", {}) or {}
        except Exception as e:
            logger.warning("[PINNED] Could not load exclusions config (%s) — using empty exclusions", e)

    def is_excluded(self, site_id: str, point_name: str) -> bool:
        if point_name in self._points:
            return True
        if any(point_name.endswith(sfx) for sfx in self._suffixes):
            return True
        site_cfg = self._site_overrides.get(site_id) or {}
        if point_name in set(site_cfg.get("excluded_points", [])):
            return True
        return any(point_name.endswith(sfx) for sfx in site_cfg.get("excluded_suffixes", []))


class PinnedSignalDetector:
    """Scheduler-cadence detector: evaluate, persist verdicts, manage findings."""

    SOURCE = "pinned_signal_detector"
    ACTION_TYPE = "data_integrity"

    def __init__(self, database_url: str | None = None):
        # Same DSN pattern as SupabaseRetentionService — never bare
        # os.getenv("DATABASE_URL") in APScheduler context.
        self._db_url = database_url or os.environ.get("DATABASE_URL_DIRECT") or settings.database_url
        self.exclusions = PinnedSignalExclusions()
        self._verdict_cache: dict[str, tuple[float, set[tuple[str, str]]]] = {}

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def _db_connect(self):
        import psycopg2

        return psycopg2.connect(self._db_url)

    def _fetch_window_stats(self, site_id: str) -> tuple[list[tuple], list[tuple]]:
        """Long-window aggregate stats + short-window frozen-bucket stats."""
        conn = self._db_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT equipment_id, point_name, count(*),
                           count(DISTINCT round(value_avg, 2)),
                           min(value_min), max(value_max), avg(value_avg)
                    FROM telemetry_hourly
                    WHERE site_id = %s AND hour_bucket > now() - make_interval(hours => %s)
                      AND value_avg IS NOT NULL AND value_min IS NOT NULL AND value_max IS NOT NULL
                    GROUP BY 1, 2
                    """,
                    (site_id, LONG_WINDOW_HOURS),
                )
                long_rows = cur.fetchall()
                cur.execute(
                    """
                    SELECT equipment_id, point_name,
                           count(DISTINCT round(value_avg, 2)),
                           count(*),
                           max(value_avg)
                    FROM telemetry_hourly
                    WHERE site_id = %s AND hour_bucket > now() - make_interval(hours => %s)
                      AND value_avg IS NOT NULL
                    GROUP BY 1, 2
                    """,
                    (site_id, SHORT_WINDOW_HOURS),
                )
                short_rows = cur.fetchall()
        finally:
            conn.close()
        return long_rows, short_rows

    def _fetch_rejection_ratios(self, site_id: str) -> dict[tuple[str, str], float]:
        """Points majority-rejected by the quality gate stay Phase 231 territory."""
        conn = self._db_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT er.equipment_id, er.sensor_type,
                           count(*) FILTER (WHERE er.quality_flag = 'rejected')::float / count(*)
                    FROM equipment_sensor_readings er
                    WHERE er.site_id = %s AND er.recorded_at > now() - interval '24 hours'
                    GROUP BY 1, 2
                    """,
                    (site_id,),
                )
                return {(str(r[0]), str(r[1])): float(r[2]) for r in cur.fetchall()}
        except Exception as e:
            # Missing quality_flag column or empty table must not stop detection.
            logger.debug("[PINNED] Rejection-ratio query failed for %s: %s", site_id, e)
            return {}
        finally:
            conn.close()

    def evaluate_site(self, site_id: str) -> list[PinnedVerdict]:
        long_rows, short_rows = self._fetch_window_stats(site_id)
        short_by_point = {
            (str(r[0]), str(r[1])): (int(r[2]), int(r[3]), float(r[4]) if r[4] is not None else None)
            for r in short_rows
        }
        rejection_ratios = self._fetch_rejection_ratios(site_id)

        verdicts: list[PinnedVerdict] = []
        for equipment_id, point_name, hrs, distinct, vmin, vmax, vmean in long_rows:
            equipment_id, point_name = str(equipment_id), str(point_name)
            if self.exclusions.is_excluded(site_id, point_name):
                continue
            if rejection_ratios.get((equipment_id, point_name), 0.0) > REJECTION_MAJORITY:
                continue  # gate-rejected streak — Phase 231's finding, not ours
            short_distinct, buckets, short_val = short_by_point.get((equipment_id, point_name), (0, 0, None))
            verdict = evaluate_point(
                long_hours=int(hrs),
                long_distinct=int(distinct),
                long_vmin=float(vmin),
                long_vmax=float(vmax),
                long_vmean=float(vmean),
                short_distinct=short_distinct,
                short_bucket_count=buckets,
                short_value=short_val,
            )
            if verdict is None:
                continue
            verdict.equipment_id = equipment_id
            verdict.point_name = point_name
            verdicts.append(verdict)
        return verdicts

    # ------------------------------------------------------------------
    # Verdict persistence + downstream availability
    # ------------------------------------------------------------------

    async def persist_verdicts(self, site_id: str, verdicts: list[PinnedVerdict]) -> int:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        now = datetime.now(UTC).isoformat()
        existing = (
            await client.table("pinned_signal_state")
            .select("equipment_id, point_name, pinned, pinned_since")
            .eq("site_id", site_id)
            .execute()
        )
        prior = {(str(r["equipment_id"]), str(r["point_name"])): r for r in existing.data or []}

        written = 0
        for v in verdicts:
            key = (v.equipment_id, v.point_name)
            prior_row = prior.get(key)
            pinned_since = None
            if v.pinned:
                pinned_since = (prior_row or {}).get("pinned_since") if (prior_row or {}).get("pinned") else None
                pinned_since = pinned_since or now
            payload = {
                "site_id": site_id,
                "equipment_id": v.equipment_id,
                "point_name": v.point_name,
                "pinned": v.pinned,
                "window_kind": v.window_kind,
                "pinned_value": v.pinned_value,
                "distinct_values": v.distinct_values,
                "relative_range": v.relative_range,
                "hours_evaluated": v.hours_evaluated,
                "pinned_since": pinned_since,
                "last_evaluated_at": now,
                "updated_at": now,
            }
            await (
                client.table("pinned_signal_state")
                .upsert(payload, on_conflict="site_id,equipment_id,point_name")
                .execute()
            )
            written += 1
        self._verdict_cache.pop(site_id, None)
        return written

    async def get_pinned_points(self, site_id: str) -> set[tuple[str, str]]:
        """Currently-pinned (equipment_id, point_name) pairs for a site.

        Cold start fails open: an empty/missing verdict set means signals are
        trusted until the first detector cycle. Cached in-process (15 min) so
        the shadow-polling hot path costs one query per cycle at most.

        Only STALE-free verdicts count: a point that loses coverage is skipped
        by evaluate_site (never re-persisted), so its old pinned row would
        otherwise linger forever. We ignore verdicts not refreshed within
        VERDICT_STALE_HOURS (well over the 6h job interval), so a decayed
        verdict fails open rather than pinning a signal indefinitely.
        """
        cached = self._verdict_cache.get(site_id)
        if cached and (time.monotonic() - cached[0]) < VERDICT_CACHE_TTL_SECONDS:
            return cached[1]
        try:
            from app.database.supabase_client import get_async_supabase_client

            client = await get_async_supabase_client()
            stale_cutoff = (datetime.now(UTC) - timedelta(hours=VERDICT_STALE_HOURS)).isoformat()
            result = (
                await client.table("pinned_signal_state")
                .select("equipment_id, point_name")
                .eq("site_id", site_id)
                .eq("pinned", True)
                .gte("last_evaluated_at", stale_cutoff)
                .execute()
            )
            pinned = {(str(r["equipment_id"]), str(r["point_name"])) for r in result.data or []}
        except Exception as e:
            logger.debug("[PINNED] Verdict fetch failed for %s (fail-open): %s", site_id, e)
            pinned = set()
        self._verdict_cache[site_id] = (time.monotonic(), pinned)
        return pinned

    # ------------------------------------------------------------------
    # Findings (recommendations) — reflex-advisory semantics
    #
    # Granularity: one finding per EQUIPMENT (metadata lists its pinned
    # points), rolled up to a single SITE-level systemic finding when the
    # majority of a site's points are pinned (live S002 case 2026-07-06:
    # 529/619 points frozen since ~June 22 — that is one bridge/feed
    # incident, not 529 sensor failures, and must read as one finding).
    # ------------------------------------------------------------------

    async def _list_active_findings(self, site_id: str) -> list[dict[str, Any]]:
        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        result = (
            await client.table("recommendations")
            .select("*")
            .eq("site_id", site_id)
            .eq("source", self.SOURCE)
            .in_("status", ["pending", "advisory_info"])
            .limit(1000)
            .execute()
        )
        return result.data or []

    @staticmethod
    def _finding_key(row: dict[str, Any]) -> tuple[str, str]:
        metadata = row.get("metadata") or {}
        return (str(row.get("target_equipment") or ""), str(metadata.get("scope") or ""))

    @staticmethod
    def _site_target(site_id: str) -> str:
        # Logical target, same convention as SITE-002-HVAC-ZONE-SCOPE.
        return f"{site_id.upper()}-TELEMETRY-INTEGRITY"

    def build_finding_units(self, site_id: str, verdicts: list[PinnedVerdict]) -> list[dict[str, Any]]:
        """Group verdicts into finding units: site-systemic or per-equipment."""
        pinned = [v for v in verdicts if v.pinned]
        if not pinned:
            return []

        def _points_payload(items: list[PinnedVerdict]) -> list[dict[str, Any]]:
            return [
                {
                    "point_name": v.point_name,
                    "window_kind": v.window_kind,
                    "pinned_value": v.pinned_value,
                    "distinct_values": v.distinct_values,
                }
                for v in sorted(items, key=lambda x: x.point_name)
            ]

        ratio = len(pinned) / max(len(verdicts), 1)
        if len(pinned) >= SYSTEMIC_MIN_POINTS and ratio > SYSTEMIC_PINNED_RATIO:
            equipment_affected = sorted({v.equipment_id for v in pinned})
            sample = _points_payload(pinned[:40])
            return [
                {
                    "key": (self._site_target(site_id), "site"),
                    "target_equipment": self._site_target(site_id),
                    "scope": "site",
                    "risk": ActionRiskLevel.HIGH,
                    "rule_key": "data_integrity.pinned_signal.site_systemic",
                    "reason": (
                        f"Systemic frozen telemetry on {site_id}: {len(pinned)} of {len(verdicts)} "
                        f"evaluated points ({ratio:.0%}) show no real variation across "
                        f"{len(equipment_affected)} equipment. This pattern indicates a "
                        "bridge/BMS export feed fault (defaults or stale cache), not individual "
                        "sensor failures. Verify the bridge connection and BMS point export "
                        "before trusting plant telemetry. Downstream inference treats these "
                        "signals as unavailable."
                    ),
                    "metadata_patch": {
                        "scope": "site",
                        "pinned_count": len(pinned),
                        "evaluated_count": len(verdicts),
                        "pinned_ratio": round(ratio, 3),
                        "equipment_affected": equipment_affected,
                        "sample_points": sample,
                    },
                }
            ]

        units: list[dict[str, Any]] = []
        by_equipment: dict[str, list[PinnedVerdict]] = {}
        for v in pinned:
            by_equipment.setdefault(v.equipment_id, []).append(v)
        for equipment_id, items in sorted(by_equipment.items()):
            names = ", ".join(v.point_name for v in sorted(items, key=lambda x: x.point_name)[:6])
            more = f" (+{len(items) - 6} more)" if len(items) > 6 else ""
            units.append(
                {
                    "key": (equipment_id, "equipment"),
                    "target_equipment": equipment_id,
                    "scope": "equipment",
                    "risk": ActionRiskLevel.MEDIUM,
                    "rule_key": "data_integrity.pinned_signal.equipment",
                    "reason": (
                        f"Pinned signals on {equipment_id}: {names}{more} pass quality gates but "
                        "show no real variation. A frozen feed usually means a bridge default, "
                        "dead point mapping, or saturated sensor. Verify the point mapping in "
                        "the BMS/bridge; downstream inference treats these signals as "
                        "unavailable until variance returns."
                    ),
                    "metadata_patch": {
                        "scope": "equipment",
                        "pinned_points": _points_payload(items),
                        "pinned_count": len(items),
                    },
                }
            )
        return units

    async def reconcile_findings(self, site_id: str, verdicts: list[PinnedVerdict]) -> dict[str, int]:
        """Create/update finding units; debounce-resolve cleared ones."""
        from app.database.repositories.recommendation_repository import get_recommendation_repository
        from app.database.supabase_client import get_async_supabase_client

        now = datetime.now(UTC)
        client = await get_async_supabase_client()
        active = await self._list_active_findings(site_id)
        active_by_key = {self._finding_key(row): row for row in active}
        units = {unit["key"]: unit for unit in self.build_finding_units(site_id, verdicts)}

        stats = {"created": 0, "updated": 0, "pending_clear": 0, "resolved": 0}

        for key, unit in units.items():
            row = active_by_key.get(key)
            if row is None:
                rec = self._build_finding(site_id, unit, now)
                await get_recommendation_repository().create(rec)
                stats["created"] += 1
                continue
            metadata = dict(row.get("metadata") or {})
            metadata.pop("pending_clear_since", None)  # re-observed — abort clear
            metadata.update(unit["metadata_patch"])
            metadata.update(
                {
                    "last_observed_at": now.isoformat(),
                    "observation_count": int(metadata.get("observation_count") or 1) + 1,
                }
            )
            await (
                client.table("recommendations")
                .update({"metadata": metadata, "reason": unit["reason"]})
                .eq("id", row["id"])
                .execute()
            )
            stats["updated"] += 1

        # Cleared: active finding whose unit did not re-form this cycle
        for key, row in active_by_key.items():
            if key in units:
                continue
            metadata = dict(row.get("metadata") or {})
            pending_since = metadata.get("pending_clear_since")
            if not pending_since:
                metadata["pending_clear_since"] = now.isoformat()
                await client.table("recommendations").update({"metadata": metadata}).eq("id", row["id"]).execute()
                stats["pending_clear"] += 1
                continue
            try:
                since = datetime.fromisoformat(str(pending_since))
            except ValueError:
                since = now
            if (now - since).total_seconds() >= CLEAR_DEBOUNCE_HOURS * 3600:
                metadata.update({"resolved_at": now.isoformat(), "resolution_reason": "variance_returned"})
                await (
                    client.table("recommendations")
                    .update({"status": RecommendationStatus.EXPIRED.value, "metadata": metadata})
                    .eq("id", row["id"])
                    .execute()
                )
                stats["resolved"] += 1
        return stats

    def _build_finding(self, site_id: str, unit: dict[str, Any], now: datetime) -> Recommendation:
        metadata = {
            "first_observed_at": now.isoformat(),
            "last_observed_at": now.isoformat(),
            "observation_count": 1,
        }
        metadata.update(unit["metadata_patch"])
        return Recommendation(
            site_id=site_id,
            timestamp=now.replace(tzinfo=None),
            action_type=self.ACTION_TYPE,
            risk_level=unit["risk"],
            target_equipment=unit["target_equipment"],
            action={
                "type": "manual_operator_review",
                "rule_key": unit["rule_key"],
                "auto_actionable": False,
            },
            reason=unit["reason"],
            expected_impact={"category": "data_integrity", "manual_action_required": True},
            confidence="high",
            confidence_score=0.9,
            profile="pinned_signal_detector",
            status=RecommendationStatus.ADVISORY_INFO,
            requires_approval=False,
            source=self.SOURCE,
            source_type="deterministic_rule",
            shadow_mode=False,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def tick(self) -> dict[str, Any]:
        """Daily-cadence entry point: evaluate every processing-enabled site."""
        import asyncio

        from app.database.supabase_client import get_async_supabase_client

        client = await get_async_supabase_client()
        sites = await client.table("sites").select("code").eq("sentinel_processing_enabled", True).execute()
        results: dict[str, Any] = {"sites": 0, "points": 0, "pinned": 0, "findings": {}}
        for row in sites.data or []:
            site_id = str(row["code"])
            try:
                # evaluate_site runs blocking psycopg2 GROUP BY scans — keep them
                # off the event loop so API handlers aren't stalled.
                verdicts = await asyncio.to_thread(self.evaluate_site, site_id)
                await self.persist_verdicts(site_id, verdicts)
                stats = await self.reconcile_findings(site_id, verdicts)
                results["sites"] += 1
                results["points"] += len(verdicts)
                results["pinned"] += sum(1 for v in verdicts if v.pinned)
                results["findings"][site_id] = stats
            except Exception as e:
                logger.error("[PINNED] Site %s evaluation failed: %s", site_id, e)
        logger.info(
            "[PINNED] tick complete: sites=%s points=%s pinned=%s findings=%s",
            results["sites"],
            results["points"],
            results["pinned"],
            results["findings"],
        )
        return results


_detector: PinnedSignalDetector | None = None


def get_pinned_signal_detector() -> PinnedSignalDetector:
    global _detector
    if _detector is None:
        _detector = PinnedSignalDetector()
    return _detector
