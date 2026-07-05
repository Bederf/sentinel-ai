"""Roll structured service readings into periodic equipment baselines."""

import logging
import statistics
import uuid
from datetime import UTC, datetime
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class EquipmentBaselineRollupService:
    """Create periodic baseline rows from recent service_readings."""

    def __init__(self, window: int = 8):
        self.window = window
        self.client = get_supabase_client()

    async def rollup_service_record(self, service_record_id: str) -> dict[str, Any]:
        """Roll up one closed/updated service record into equipment_baselines.

        Returns a small status dict so Sentry routes can report whether a rollup
        was written or skipped without treating "no numeric readings" as a hard
        failure.
        """
        service_record = self._get_service_record(service_record_id)
        if not service_record:
            return {"success": False, "skipped": True, "reason": "service_record_not_found"}

        equipment_id = str(service_record.get("equipment_id") or "").strip()
        if not equipment_id:
            return {"success": False, "skipped": True, "reason": "service_record_missing_equipment"}

        current_readings = self._get_readings([service_record_id])
        current_elements = self._numeric_elements(current_readings)
        if not current_elements:
            return {"success": True, "skipped": True, "reason": "no_numeric_readings"}

        record_ids = self._recent_service_record_ids(equipment_id, service_record_id)
        readings = self._get_readings(record_ids)
        grouped = self._group_numeric_readings(readings, set(current_elements))
        if not grouped:
            return {"success": True, "skipped": True, "reason": "no_rollup_values"}

        active_baseline = self._get_active_baseline(equipment_id)
        tolerances = self._extract_tolerances(active_baseline)
        now = datetime.now(UTC).isoformat()

        baseline_values = {
            element_id: self._rollup_element(
                values=values,
                element_id=element_id,
                unit=self._latest_unit(readings, element_id),
                tolerance=tolerances.get(element_id),
                captured_at=now,
                source_record_id=service_record_id,
            )
            for element_id, values in grouped.items()
        }

        baseline_id = str(uuid.uuid4())
        self._supersede_active_baselines(equipment_id)
        self.client.table("equipment_baselines").insert(
            {
                "id": baseline_id,
                "equipment_id": equipment_id,
                "baseline_date": now,
                "captured_by": service_record.get("technician_name") or "sentry",
                "baseline_type": "periodic",
                "status": "active",
                "baseline_values": baseline_values,
                "measurement_conditions": {
                    "window": self.window,
                    "source": "service_readings",
                    "service_record_id": service_record_id,
                    "work_order_id": service_record.get("work_order_id"),
                },
                "source_type": "work_order",
                "source_record_id": service_record_id,
                "notes": "Periodic baseline rollup from structured service readings",
                "created_at": now,
                "updated_at": now,
            }
        ).execute()

        self.client.table("equipment").update(
            {
                "baseline_state": "rolling_active",
                "last_rollup_at": now,
                "updated_at": now,
            }
        ).eq("id", equipment_id).execute()

        return {
            "success": True,
            "skipped": False,
            "baseline_id": baseline_id,
            "equipment_id": equipment_id,
            "elements": sorted(baseline_values.keys()),
            "window": self.window,
        }

    def _get_service_record(self, service_record_id: str) -> dict[str, Any] | None:
        result = self.client.table("service_records").select("*").eq("id", service_record_id).limit(1).execute()
        return result.data[0] if result.data else None

    def _recent_service_record_ids(self, equipment_id: str, current_record_id: str) -> list[str]:
        result = (
            self.client.table("service_records")
            .select("id, completed_at, created_at")
            .eq("equipment_id", equipment_id)
            .order("completed_at", desc=True)
            .order("created_at", desc=True)
            .limit(max(self.window * 3, self.window))
            .execute()
        )
        ids: list[str] = []
        for row in result.data or []:
            record_id = str(row.get("id") or "")
            if record_id and record_id not in ids:
                ids.append(record_id)
            if len(ids) >= self.window:
                break
        if current_record_id not in ids:
            ids.insert(0, current_record_id)
        return ids[: self.window]

    def _get_readings(self, service_record_ids: list[str]) -> list[dict[str, Any]]:
        if not service_record_ids:
            return []
        result = (
            self.client.table("service_readings")
            .select("*")
            .in_("service_record_id", service_record_ids)
            .order("captured_at", desc=True)
            .execute()
        )
        return result.data or []

    def _get_active_baseline(self, equipment_id: str) -> dict[str, Any] | None:
        result = (
            self.client.table("equipment_baselines")
            .select("*")
            .eq("equipment_id", equipment_id)
            .eq("status", "active")
            .order("baseline_date", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def _supersede_active_baselines(self, equipment_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        self.client.table("equipment_baselines").update({"status": "superseded", "updated_at": now}).eq(
            "equipment_id", equipment_id
        ).eq("status", "active").execute()

    @staticmethod
    def _numeric_elements(readings: list[dict[str, Any]]) -> set[str]:
        return {
            element_id
            for row in readings
            if (element_id := EquipmentBaselineRollupService._element_id(row))
            and EquipmentBaselineRollupService._numeric_value(row) is not None
        }

    @staticmethod
    def _group_numeric_readings(
        readings: list[dict[str, Any]],
        allowed_elements: set[str],
    ) -> dict[str, list[float]]:
        grouped: dict[str, list[float]] = {}
        for row in readings:
            element_id = EquipmentBaselineRollupService._element_id(row)
            if not element_id or element_id not in allowed_elements:
                continue
            value = EquipmentBaselineRollupService._numeric_value(row)
            if value is None:
                continue
            grouped.setdefault(element_id, []).append(value)
        return grouped

    @staticmethod
    def _element_id(row: dict[str, Any]) -> str | None:
        value = row.get("element_id") or row.get("reading_type")
        return str(value).strip() if value else None

    @staticmethod
    def _numeric_value(row: dict[str, Any]) -> float | None:
        value: Any = row.get("numeric_value")
        if value is None:
            value = row.get("value")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _latest_unit(readings: list[dict[str, Any]], element_id: str) -> str | None:
        for row in readings:
            if EquipmentBaselineRollupService._element_id(row) == element_id and row.get("unit"):
                return str(row["unit"])
        return None

    def _rollup_element(
        self,
        values: list[float],
        element_id: str,
        unit: str | None,
        tolerance: float | None,
        captured_at: str,
        source_record_id: str,
    ) -> dict[str, Any]:
        n = len(values)
        mean_value = statistics.mean(values)
        observed_sigma = statistics.stdev(values) if n >= 2 else None
        sigma = tolerance if n < self.window and tolerance is not None else observed_sigma
        if sigma is None:
            sigma = 0.0

        return {
            "value": round(mean_value, 4),
            "sigma": round(float(sigma), 4),
            "n": n,
            "unit": unit,
            "captured_at": captured_at,
            "source_record_id": source_record_id,
            "tolerance": tolerance,
            "tolerance_type": "absolute" if tolerance is not None else None,
            "rollup_window": self.window,
            "element_id": element_id,
        }

    @staticmethod
    def _extract_tolerances(active_baseline: dict[str, Any] | None) -> dict[str, float]:
        if not active_baseline:
            return {}
        baseline_values = active_baseline.get("baseline_values")
        if not isinstance(baseline_values, dict):
            return {}

        tolerances: dict[str, float] = {}
        for element_id, value in baseline_values.items():
            if not isinstance(value, dict):
                continue
            tolerance = value.get("tolerance")
            try:
                if tolerance is not None:
                    tolerances[str(element_id)] = float(tolerance)
            except (TypeError, ValueError):
                continue
        return tolerances
