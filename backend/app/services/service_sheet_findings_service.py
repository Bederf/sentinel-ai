"""Service-sheet findings classifier and auto-escalation.

When OCR extracts checklist items or readings from a technician service sheet,
this service flags abnormal findings and escalates them:

- critical  → create work order
- warning   → add observation to service record
- good/ok   → log as normal observation (no escalation)

Reuses existing repositories and health-score update paths.
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import datetime
from typing import Any

from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.database.repositories.work_order_repository import WorkOrderRepository

logger = logging.getLogger(__name__)

# Severity mapping from raw OCR checklist values
CHECKLIST_SEVERITY: dict[str, str] = {
    "critical": "critical",
    "fail": "critical",
    "failed": "critical",
    "danger": "critical",
    "low": "warning",
    "warning": "warning",
    "needs_attention": "warning",
    "poor": "warning",
    "fair": "warning",
    "good": "normal",
    "ok": "normal",
    "pass": "normal",
    "excellent": "normal",
}


def _severity_from_checklist_value(value: str) -> str:
    """Map raw checklist value to canonical severity."""
    normalized = str(value).strip().lower().replace(" ", "_")
    return CHECKLIST_SEVERITY.get(normalized, "unknown")


def _severity_from_reading(
    value: float,
    tolerance_min: float | None,
    tolerance_max: float | None,
) -> str:
    """Classify numeric reading against tolerance limits."""
    if tolerance_max is not None and value > tolerance_max:
        # How far out of range?
        overshoot = (value - tolerance_max) / max(abs(tolerance_max), 1e-6)
        return "critical" if overshoot > 0.20 else "warning"
    if tolerance_min is not None and value < tolerance_min:
        undershoot = (tolerance_min - value) / max(abs(tolerance_min), 1e-6)
        return "critical" if undershoot > 0.20 else "warning"
    return "normal"


class ServiceSheetFindingsService:
    """Classify OCR-extracted service-sheet findings and escalate."""

    def __init__(self) -> None:
        self._wo_repo = WorkOrderRepository()
        self._sr_repo = ServiceRecordRepository()
        self._eq_repo = EquipmentRepository()

    async def classify_and_flag_findings(
        self,
        *,
        extracted_data: dict[str, Any],
        equipment_code: str,
        document_id: str | None = None,
        site_id: str | None = None,
        uploaded_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Scan extracted data for abnormal findings and escalate.

        Returns findings report with actions taken.
        """
        findings: list[dict[str, Any]] = []
        created_work_orders: list[str] = []
        added_observations: list[str] = []
        health_changes: list[dict[str, Any]] = []

        # Resolve site + equipment UUID from code
        equipment = self._eq_repo.get_by_id(equipment_code)
        if not equipment:
            logger.warning("Equipment not found for findings classifier: %s", equipment_code)
            return {
                "findings": [],
                "created_work_orders": [],
                "added_observations": [],
                "health_changes": [],
                "error": f"Equipment not found: {equipment_code}",
            }

        equipment_uuid = str(equipment.get("id") or "")
        resolved_site_id = site_id or str(equipment.get("site_id") or "")
        equipment_name = str(equipment.get("name") or equipment_code)

        # 1. Checklist items
        checklists = extracted_data.get("checklists") or {}
        for item_name, item_data in checklists.items():
            raw_value = item_data.get("value") if isinstance(item_data, dict) else str(item_data)
            severity = _severity_from_checklist_value(str(raw_value))
            if severity == "unknown":
                continue

            finding = {
                "source": "checklist",
                "item_name": item_name,
                "raw_value": raw_value,
                "severity": severity,
            }
            findings.append(finding)

            if severity == "critical":
                wo_code = await self._create_work_order_for_finding(
                    equipment_uuid=equipment_uuid,
                    equipment_code=equipment_code,
                    equipment_name=equipment_name,
                    site_id=resolved_site_id,
                    component=item_name,
                    condition=str(raw_value),
                    document_id=document_id,
                    uploaded_by_user_id=uploaded_by_user_id,
                )
                if wo_code:
                    finding["work_order_code"] = wo_code
                    created_work_orders.append(wo_code)
            elif severity == "warning":
                obs_id = await self._add_observation_for_finding(
                    equipment_uuid=equipment_uuid,
                    component=item_name,
                    condition=str(raw_value),
                    document_id=document_id,
                    severity="warning",
                )
                if obs_id:
                    finding["observation_id"] = obs_id
                    added_observations.append(obs_id)

        # 2. Readings
        readings = extracted_data.get("readings") or {}
        for reading_name, reading_data in readings.items():
            if not isinstance(reading_data, dict):
                continue
            numeric = reading_data.get("value")
            if numeric is None:
                continue
            try:
                numeric = float(numeric)
            except (ValueError, TypeError):
                continue

            unit = str(reading_data.get("unit") or "")
            # Try to find tolerance from equipment metadata or baseline
            tolerance_min, tolerance_max = self._resolve_tolerance(equipment_uuid, reading_name)

            severity = _severity_from_reading(numeric, tolerance_min, tolerance_max)
            if severity == "normal":
                continue

            finding = {
                "source": "reading",
                "item_name": reading_name,
                "raw_value": numeric,
                "unit": unit,
                "severity": severity,
                "tolerance_min": tolerance_min,
                "tolerance_max": tolerance_max,
            }
            findings.append(finding)

            if severity == "critical":
                wo_code = await self._create_work_order_for_finding(
                    equipment_uuid=equipment_uuid,
                    equipment_code=equipment_code,
                    equipment_name=equipment_name,
                    site_id=resolved_site_id,
                    component=reading_name,
                    condition=f"{numeric} {unit}",
                    document_id=document_id,
                    uploaded_by_user_id=uploaded_by_user_id,
                )
                if wo_code:
                    finding["work_order_code"] = wo_code
                    created_work_orders.append(wo_code)
            elif severity == "warning":
                obs_id = await self._add_observation_for_finding(
                    equipment_uuid=equipment_uuid,
                    component=reading_name,
                    condition=f"{numeric} {unit}",
                    document_id=document_id,
                    severity="warning",
                )
                if obs_id:
                    finding["observation_id"] = obs_id
                    added_observations.append(obs_id)

        # 3. Notes / observations text
        notes = str(extracted_data.get("notes") or "").strip()
        if notes and len(notes) > 10:
            # Heuristic: if notes contain critical keywords, flag
            critical_keywords = ("critical", "fail", "broken", "leak", "danger", "urgent", "replace")
            if any(kw in notes.lower() for kw in critical_keywords):
                finding = {
                    "source": "notes",
                    "item_name": "technician_notes",
                    "raw_value": notes[:200],
                    "severity": "warning",
                }
                findings.append(finding)
                obs_id = await self._add_observation_for_finding(
                    equipment_uuid=equipment_uuid,
                    component="technician_notes",
                    condition=notes[:500],
                    document_id=document_id,
                    severity="warning",
                )
                if obs_id:
                    finding["observation_id"] = obs_id
                    added_observations.append(obs_id)

        # 4. Health score impact: any critical or warning finding lowers health
        if findings:
            health_delta = self._calculate_health_delta(findings)
            if health_delta != 0:
                changed = await self._apply_health_delta(equipment_uuid, health_delta)
                if changed:
                    health_changes.append(
                        {
                            "equipment_code": equipment_code,
                            "delta": health_delta,
                            "new_health": changed.get("health_score"),
                        }
                    )

        return {
            "findings": findings,
            "created_work_orders": created_work_orders,
            "added_observations": added_observations,
            "health_changes": health_changes,
        }

    async def _create_work_order_for_finding(
        self,
        *,
        equipment_uuid: str,
        equipment_code: str,
        equipment_name: str,
        site_id: str,
        component: str,
        condition: str,
        document_id: str | None,
        uploaded_by_user_id: str | None,
    ) -> str | None:
        """Create a work order for a critical finding."""
        try:
            title = f"{component.replace('_', ' ').title()}: {condition}"
            description = (
                f"Critical finding flagged from service sheet upload.\n"
                f"Equipment: {equipment_name} ({equipment_code})\n"
                f"Component: {component}\n"
                f"Condition: {condition}\n"
            )
            if document_id:
                description += f"Source document: {document_id}\n"

            wo_data: dict[str, Any] = {
                "equipment_id": equipment_uuid,
                "equipment_code": equipment_code,
                "site_id": site_id,
                "title": title,
                "description": description,
                "priority": "urgent",
                "status": "scheduled",
                "created_by": uploaded_by_user_id or "system:findings_classifier",
            }
            created = await self._wo_repo.create_work_order(wo_data)
            if created:
                wo_code = str(created.get("code") or "")
                logger.info(
                    "Created WO %s for critical finding on %s (%s)",
                    wo_code,
                    equipment_code,
                    component,
                )
                return wo_code
        except Exception as exc:
            logger.error("Failed to create WO for finding on %s: %s", equipment_code, exc)
        return None

    async def _add_observation_for_finding(
        self,
        *,
        equipment_uuid: str,
        component: str,
        condition: str,
        document_id: str | None,
        severity: str,
    ) -> str | None:
        """Add observation to the latest service record for equipment."""
        try:
            # Find latest service record for this equipment
            records = await self._sr_repo.list({"equipment_id": equipment_uuid})
            if not records:
                # No service record exists yet; observations can't be orphaned,
                # so we silently skip. The critical path already creates a WO
                # which will create a service record in the existing flow.
                logger.info(
                    "No service record for %s; skipping observation for %s",
                    equipment_uuid,
                    component,
                )
                return None

            # Most recent by updated_at or created_at
            records.sort(
                key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""),
                reverse=True,
            )
            sr = records[0]
            sr_id = str(sr.get("id") or "")

            observation = await self._sr_repo.add_observation(
                sr_id,
                {
                    "observation_type": "service_sheet_finding",
                    "content": f"{component}: {condition}",
                    "severity": severity,
                    "metadata": {
                        "source_document_id": document_id,
                        "component": component,
                        "condition": condition,
                        "flagged_at": datetime.utcnow().isoformat() + "Z",
                    },
                },
            )
            obs_id = str(observation.get("id") or "")
            logger.info(
                "Added observation %s to SR %s for %s (%s)",
                obs_id,
                sr_id,
                component,
                severity,
            )
            return obs_id
        except Exception as exc:
            logger.error("Failed to add observation for %s: %s", component, exc)
        return None

    def _resolve_tolerance(self, equipment_uuid: str, reading_name: str) -> tuple[float | None, float | None]:
        """Try to resolve tolerance min/max for a reading from equipment metadata."""
        try:
            equipment = self._eq_repo.get_by_id(equipment_uuid)
            if not equipment:
                return None, None
            # Look in equipment metadata / specs JSONB
            specs = equipment.get("specs") or equipment.get("metadata") or {}
            if isinstance(specs, str):
                with contextlib.suppress(Exception):
                    specs = json.loads(specs)
            if not isinstance(specs, dict):
                return None, None
            tolerances = specs.get("tolerances") or specs.get("thresholds") or {}
            if not isinstance(tolerances, dict):
                return None, None
            rule = tolerances.get(reading_name) or tolerances.get(reading_name.lower())
            if isinstance(rule, dict):
                return rule.get("min"), rule.get("max")
            # Fallback: common HVAC thresholds
            hvac_defaults: dict[str, tuple[float | None, float | None]] = {
                "compressor_current": (None, 80.0),
                "chw_supply_temp": (4.0, 8.0),
                "chw_return_temp": (8.0, 14.0),
                "condenser_pressure": (None, 2000.0),
                "evaporator_pressure": (None, 500.0),
                "oil_pressure": (20.0, 60.0),
                "suction_pressure": (None, 80.0),
                "discharge_pressure": (None, 250.0),
                "vibration": (None, 7.0),
                "temperature": (None, 85.0),
                "bearing_temp": (None, 80.0),
            }
            return hvac_defaults.get(reading_name.lower(), (None, None))
        except Exception:
            return None, None

    def _calculate_health_delta(self, findings: list[dict[str, Any]]) -> int:
        """Calculate health score delta from findings."""
        critical_count = sum(1 for f in findings if f.get("severity") == "critical")
        warning_count = sum(1 for f in findings if f.get("severity") == "warning")
        # Critical: -5 each, Warning: -2 each, cap at -20
        delta = (critical_count * -5) + (warning_count * -2)
        return max(-20, delta)

    async def _apply_health_delta(self, equipment_uuid: str, delta: int) -> dict[str, Any] | None:
        """Apply health delta to equipment, clamped 0-100."""
        try:
            equipment = self._eq_repo.get_by_id(equipment_uuid)
            if not equipment:
                return None
            current = int(equipment.get("health_score") or 70)
            new_health = max(0, min(100, current + delta))
            updated = self._eq_repo.update(
                equipment_uuid, {"health_score": new_health, "updated_at": datetime.utcnow().isoformat() + "Z"}
            )
            logger.info(
                "Equipment %s health: %d -> %d (delta %d)",
                equipment_uuid,
                current,
                new_health,
                delta,
            )
            return updated
        except Exception as exc:
            logger.error("Failed to update health for %s: %s", equipment_uuid, exc)
        return None


# Singleton
_findings_service: ServiceSheetFindingsService | None = None


def get_service_sheet_findings_service() -> ServiceSheetFindingsService:
    global _findings_service
    if _findings_service is None:
        _findings_service = ServiceSheetFindingsService()
    return _findings_service
