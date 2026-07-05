"""PPM (Planned Preventive Maintenance) Scheduler.

Phase B.4: emit auto-WOs for big-equipment items whose last rollup is older
than their cadence. Wired into the daily cadence by background_scheduler.

Cadence resolution per equipment (in order):
  1. equipment.service_interval_days (per-asset override; set on the
     maintenance page by the operator)
  2. health_calculation_config.json[equipment_type].service_interval_days
     (type-level default in days)
  3. 90 days (last-resort fallback if the type config is missing)

Skip conditions:
  - equipment.baseline_state == 'none' (gating policy A — onboarding hasn't
    completed for this asset; the operator must finish onboarding or set a
    manual baseline via the maintenance tab before PPM emission begins)
  - existing open work_orders row with work_type='preventive' for this
    equipment (idempotent — don't double-emit)

Capture path (per-visit):
  1. PPM scheduler emits WO + service_records row linked by work_order_id
  2. Technician bot notifies the technician (Telegram + email) via
     work_order_notifier.notify_technician_with_code
  3. Technician runs /done-WO-XXXX (technician-closeout skill) — supplies
     numeric readings via Phase B.6 Step 8.5 + service_attachments
  4. inspection-result POST succeeds (Phase B.7)
  5. EquipmentBaselineRollupService fires — updates last_rollup_at
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Last-resort cadence when neither per-asset nor per-type is configured.
DEFAULT_SERVICE_INTERVAL_DAYS = 90

# Big-equipment types the PPM scheduler emits WOs for. Restricted to the
# 8 mechanical types already in prediction_generator.MECHANICAL_TYPES so
# we don't poll the operator for weather stations, access control, etc.
BIG_EQUIPMENT_TYPES = frozenset({"ahu", "chiller", "cooling_tower", "fcu", "pump", "vav", "boiler", "generator"})


class PPMScheduler:
    """Daily tick that emits preventive WOs for big equipment whose
    last rollup is older than their cadence."""

    def __init__(self) -> None:
        self._type_cadence_cache: dict[str, int] | None = None

    # ------------------------------------------------------------------
    # Cadence resolution
    # ------------------------------------------------------------------

    def effective_cadence_days(self, equipment: dict[str, Any]) -> int:
        """Resolve the cadence for one equipment item.

        Order: per-asset override (equipment.service_interval_days) →
        type default (health_calculation_config.json) → DEFAULT_SERVICE_INTERVAL_DAYS.
        Clamped to [1, 365] to align with the column CHECK constraint.
        """
        per_asset = equipment.get("service_interval_days")
        if isinstance(per_asset, int) and 1 <= per_asset <= 365:
            return per_asset

        equipment_type = (equipment.get("type") or "").lower()
        per_type = self._type_cadence_days(equipment_type)
        if isinstance(per_type, int) and 1 <= per_type <= 365:
            return per_type

        return DEFAULT_SERVICE_INTERVAL_DAYS

    def _type_cadence_days(self, equipment_type: str) -> int | None:
        """Read per-type default from health_calculation_config.json (cached)."""
        if not equipment_type:
            return None
        if self._type_cadence_cache is None:
            self._type_cadence_cache = self._load_type_cadence()
        return self._type_cadence_cache.get(equipment_type)

    @staticmethod
    def _load_type_cadence() -> dict[str, int]:
        config_path = Path(__file__).parent.parent / "data" / "health_calculation_config.json"
        if not config_path.exists():
            logger.warning(
                "health_calculation_config.json missing at %s — PPM scheduler will use default cadence",
                config_path,
            )
            return {}
        try:
            with open(config_path) as f:
                raw = json.load(f)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", config_path, exc)
            return {}

        cadence: dict[str, int] = {}
        for equipment_type, type_config in raw.items():
            if not isinstance(type_config, dict):
                continue
            days = type_config.get("service_interval_days")
            if isinstance(days, int) and 1 <= days <= 365:
                cadence[equipment_type.lower()] = days
        return cadence

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    async def select_due_equipment(self) -> list[dict[str, Any]]:
        """Find equipment whose last_rollup_at is older than its cadence.

        Skips equipment with baseline_state='none' (per gating policy A).
        Big-equipment types only.

        Returns the equipment rows ready for WO emission. Each row includes
        equipment_id, site_id, code, name, type, last_rollup_at, and
        the resolved cadence so callers can log it.
        """
        try:
            from app.database.supabase_client import get_supabase_client

            sb = get_supabase_client()
            if sb is None:
                logger.warning("Supabase unavailable — skipping PPM selection")
                return []

            resp = (
                sb.table("equipment")
                .select("id, code, name, type, site_id, baseline_state, last_rollup_at, service_interval_days")
                .in_("baseline_state", ["seed_only", "rolling_active"])
                .in_("type", sorted(BIG_EQUIPMENT_TYPES))
                .execute()
            )
            candidates = resp.data or []
        except Exception as exc:
            logger.error("PPM select_due_equipment failed: %s", exc)
            return []

        now = datetime.now(timezone.utc)
        due: list[dict[str, Any]] = []
        for equipment in candidates:
            cadence = self.effective_cadence_days(equipment)
            last_rollup = equipment.get("last_rollup_at")
            if last_rollup:
                try:
                    last_dt = _parse_iso_datetime(last_rollup)
                except ValueError:
                    last_dt = None
                if last_dt is not None and (now - last_dt) < timedelta(days=cadence):
                    continue  # not due yet
            equipment["_effective_cadence_days"] = cadence
            due.append(equipment)
        return due

    async def has_open_preventive_wo(self, equipment_id: str) -> bool:
        """True if the equipment already has an open preventive WO.

        Idempotency check — prevents double-emit if the previous daily
        tick wrote a WO that hasn't been closed yet.
        """
        try:
            from app.database.supabase_client import get_supabase_client

            sb = get_supabase_client()
            if sb is None:
                return False
            resp = (
                sb.table("work_orders")
                .select("id")
                .eq("equipment_id", equipment_id)
                .eq("work_type", "preventive")
                .in_("status", ["open", "scheduled", "in_progress", "assigned", "draft", "pending"])
                .limit(1)
                .execute()
            )
            return bool(resp.data)
        except Exception as exc:
            logger.warning("PPM has_open_preventive_wo check failed for %s: %s", equipment_id, exc)
            # Fail-open: assume no open WO so the scheduler can still emit.
            return False

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    async def emit_for_equipment(self, equipment: dict[str, Any]) -> str | None:
        """Emit a preventive WO + linked service_records for one equipment.

        Returns the new work_order id, or None on failure. Creates the
        work_orders row first, then calls work_order_notifier.notify_technician_with_code
        so the service_records row, Telegram message, and email use the same
        existing closeout path as operator-created work orders.
        """
        if await self.has_open_preventive_wo(equipment["id"]):
            logger.info(
                "PPM skip (open preventive WO exists) for %s",
                equipment.get("code") or equipment.get("id"),
            )
            return None

        cadence = equipment.get("_effective_cadence_days") or self.effective_cadence_days(equipment)
        wo_data = await self._build_ppm_work_order(equipment, cadence)
        try:
            from app.database.repositories.work_order_repository import get_work_order_repository
            from app.services.sentry_integration.work_order_notifier import (
                WorkOrderNotifier,
            )

            wo_repo = get_work_order_repository()
            work_order = await wo_repo.create_work_order(wo_data)
            if not work_order:
                logger.error(
                    "PPM create_work_order failed for %s",
                    equipment.get("code") or equipment.get("id"),
                )
                return None

            notify_data = self._notification_payload(wo_data, work_order, equipment)
            notifier = WorkOrderNotifier()
            result = await notifier.notify_technician_with_code(notify_data)
        except Exception as exc:
            logger.error(
                "PPM emission failed for %s: %s",
                equipment.get("code") or equipment.get("id"),
                exc,
            )
            return None

        if not result.get("success"):
            logger.warning(
                "PPM emission returned non-success for %s: %s",
                equipment.get("code") or equipment.get("id"),
                result.get("error"),
            )
            return None

        logger.info(
            "PPM emitted WO for %s (cadence=%dd, service_record=%s)",
            equipment.get("code") or equipment.get("id"),
            cadence,
            result.get("service_record_code"),
        )
        return work_order.get("id")

    async def _build_ppm_work_order(self, equipment: dict[str, Any], cadence_days: int) -> dict[str, Any]:
        """Compose the work_order_data dict for the notifier.

        Resolves the site by code → UUID fallback, the technician via the
        active registry (first available), and constructs a description
        that names the cadence and prompts /done-WO-XXXX with readings.
        """
        site_id = (equipment.get("site_id") or "").strip() or None
        equipment_code = equipment.get("code") or ""
        equipment_name = equipment.get("name") or equipment_code or equipment.get("id")
        equipment_id = equipment.get("id")

        description = (
            f"PPM check ({cadence_days}-day cadence) for {equipment_name}. "
            f"Please capture numeric readings (vibration / acoustic / temperature) "
            "and run /done-WO-XXXX to close."
        )

        wo_data: dict[str, Any] = {
            "site_id": site_id,
            "equipment_id": equipment_id,
            "equipment_code": equipment_code,
            "equipment_name": equipment_name,
            "service_type": "preventive",
            "work_type": "preventive",
            "priority": "medium",
            "status": "scheduled",
            "title": f"PPM: {equipment_name}",
            "description": description,
            "created_by": "SENTINEL",
            "create_service_record": True,
        }

        technician = await self._resolve_default_technician(site_id)
        if technician:
            wo_data["assigned_to"] = technician.get("name") or ""
            wo_data["assigned_team"] = technician.get("specialty") or ""
            wo_data["technician_name"] = technician.get("name") or ""
            wo_data["technician_id"] = technician.get("telegram_id") or ""
            wo_data["technician_email"] = technician.get("email") or ""
        return wo_data

    @staticmethod
    def _notification_payload(
        wo_data: dict[str, Any],
        work_order: dict[str, Any],
        equipment: dict[str, Any],
    ) -> dict[str, Any]:
        """Build notifier payload from the created work_order row."""
        technician_name = wo_data.get("technician_name") or work_order.get("assigned_to") or "Technician"
        payload = {
            **wo_data,
            "work_order_id": work_order["id"],
            "work_order_code": work_order.get("code"),
            "code": work_order.get("code"),
            "site_id": work_order.get("site_id") or wo_data.get("site_id"),
            "equipment_id": work_order.get("equipment_id") or equipment.get("id"),
            "equipment_code": equipment.get("code") or wo_data.get("equipment_code"),
            "equipment_name": equipment.get("name") or wo_data.get("equipment_name"),
            "service_type": "preventive",
            "criticality": str(wo_data.get("priority") or "medium").upper(),
            "problem_description": wo_data.get("description"),
            "original_message": wo_data.get("description"),
            "technician_name": technician_name,
            "technician_id": wo_data.get("technician_id") or "",
            "technician_email": wo_data.get("technician_email") or "",
        }
        return payload

    async def _resolve_default_technician(self, site_id: str | None) -> dict[str, Any] | None:
        """Pick an active technician for the site.

        Falls back across site-scoped → global. Returns the full technician
        row so the caller has name / telegram_id / email. None if no
        technician found — emit unassigned; the technician-bot skill can
        claim the WO via /status.
        """
        try:
            from app.database.repositories.technician_repository import get_technician_repository

            repo = get_technician_repository()
            all_techs = await repo.get_all_technicians(active_only=True)
            if not all_techs:
                return None

            site_matches = {site_id} if site_id else set()
            if site_id:
                try:
                    from uuid import UUID

                    from app.database.supabase_client import get_supabase_client

                    UUID(str(site_id))
                    site_resp = get_supabase_client().table("sites").select("code").eq("id", site_id).limit(1).execute()
                    if site_resp.data and site_resp.data[0].get("code"):
                        site_matches.add(site_resp.data[0]["code"])
                except Exception:
                    pass

            # Prefer technicians whose row site_id matches the WO site UUID or code.
            if site_matches:
                same_site = [t for t in all_techs if (t.get("site_id") or "").strip() in site_matches]
                if same_site:
                    return same_site[0]
            return all_techs[0]
        except Exception as exc:
            logger.warning("PPM technician resolution failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Tick (entry point called by background_scheduler)
    # ------------------------------------------------------------------

    async def tick(self) -> dict[str, Any]:
        """One daily pass: select due equipment, emit preventive WOs.

        Returns a small summary so the scheduler logs can confirm the run.
        Errors on individual equipment rows are caught and logged; the tick
        itself never raises so a single bad row can't take down the daily
        cadence.
        """
        started_at = datetime.now(timezone.utc)
        due = await self.select_due_equipment()
        emitted = 0
        skipped_existing = 0
        failed = 0
        for equipment in due:
            try:
                result = await self.emit_for_equipment(equipment)
                if result:
                    emitted += 1
                elif result is None:
                    skipped_existing += 1
            except Exception as exc:
                failed += 1
                logger.error(
                    "PPM tick row failed for %s: %s",
                    equipment.get("code") or equipment.get("id"),
                    exc,
                )
        summary = {
            "selected": len(due),
            "emitted": emitted,
            "skipped_existing": skipped_existing,
            "failed": failed,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("PPM tick complete: %s", summary)
        return summary


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 string into an aware UTC datetime.

    Accepts Postgres-style `2026-07-05T08:00:00+00:00` and `...+00:00Z` mixed
    forms. Naive timestamps are treated as UTC.
    """
    cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ----------------------------------------------------------------------------
# Singleton accessor (matches the pattern in prediction_generator.py)
# ----------------------------------------------------------------------------

_ppm_scheduler_singleton: PPMScheduler | None = None


def get_ppm_scheduler() -> PPMScheduler:
    global _ppm_scheduler_singleton
    if _ppm_scheduler_singleton is None:
        _ppm_scheduler_singleton = PPMScheduler()
    return _ppm_scheduler_singleton
