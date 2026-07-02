"""Repository for trust history persistence.

Phase 162: Semantic Control Foundation — Plan 04.
Persists trust history for point classifications with Supabase primary
storage and JSON file fallback.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.models.trust_history import TrustHistory

logger = logging.getLogger(__name__)

# JSON fallback directory
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "simbiot" / "trust_history"


class TrustHistoryRepository:
    """Persists and retrieves trust history for points."""

    def __init__(self) -> None:
        self._client = None
        self._use_json = False

    # ------------------------------------------------------------------
    # Supabase client (lazy, falls back to JSON on failure)
    # ------------------------------------------------------------------

    @property
    def client(self):
        """Lazy-load Supabase client; fall back to JSON if unavailable."""
        if self._client is None and not self._use_json:
            try:
                from app.database.supabase_client import get_supabase_client

                self._client = get_supabase_client()
            except Exception as exc:
                logger.warning("Failed to get Supabase client, using JSON fallback: %s", exc)
                self._use_json = True
        return self._client

    # ------------------------------------------------------------------
    # JSON fallback helpers
    # ------------------------------------------------------------------

    def _json_path(self, point_id: str, site_id: str) -> Path:
        key = f"{site_id}__{point_id}".replace("/", "_")
        return DATA_DIR / f"{key}.json"

    def _store_json_fallback(self, trust_history: TrustHistory) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = self._json_path(trust_history.point_id, trust_history.site_id)
        data = trust_history.model_dump(mode="json")
        with path.open("w") as fh:
            json.dump(data, fh, indent=2, default=str)

    def _load_json_fallback(self, point_id: str, site_id: str) -> TrustHistory | None:
        path = self._json_path(point_id, site_id)
        if not path.exists():
            return None
        with path.open() as fh:
            data = json.load(fh)
        return TrustHistory(**data)

    # ------------------------------------------------------------------
    # Public interface (async-compatible via synchronous implementation)
    # ------------------------------------------------------------------

    async def upsert_trust_history(self, trust_history: TrustHistory) -> bool:
        """Insert or update trust history for a point.

        Uses upsert pattern: if point_id+site_id exists, update; otherwise insert.
        Falls back to JSON storage if Supabase is unavailable.
        """
        trust_history.updated_at = datetime.utcnow()

        if not self._use_json and self.client is not None:
            try:
                payload = {
                    "point_id": trust_history.point_id,
                    "site_id": trust_history.site_id,
                    "equipment_id": trust_history.equipment_id or "",
                    "stability_days": trust_history.stability_days,
                    "validation_runs": trust_history.validation_runs,
                    "successful_actions": trust_history.successful_actions,
                    "failed_actions": trust_history.failed_actions,
                    "last_validation_error": (
                        trust_history.last_validation_error.isoformat() if trust_history.last_validation_error else None
                    ),
                    "last_successful_action": (
                        trust_history.last_successful_action.isoformat()
                        if trust_history.last_successful_action
                        else None
                    ),
                    "trust_score": trust_history.trust_score,
                    "updated_at": trust_history.updated_at.isoformat(),
                }
                self.client.table("trust_history").upsert(payload, on_conflict="point_id,site_id").execute()
                return True
            except Exception as exc:
                logger.warning("Supabase upsert failed, falling back to JSON: %s", exc)

        self._store_json_fallback(trust_history)
        return True

    async def get_trust_history(self, point_id: str, site_id: str) -> TrustHistory | None:
        """Retrieve trust history for a point."""
        if not self._use_json and self.client is not None:
            try:
                result = (
                    self.client.table("trust_history")
                    .select("*")
                    .eq("point_id", point_id)
                    .eq("site_id", site_id)
                    .execute()
                )
                if result.data:
                    return TrustHistory(**result.data[0])
            except Exception as exc:
                logger.warning("Supabase read failed, falling back to JSON: %s", exc)

        return self._load_json_fallback(point_id, site_id)

    async def increment_validation_run(self, point_id: str, site_id: str, had_error: bool = False) -> None:
        """Increment validation run counter and update stability days."""
        history = await self.get_trust_history(point_id, site_id)

        if history is None:
            history = TrustHistory(
                point_id=point_id,
                site_id=site_id,
                validation_runs=1,
                stability_days=0 if had_error else 1,
            )
            if had_error:
                history.last_validation_error = datetime.utcnow()
        else:
            history.validation_runs += 1
            if had_error:
                history.stability_days = 0
                history.last_validation_error = datetime.utcnow()
            else:
                history.stability_days += 1

        history.trust_score = TrustHistory.calculate_trust_score(
            history.stability_days,
            history.validation_runs,
            history.successful_actions,
            history.failed_actions,
        )
        await self.upsert_trust_history(history)

    async def record_control_action(
        self,
        point_id: str,
        site_id: str,
        success: bool,
        expected_outcome: dict,
        actual_outcome: dict,
    ) -> None:
        """Record a control action outcome and update trust metrics."""
        history = await self.get_trust_history(point_id, site_id)

        if history is None:
            history = TrustHistory(point_id=point_id, site_id=site_id)

        if success:
            history.successful_actions += 1
            history.last_successful_action = datetime.utcnow()
        else:
            history.failed_actions += 1

        history.trust_score = TrustHistory.calculate_trust_score(
            history.stability_days,
            history.validation_runs,
            history.successful_actions,
            history.failed_actions,
        )
        await self.upsert_trust_history(history)

    # ------------------------------------------------------------------
    # Equipment-level trust reset (PLAN-162B)
    # ------------------------------------------------------------------

    async def find_by_equipment(self, equipment_id: str) -> list[TrustHistory]:
        """Find all trust history rows for a given equipment."""
        if not self._use_json and self.client is not None:
            try:
                result = self.client.table("trust_history").select("*").eq("equipment_id", equipment_id).execute()
                if result.data:
                    return [TrustHistory(**row) for row in result.data]
            except Exception as exc:
                logger.warning("Supabase query by equipment failed: %s", exc)

        if not DATA_DIR.exists():
            return []
        results: list[TrustHistory] = []
        for path in DATA_DIR.iterdir():
            if path.suffix != ".json":
                continue
            try:
                data = json.loads(path.read_text())
                if data.get("equipment_id") == equipment_id:
                    results.append(TrustHistory(**data))
            except Exception:
                continue
        return results

    async def reset_equipment_trust(self, equipment_id: str, *, hard: bool = False) -> int:
        """Reset trust history for all points on an equipment.

        Args:
            equipment_id: Canonical equipment code.
            hard: True for replacement (full zero), False for partial decay.

        Returns:
            Number of trust history rows modified.
        """
        rows = await self.find_by_equipment(equipment_id)
        if not rows:
            return 0

        count = 0
        for row in rows:
            prior = row.model_dump(mode="json")
            if hard:
                row.stability_days = 0
                row.validation_runs = 0
                row.successful_actions = 0
                row.failed_actions = 0
            else:
                row.stability_days = max(0, int(row.stability_days * 0.3))
                row.successful_actions = max(0, row.successful_actions - 3)
                row.validation_runs = max(0, row.validation_runs - 2)
            row.trust_score = TrustHistory.calculate_trust_score(
                row.stability_days,
                row.validation_runs,
                row.successful_actions,
                row.failed_actions,
            )
            await self.upsert_trust_history(row)
            count += 1
            logger.info(
                "[TRUST-RESET] %s equipment=%s point=%s prior_trust_score=%.3f",
                "Hard reset" if hard else "Partial decay",
                equipment_id,
                row.point_id,
                prior.get("trust_score", 0),
            )

        return count

    # ------------------------------------------------------------------
    # Drift-triggered trust decay (PLAN-162B)
    # ------------------------------------------------------------------

    async def decay_by_equipment_type(self, equipment_type: str, features_drifted: int = 0) -> int:
        """Apply trust decay to all equipment matching a type.

        Severity scales with features_drifted:
        - features_drifted <= 1: no decay (noise)
        - features_drifted 2-3: stable_days *= 0.5 (moderate)
        - features_drifted >3 or model drift: stable_days *= 0.1 (severe)
        """
        if features_drifted <= 1:
            return 0

        severe = features_drifted > 3
        eq_pattern = f"%-{equipment_type.upper()}-%"

        if not self._use_json and self.client is not None:
            try:
                result = self.client.table("trust_history").select("*").ilike("equipment_id", eq_pattern).execute()
                rows = [TrustHistory(**row) for row in (result.data or [])]
            except Exception as exc:
                logger.warning("Supabase decay lookup failed: %s", exc)
                rows = []
        else:
            rows = await self._find_by_equipment_type_json(equipment_type.upper())

        return await self._apply_decay_to_rows(rows, severe=severe)

    async def _find_by_equipment_type_json(self, eq_type_upper: str) -> list[TrustHistory]:
        if not DATA_DIR.exists():
            return []
        results: list[TrustHistory] = []
        for path in DATA_DIR.iterdir():
            if path.suffix != ".json":
                continue
            try:
                data = json.loads(path.read_text())
                eq_id = str(data.get("equipment_id", "")).upper()
                if f"-{eq_type_upper}-" in eq_id:
                    results.append(TrustHistory(**data))
            except Exception:
                continue
        return results

    async def _apply_decay_to_rows(self, rows: list[TrustHistory], *, severe: bool) -> int:
        if not rows:
            return 0
        count = 0
        for row in rows:
            prior = row.model_dump(mode="json")
            if severe:
                row.stability_days = max(0, int(row.stability_days * 0.1))
                row.successful_actions = max(0, int(row.successful_actions / 2))
            else:
                row.stability_days = max(0, int(row.stability_days * 0.5))
            row.trust_score = TrustHistory.calculate_trust_score(
                row.stability_days,
                row.validation_runs,
                row.successful_actions,
                row.failed_actions,
            )
            await self.upsert_trust_history(row)
            count += 1
            logger.info(
                "[TRUST-DECAY] %s equipment=%s point=%s prior_trust_score=%.3f",
                "Severe" if severe else "Moderate",
                row.equipment_id,
                row.point_id,
                prior.get("trust_score", 0),
            )
        return count
