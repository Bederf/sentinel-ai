"""
Health Snapshot Service — persistence, retrieval, and recompute for health ratings.

Phase 109B: Health Assessment Timeline

Stores HealthRating snapshots in asset_health_snapshots (Supabase) and
aggregates daily rollups. Provides a recompute job that can process
single equipment, a site, or all equipment.

When Supabase is unavailable, stores snapshots in-memory
so tests and local/offline operation work without a database.

HARD RULE: Only writes health_score and health_status.
NEVER writes risk probabilities.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.models.health_rating import (
    DailyRollup,
    HealthRating,
    RecomputeResult,
)

logger = logging.getLogger(__name__)


class HealthSnapshotService:
    """Service for storing and retrieving health rating snapshots.

    Supports Supabase persistence with in-memory fallback for local/offline mode.
    """

    def __init__(self):
        """Initialize with lazy Supabase access and in-memory fallback."""
        self._supabase = None
        self._use_memory = False

        # In-memory fallback storage (keyed by equipment_id)
        self._memory_snapshots: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._memory_rollups: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

        self._init_supabase()

    def _init_supabase(self):
        """Try to connect to Supabase; fall back to in-memory on failure."""
        try:
            from app.database.supabase_client import get_supabase_client

            self._supabase = get_supabase_client()
            # Quick check that the table exists
            self._supabase.table("asset_health_snapshots").select("id").limit(0).execute()
            logger.debug("HealthSnapshotService: Supabase connection OK")
        except Exception as e:
            logger.info(f"HealthSnapshotService: using in-memory fallback ({e})")
            self._supabase = None
            self._use_memory = True

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def store_snapshot(
        self,
        rating: HealthRating,
        site_id: str | None = None,
    ) -> str:
        """Store a health rating snapshot.

        Also updates the equipment table's health_score.

        Args:
            rating: The computed HealthRating.
            site_id: Optional building UUID for the index.

        Returns:
            Snapshot ID (UUID string).
        """
        snapshot_data = {
            "equipment_id": rating.equipment_id,
            "site_id": site_id,
            "snapshot_at": rating.snapshot_at,
            "health_score": rating.health_score,
            "health_status": rating.health_status,
            "assessment_state": rating.assessment_state,
            "confidence": rating.confidence,
            "baseline_alignment_score": (rating.components.baseline_alignment_score),
            "service_compliance_score": (rating.components.service_compliance_score),
            "runtime_age_score": rating.components.runtime_age_score,
            "fault_burden_score": rating.components.fault_burden_score,
            "trend_momentum_score": rating.components.trend_momentum_score,
            "data_freshness_minutes": rating.data_quality.freshness_minutes,
            "snapshot_count_24h": rating.data_quality.snapshot_count_24h,
            "valid_point_ratio": rating.data_quality.valid_point_ratio,
            "baseline_age_days": rating.data_quality.baseline_age_days,
            "health_source": "calculator",
            "formula_version": rating.formula_version,
        }

        if self._use_memory:
            return self._store_memory(snapshot_data)

        return await self._store_supabase(snapshot_data, rating, site_id)

    # ------------------------------------------------------------------
    # UUID resolution helpers
    # ------------------------------------------------------------------

    def _resolve_uuid(self, code_or_uuid: str) -> str | None:
        """Resolve equipment code or UUID to a UUID string.

        If input looks like a UUID, return it directly.
        Otherwise look up by code and return the equipment's UUID.
        Returns None if resolution fails.
        """
        # Fast path: already a UUID
        try:
            from app.database.repositories.equipment_repository import (
                EquipmentRepository,
            )

            repo = EquipmentRepository()
            if repo._is_uuid(code_or_uuid):
                return code_or_uuid
        except Exception:
            pass

        # Slow path: resolve code → UUID
        try:
            from app.database.repositories.equipment_repository import (
                EquipmentRepository,
            )

            repo = EquipmentRepository()
            eq = repo.get_by_id(code_or_uuid)
            if eq and eq.get("id"):
                return eq["id"]
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def _store_memory(self, snapshot_data: dict) -> str:
        """Store snapshot in memory (test/local fallback)."""
        import uuid

        snapshot_id = str(uuid.uuid4())
        snapshot_data["id"] = snapshot_id
        snapshot_data["created_at"] = datetime.utcnow().isoformat() + "Z"

        equipment_id = snapshot_data["equipment_id"]
        self._memory_snapshots[equipment_id].append(snapshot_data)

        logger.debug(f"Stored in-memory snapshot {snapshot_id} for {equipment_id}")
        return snapshot_id

    async def _store_supabase(self, snapshot_data: dict, rating: HealthRating, site_id: str | None = None) -> str:
        """Store snapshot in Supabase and update equipment health_score."""
        # Resolve equipment UUID before any DB operation
        eq_uuid = self._resolve_uuid(rating.equipment_id)
        if eq_uuid is None:
            logger.debug("Could not resolve UUID for %s — storing in memory", rating.equipment_id)
            return self._store_memory(snapshot_data)
        snapshot_data = dict(snapshot_data)
        snapshot_data["equipment_id"] = eq_uuid

        try:
            result = self._supabase.table("asset_health_snapshots").insert(snapshot_data).execute()
            snapshot_id = result.data[0]["id"] if result.data else "unknown"

            # Update equipment.health_score AND status — sync derived status from health_status
            # Status mapping: healthy→normal, warning→warning, critical→critical
            health_status = rating.health_status  # "healthy", "warning", or "critical"
            equip_status = "normal" if health_status == "healthy" else health_status
            try:
                self._supabase.table("equipment").update(
                    {
                        "health_score": int(rating.health_score),
                        "status": equip_status,
                        "updated_at": datetime.utcnow().isoformat() + "Z",
                    }
                ).eq("id", eq_uuid).execute()

                # Create alert when equipment status is warning or critical
                if health_status in ("warning", "critical"):
                    eq_code = rating.equipment_id
                    eq_name = eq_code

                    # Check if there's already an active alert for this equipment
                    existing = self._supabase.table("alerts").select("id").eq(
                        "equipment_id", eq_uuid
                    ).neq("status", "resolved").limit(1).execute()

                    if not existing.data:
                        alert_severity = "critical" if health_status == "critical" else "warning"
                        self._supabase.table("alerts").insert({
                            "site_id": site_id,
                            "equipment_id": eq_uuid,
                            "type": "health",
                            "title": f"{eq_name} health is {health_status}",
                            "message": f"Equipment health score {int(rating.health_score)} is in '{health_status}' range.",
                            "severity": alert_severity,
                            "status": "active",
                        }).execute()
                        logger.info("Alert created: %s health=%d status=%s", eq_code, int(rating.health_score), health_status)

            except Exception as e:
                logger.warning(f"Could not update equipment health_score for {eq_uuid}: {e}")

            return snapshot_id

        except Exception as e:
            logger.error(f"Supabase store failed, falling back to memory: {e}")
            return self._store_memory(snapshot_data)

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    async def get_latest(self, equipment_id: str) -> HealthRating | None:
        """Get the most recent snapshot for an equipment item.

        Args:
            equipment_id: Equipment code or UUID.

        Returns:
            HealthRating or None if no snapshots exist.
        """
        if self._use_memory:
            snapshots = self._memory_snapshots.get(equipment_id, [])
            if not snapshots:
                return None
            latest = max(snapshots, key=lambda s: s.get("snapshot_at", ""))
            return self._snapshot_to_rating(latest)

        # Resolve code → UUID before querying asset_health_snapshots
        eq_uuid = self._resolve_uuid(equipment_id)
        if eq_uuid is None:
            logger.debug("Could not resolve UUID for %s — no latest snapshot", equipment_id)
            return None

        try:
            result = (
                self._supabase.table("asset_health_snapshots")
                .select("*")
                .eq("equipment_id", eq_uuid)
                .order("snapshot_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return self._snapshot_to_rating(result.data[0])
        except Exception as e:
            logger.debug(f"Failed to get latest snapshot for {equipment_id}: {e}")

        return None

    async def get_history(
        self,
        equipment_id: str,
        range_days: int = 7,
    ) -> list[HealthRating]:
        """Get snapshots within the given range.

        Args:
            equipment_id: Equipment code or UUID.
            range_days: Number of days of history to retrieve.

        Returns:
            List of HealthRating sorted newest-first.
        """
        cutoff = (datetime.utcnow() - timedelta(days=range_days)).isoformat() + "Z"

        if self._use_memory:
            snapshots = self._memory_snapshots.get(equipment_id, [])
            filtered = [s for s in snapshots if s.get("snapshot_at", "") >= cutoff]
            filtered.sort(key=lambda s: s.get("snapshot_at", ""), reverse=True)
            return [self._snapshot_to_rating(s) for s in filtered]

        # Resolve code → UUID before querying asset_health_snapshots
        eq_uuid = self._resolve_uuid(equipment_id)
        if eq_uuid is None:
            logger.debug("Could not resolve UUID for %s — no snapshot history", equipment_id)
            return []

        try:
            result = (
                self._supabase.table("asset_health_snapshots")
                .select("*")
                .eq("equipment_id", eq_uuid)
                .gte("snapshot_at", cutoff)
                .order("snapshot_at", desc=True)
                .execute()
            )
            return [self._snapshot_to_rating(s) for s in (result.data or [])]
        except Exception as e:
            logger.debug(f"Failed to get snapshot history for {equipment_id}: {e}")
            return []

    async def get_daily_rollups(
        self,
        equipment_id: str,
        range_days: int = 30,
    ) -> list[DailyRollup]:
        """Get daily rollups for an equipment item.

        If rollups are missing in Supabase, computes them from snapshots.

        Args:
            equipment_id: Equipment code or UUID.
            range_days: Number of days.

        Returns:
            List of DailyRollup sorted newest-first.
        """
        if self._use_memory:
            rollups = self._memory_rollups.get(equipment_id, {})
            cutoff = (datetime.utcnow() - timedelta(days=range_days)).strftime("%Y-%m-%d")
            filtered = {k: v for k, v in rollups.items() if k >= cutoff}
            return [DailyRollup(**v) for v in sorted(filtered.values(), key=lambda r: r["date"], reverse=True)]

        eq_uuid = self._resolve_uuid(equipment_id)
        if eq_uuid is None:
            logger.debug("Could not resolve UUID for %s — no daily rollups", equipment_id)
            return []

        try:
            cutoff = (datetime.utcnow() - timedelta(days=range_days)).strftime("%Y-%m-%d")
            result = (
                self._supabase.table("asset_health_daily_rollups")
                .select("*")
                .eq("equipment_id", eq_uuid)
                .gte("date", cutoff)
                .order("date", desc=True)
                .execute()
            )
            return [
                DailyRollup(
                    date=r["date"],
                    score_min=r.get("score_min"),
                    score_max=r.get("score_max"),
                    score_avg=r.get("score_avg"),
                    status_mode=r.get("status_mode"),
                    confidence_mode=r.get("confidence_mode"),
                    snapshot_count=r.get("snapshot_count", 0),
                )
                for r in (result.data or [])
            ]
        except Exception as e:
            logger.error(f"Failed to get daily rollups: {e}")
            return []

    # ------------------------------------------------------------------
    # Daily Rollup Update
    # ------------------------------------------------------------------

    async def update_daily_rollup(
        self,
        equipment_id: str,
        date: str,
    ) -> None:
        """Compute and upsert a daily rollup from the day's snapshots.

        Args:
            equipment_id: Equipment code or UUID.
            date: Date string in YYYY-MM-DD format.
        """
        if self._use_memory:
            self._update_memory_rollup(equipment_id, date)
            return

        # Resolve equipment code → UUID before querying snapshots
        eq_uuid = self._resolve_uuid(equipment_id)
        if eq_uuid is None:
            logger.debug("Could not resolve UUID for %s — skipping daily rollup", equipment_id)
            return

        try:
            # Get all snapshots for the day
            start = f"{date}T00:00:00Z"
            end = f"{date}T23:59:59Z"
            result = (
                self._supabase.table("asset_health_snapshots")
                .select("health_score, health_status, confidence")
                .eq("equipment_id", eq_uuid)
                .gte("snapshot_at", start)
                .lte("snapshot_at", end)
                .execute()
            )

            snapshots = result.data or []
            if not snapshots:
                return

            scores = [s["health_score"] for s in snapshots]
            statuses = [s["health_status"] for s in snapshots]
            confidences = [s["confidence"] for s in snapshots]

            rollup_data = {
                "equipment_id": eq_uuid,
                "date": date,
                "score_min": min(scores),
                "score_max": max(scores),
                "score_avg": round(sum(scores) / len(scores), 1),
                "status_mode": max(set(statuses), key=statuses.count),
                "confidence_mode": max(set(confidences), key=confidences.count),
                "snapshot_count": len(snapshots),
            }

            self._supabase.table("asset_health_daily_rollups").upsert(
                rollup_data,
                on_conflict="equipment_id,date",
            ).execute()

        except Exception as e:
            logger.error(f"Failed to update daily rollup: {e}")

    def _update_memory_rollup(self, equipment_id: str, date: str) -> None:
        """Update daily rollup from in-memory snapshots."""
        snapshots = self._memory_snapshots.get(equipment_id, [])
        day_snapshots = [s for s in snapshots if s.get("snapshot_at", "").startswith(date)]

        if not day_snapshots:
            return

        scores = [s["health_score"] for s in day_snapshots]
        statuses = [s["health_status"] for s in day_snapshots]
        confidences = [s["confidence"] for s in day_snapshots]

        self._memory_rollups[equipment_id][date] = {
            "date": date,
            "score_min": min(scores),
            "score_max": max(scores),
            "score_avg": round(sum(scores) / len(scores), 1),
            "status_mode": max(set(statuses), key=statuses.count),
            "confidence_mode": max(set(confidences), key=confidences.count),
            "snapshot_count": len(day_snapshots),
        }

    # ------------------------------------------------------------------
    # Recompute
    # ------------------------------------------------------------------

    async def recompute(
        self,
        scope: str,
        equipment_id: str | None = None,
        site_id: str | None = None,
    ) -> RecomputeResult:
        """Recompute health ratings for the given scope.

        HARD RULE: Only writes health_score and health_status.
        NEVER writes risk probabilities.

        Args:
            scope: 'single', 'site', or 'all'.
            equipment_id: Required for scope='single'.
            site_id: Required for scope='site'.

        Returns:
            RecomputeResult with counts and duration.
        """
        from app.services.health_rating_calculator import HealthRatingCalculator

        calculator = HealthRatingCalculator()
        start_ms = int(time.time() * 1000)

        equipment_list = await self._get_equipment_list(scope, equipment_id, site_id)

        processed = 0
        failed = 0
        mode = self._resolve_mode()

        for equip in equipment_list:
            eq_type = equip.get("type", "")
            eq_code = equip.get("code", "?")

            # Gate: check if equipment type is scoreable
            from app.config.health_config import get_scoreability
            score_cfg = get_scoreability(eq_type)
            if not score_cfg.get("scoreable", False):
                logger.debug(f"[HEALTH-SNAP] Skipping {eq_code} ({eq_type}): {score_cfg.get('reason', 'not scoreable')}")
                continue

            # Skip synthetic fallback types (VAV/FCU) — static placeholder until real service data
            if score_cfg.get("method") == "synthetic_fallback":
                logger.debug(f"[HEALTH-SNAP] Skipping {eq_code} ({eq_type}): synthetic fallback (no service data)")
                continue

            # Skip if no baseline
            if equip.get("health_score") is None:
                logger.debug(f"[HEALTH-SNAP] Skipping {eq_code} ({eq_type}): no baseline")
                continue

            try:
                eq_id = equip.get("code") or equip.get("id", "")
                rating = await calculator.compute_rating(
                    equipment_id=eq_id,
                    equipment=equip,
                    mode=mode,
                )
                site_id = equip.get("site_id")
                await self.store_snapshot(rating, site_id=site_id)

                # Update daily rollup for today
                today = datetime.utcnow().strftime("%Y-%m-%d")
                await self.update_daily_rollup(eq_id, today)

                processed += 1
            except Exception as e:
                logger.error(f"Failed to recompute for {equip.get('code', '?')}: {e}")
                failed += 1

        duration_ms = int(time.time() * 1000) - start_ms

        # Audit log
        try:
            from app.services.audit_logger import AuditLogger

            audit = AuditLogger()
            await audit.log(
                action="health_assessment_recompute",
                resource_type="equipment",
                resource_id=equipment_id or site_id or "all",
                details={
                    "scope": scope,
                    "processed": processed,
                    "failed": failed,
                    "duration_ms": duration_ms,
                },
            )
        except Exception as e:
            logger.debug(f"Audit log skipped: {e}")

        return RecomputeResult(
            scope=scope,
            equipment_processed=processed,
            equipment_failed=failed,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_equipment_list(
        self,
        scope: str,
        equipment_id: str | None,
        site_id: str | None,
    ) -> list[dict[str, Any]]:
        """Get equipment list based on scope."""
        if scope == "single" and equipment_id:
            return [await self._get_single_equipment(equipment_id)]

        try:
            from app.database.repositories.equipment_repository import (
                EquipmentRepository,
            )

            repo = EquipmentRepository()
            if scope == "site" and site_id:
                # Resolve site code → UUID before querying equipment
                resolved = self._resolve_uuid(site_id)
                return repo.get_all(site_id=resolved)
            return repo.get_all()
        except Exception as e:
            logger.error(f"Could not get equipment list: {e}")
            return []

    async def _get_single_equipment(self, equipment_id: str) -> dict[str, Any]:
        """Get a single equipment item by ID or code.

        Tries code lookup first, then UUID lookup if code lookup returns None.
        """
        try:
            from app.database.repositories.equipment_repository import (
                EquipmentRepository,
            )

            repo = EquipmentRepository()
            # Try code first (get_by_id queries equipment.code)
            equip = repo.get_by_id(equipment_id)
            if equip:
                return equip
            # Fall back to UUID lookup (get_by_uuid queries equipment.id)
            equip = repo.get_by_uuid(equipment_id)
            if equip:
                return equip
        except Exception:
            pass
        # Last resort: resolve UUID but return minimal dict
        uuid_resolved = self._resolve_uuid(equipment_id)
        return {"id": uuid_resolved, "code": equipment_id}

    def _resolve_mode(self) -> str:
        """Resolve the current ingestion mode string."""
        try:
            from app.config.settings import settings

            # Check for resolved_ingestion_mode attribute
            if hasattr(settings, "resolved_ingestion_mode"):
                mode = settings.resolved_ingestion_mode
                if hasattr(mode, "value"):
                    return mode.value.lower()
                return str(mode).lower()
        except Exception:
            pass
        return "simulation"

    @staticmethod
    def _snapshot_to_rating(snapshot: dict) -> HealthRating:
        """Convert a snapshot dict to a HealthRating model."""
        from app.models.health_rating import (
            HealthComponentBreakdown,
            HealthDataQualityResult,
        )

        components = HealthComponentBreakdown(
            baseline_alignment_score=snapshot.get("baseline_alignment_score"),
            service_compliance_score=snapshot.get("service_compliance_score"),
            runtime_age_score=snapshot.get("runtime_age_score"),
            fault_burden_score=snapshot.get("fault_burden_score"),
            trend_momentum_score=snapshot.get("trend_momentum_score"),
        )

        data_quality = HealthDataQualityResult(
            freshness_minutes=snapshot.get("data_freshness_minutes", 0),
            snapshot_count_24h=snapshot.get("snapshot_count_24h", 0),
            valid_point_ratio=snapshot.get("valid_point_ratio", 1.0),
            baseline_age_days=snapshot.get("baseline_age_days", 0),
            gates_passed=snapshot.get("gates_passed", 4),
            gates_total=snapshot.get("gates_total", 4),
            confidence=snapshot.get("confidence", "high"),
            assessment_state=snapshot.get("assessment_state", "normal"),
        )

        return HealthRating(
            equipment_id=snapshot.get("equipment_id", ""),
            health_score=float(snapshot.get("health_score", 0)),
            health_status=snapshot.get("health_status", "critical"),
            confidence=snapshot.get("confidence", "high"),
            assessment_state=snapshot.get("assessment_state", "normal"),
            components=components,
            data_quality=data_quality,
            formula_version=snapshot.get("formula_version", "v1"),
            snapshot_at=snapshot.get("snapshot_at", ""),
        )
