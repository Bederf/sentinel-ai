"""
Fire Pump Compliance Repository

Database operations for fire pump inspection records (FNBFW:32335).
Dual-write: Supabase primary + JSON fallback.
"""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.database.supabase_client import get_supabase_client
from app.models.fire_pump_compliance import FirePumpInspection, InspectionResult

logger = logging.getLogger(__name__)

# JSON fallback file for fire pump inspections
FIRE_PUMP_JSON_FILE = Path(__file__).parent.parent.parent / "data" / "fire_pump_inspections.json"


class FirePumpComplianceRepository:
    """Repository for fire pump compliance database operations."""

    TABLE_NAME = "fire_pump_inspections"

    def __init__(self, supabase=None, json_fallback_path: Path | None = None):
        self.supabase = supabase or get_supabase_client()
        self.json_fallback_path = json_fallback_path or FIRE_PUMP_JSON_FILE
        self._ensure_json_fallback_dir()

    def _ensure_json_fallback_dir(self) -> None:
        """Ensure JSON fallback directory exists."""
        self.json_fallback_path.parent.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # JSON Fallback Helpers
    # ========================================================================

    def _load_json_records(self) -> list[dict[str, Any]]:
        """Load records from JSON fallback file."""
        if not self.json_fallback_path.exists():
            return []
        try:
            with open(self.json_fallback_path) as f:
                data = json.load(f)
                return data.get("records", [])
        except Exception as e:
            logger.error(f"Failed to load JSON fallback: {e}")
            return []

    def _save_json_records(self, records: list[dict[str, Any]]) -> None:
        """Save records to JSON fallback file."""
        try:
            with open(self.json_fallback_path, "w") as f:
                json.dump(
                    {
                        "updated_at": datetime.now().isoformat(),
                        "records": records,
                    },
                    f,
                    indent=2,
                    default=str,
                )
        except Exception as e:
            logger.error(f"Failed to save JSON fallback: {e}")

    def _json_insert(self, inspection: FirePumpInspection) -> FirePumpInspection:
        """Insert record into JSON fallback."""
        records = self._load_json_records()
        records.append(inspection.to_dict())
        self._save_json_records(records)
        return inspection

    def _json_update(self, inspection: FirePumpInspection) -> FirePumpInspection:
        """Update record in JSON fallback."""
        records = self._load_json_records()
        for i, rec in enumerate(records):
            if rec["id"] == str(inspection.id):
                records[i] = inspection.to_dict()
                break
        self._save_json_records(records)
        return inspection

    # ========================================================================
    # Schedule Inspection
    # ========================================================================

    async def schedule_inspection(self, site_code: str, equipment_id: str, scheduled_date: date) -> FirePumpInspection:
        """Create a scheduled fire pump inspection."""
        inspection = FirePumpInspection(
            id=uuid4(),
            site_code=site_code,
            equipment_id=equipment_id,
            scheduled_date=scheduled_date,
        )

        try:
            # Try Supabase first
            result = self.supabase.table(self.TABLE_NAME).insert(inspection.to_dict()).execute()
            if result.data:
                return FirePumpInspection.from_dict(result.data[0])
        except Exception as e:
            logger.warning(f"Supabase insert failed, using JSON fallback: {e}")

        # JSON fallback
        return self._json_insert(inspection)

    # ========================================================================
    # Record Inspection Result
    # ========================================================================

    async def record_inspection_result(
        self,
        inspection_id: UUID | str,
        result: InspectionResult,
        certified_by: str | None,
        notes: str | None,
    ) -> FirePumpInspection | None:
        """Record test result for an existing inspection."""
        update_data = {
            "completed_date": date.today().isoformat(),
            "result": result.value,
            "certified_by": certified_by,
            "notes": notes,
            "updated_at": datetime.now().isoformat(),
        }

        try:
            result_db = self.supabase.table(self.TABLE_NAME).update(update_data).eq("id", str(inspection_id)).execute()
            if result_db.data:
                return FirePumpInspection.from_dict(result_db.data[0])
        except Exception as e:
            logger.warning(f"Supabase update failed, trying JSON fallback: {e}")

        # JSON fallback - find and update
        records = self._load_json_records()
        for i, rec in enumerate(records):
            if rec["id"] == str(inspection_id):
                records[i].update(update_data)
                records[i]["updated_at"] = datetime.now().isoformat()
                self._save_json_records(records)
                return FirePumpInspection.from_dict(records[i])

        return None

    # ========================================================================
    # Get Upcoming Inspections
    # ========================================================================

    async def get_upcoming_inspections(self, site_code: str, days: int = 7) -> list[FirePumpInspection]:
        """Get inspections due in the next N days (including today)."""
        today = date.today()
        end_date = today + timedelta(days=days)

        try:
            result = (
                self.supabase.table(self.TABLE_NAME)
                .select("*")
                .eq("site_code", site_code)
                .gte("scheduled_date", today.isoformat())
                .lte("scheduled_date", end_date.isoformat())
                .order("scheduled_date")
                .execute()
            )
            if result.data:
                return [FirePumpInspection.from_dict(row) for row in result.data]
        except Exception as e:
            logger.warning(f"Supabase query failed, using JSON fallback: {e}")

        # JSON fallback
        records = self._load_json_records()
        upcoming = []
        for rec in records:
            if rec.get("site_code") != site_code:
                continue
            sched = rec.get("scheduled_date")
            if sched:
                sched_date = date.fromisoformat(sched) if isinstance(sched, str) else sched
                if today <= sched_date <= end_date:
                    upcoming.append(FirePumpInspection.from_dict(rec))

        upcoming.sort(key=lambda x: x.scheduled_date)
        return upcoming

    # ========================================================================
    # Get Overdue Inspections
    # ========================================================================

    async def get_overdue_inspections(self, site_code: str) -> list[FirePumpInspection]:
        """Get overdue inspections: scheduled_date < today AND completed_date is null."""
        today = date.today()

        try:
            result = (
                self.supabase.table(self.TABLE_NAME)
                .select("*")
                .eq("site_code", site_code)
                .lt("scheduled_date", today.isoformat())
                .is_("completed_date", None)
                .order("scheduled_date")
                .execute()
            )
            if result.data:
                return [FirePumpInspection.from_dict(row) for row in result.data]
        except Exception as e:
            logger.warning(f"Supabase query failed, using JSON fallback: {e}")

        # JSON fallback
        records = self._load_json_records()
        overdue = []
        for rec in records:
            if rec.get("site_code") != site_code:
                continue
            sched = rec.get("scheduled_date")
            completed = rec.get("completed_date")
            if sched and completed is None:
                sched_date = date.fromisoformat(sched) if isinstance(sched, str) else sched
                if sched_date < today:
                    overdue.append(FirePumpInspection.from_dict(rec))

        overdue.sort(key=lambda x: x.scheduled_date)
        return overdue

    # ========================================================================
    # Get Compliance Status
    # ========================================================================

    async def get_compliance_status(self, site_code: str) -> dict[str, Any]:
        """Get overall compliance rate: completed / total scheduled."""
        try:
            # All-time stats (all scheduled records for this site)
            all_result = self.supabase.table(self.TABLE_NAME).select("*").eq("site_code", site_code).execute()
            total = len(all_result.data) if all_result.data else 0
            completed = sum(1 for r in all_result.data if r.get("completed_date") is not None)

        except Exception as e:
            logger.warning(f"Supabase query failed, using JSON fallback: {e}")

            # JSON fallback
            records = self._load_json_records()
            site_records = [r for r in records if r.get("site_code") == site_code]
            total = len(site_records)
            completed = sum(1 for r in site_records if r.get("completed_date") is not None)

        compliance_rate = (completed / total * 100) if total > 0 else 0.0

        return {
            "site_code": site_code,
            "total_scheduled": total,
            "completed": completed,
            "pending": total - completed,
            "compliance_rate": round(compliance_rate, 2),
        }

    # ========================================================================
    # Get Inspections in Date Range
    # ========================================================================

    async def get_inspections_in_range(
        self,
        site_code: str,
        start_date: date,
        end_date: date,
    ) -> list[FirePumpInspection]:
        """Get all inspections within a date range."""
        try:
            result = (
                self.supabase.table(self.TABLE_NAME)
                .select("*")
                .eq("site_code", site_code)
                .gte("scheduled_date", start_date.isoformat())
                .lte("scheduled_date", end_date.isoformat())
                .order("scheduled_date")
                .execute()
            )
            if result.data:
                return [FirePumpInspection.from_dict(row) for row in result.data]
        except Exception as e:
            logger.warning(f"Supabase query failed, using JSON fallback: {e}")

        # JSON fallback
        records = self._load_json_records()
        in_range = []
        for rec in records:
            if rec.get("site_code") != site_code:
                continue
            sched = rec.get("scheduled_date")
            if sched:
                sched_date = date.fromisoformat(sched) if isinstance(sched, str) else sched
                if start_date <= sched_date <= end_date:
                    in_range.append(FirePumpInspection.from_dict(rec))

        in_range.sort(key=lambda x: x.scheduled_date)
        return in_range
