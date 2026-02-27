"""Inspection Priority Scoring Service.

Computes inspection priority scores (0-100) per asset using a weighted
formula combining multiple signals. Higher score = more urgent inspection.

Formula:
  Priority = (days_overdue × 0.25) + (anomaly_score × 0.25) +
             (fault_history × 0.20) + (rul_inverse × 0.15) +
             (criticality × 0.15)

Used by: maintenance scheduling, work order prioritisation, helpdesk queue.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Singleton
_inspection_priority_service: Optional["InspectionPriorityService"] = None


def get_inspection_priority_service() -> "InspectionPriorityService":
    """Get singleton inspection priority service."""
    global _inspection_priority_service
    if _inspection_priority_service is None:
        _inspection_priority_service = InspectionPriorityService()
    return _inspection_priority_service


# Default inspection intervals by equipment type (days)
DEFAULT_INSPECTION_INTERVALS = {
    "chiller": 90,
    "ahu": 90,
    "fcu": 180,
    "vav": 180,
    "generator": 30,
    "ups": 90,
    "pump": 180,
    "ct": 90,
    "bess": 90,
    "dali": 365,
    "default": 180,
}

# Asset criticality by type (0-1, higher = more critical)
DEFAULT_CRITICALITY = {
    "chiller": 0.9,
    "ahu": 0.7,
    "fcu": 0.3,
    "vav": 0.3,
    "generator": 0.95,
    "ups": 0.85,
    "pump": 0.5,
    "ct": 0.6,
    "bess": 0.8,
    "dali": 0.2,
    "default": 0.4,
}


class InspectionPriorityService:
    """Computes inspection priority scores for equipment."""

    # Weights for priority formula
    W_DAYS_OVERDUE = 0.25
    W_ANOMALY = 0.25
    W_FAULT_HISTORY = 0.20
    W_RUL_INVERSE = 0.15
    W_CRITICALITY = 0.15

    async def compute_priority(
        self,
        equipment_id: str,
        equipment_type: str,
        last_inspection_date: Optional[datetime] = None,
        anomaly_score: float = 0.0,
        fault_count_30d: int = 0,
        rul_days: Optional[float] = None,
        criticality_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute inspection priority score for a single asset.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Equipment type (lowercase)
            last_inspection_date: Date of last inspection
            anomaly_score: Current anomaly score (0-1)
            fault_count_30d: Number of faults in last 30 days
            rul_days: Remaining useful life in days (None if unknown)
            criticality_override: Override default criticality (0-1)

        Returns:
            Dict with priority_score (0-100), components, and metadata
        """
        eq_type = equipment_type.lower()
        interval = DEFAULT_INSPECTION_INTERVALS.get(eq_type, DEFAULT_INSPECTION_INTERVALS["default"])
        criticality = criticality_override or DEFAULT_CRITICALITY.get(eq_type, DEFAULT_CRITICALITY["default"])

        # Component 1: Days overdue (0-100)
        days_overdue_score = 0.0
        days_since = None
        if last_inspection_date:
            days_since = (datetime.utcnow() - last_inspection_date).days
            days_overdue = max(0, days_since - interval)
            # Scale: 0 days overdue = 0, 2× interval overdue = 100
            days_overdue_score = min(100, (days_overdue / max(interval, 1)) * 100)
        else:
            # No inspection record — assume overdue
            days_overdue_score = 75.0

        # Component 2: Anomaly score (0-100)
        anomaly_component = min(100, anomaly_score * 100)

        # Component 3: Fault history (0-100)
        # 0 faults = 0, 1 fault = 25, 2 = 50, 3 = 75, 4+ = 100
        fault_component = min(100, fault_count_30d * 25)

        # Component 4: RUL inverse (0-100)
        rul_component = 0.0
        if rul_days is not None:
            if rul_days <= 0:
                rul_component = 100.0
            elif rul_days < 30:
                rul_component = 90.0
            elif rul_days < 90:
                rul_component = 60.0
            elif rul_days < 180:
                rul_component = 30.0
            else:
                rul_component = 10.0
        else:
            rul_component = 20.0  # Unknown = mild concern

        # Component 5: Criticality (0-100)
        criticality_component = criticality * 100

        # Weighted sum
        priority_score = (
            days_overdue_score * self.W_DAYS_OVERDUE
            + anomaly_component * self.W_ANOMALY
            + fault_component * self.W_FAULT_HISTORY
            + rul_component * self.W_RUL_INVERSE
            + criticality_component * self.W_CRITICALITY
        )

        priority_score = round(max(0, min(100, priority_score)), 1)

        return {
            "equipment_id": equipment_id,
            "equipment_type": eq_type,
            "priority_score": priority_score,
            "priority_level": self._score_to_level(priority_score),
            "components": {
                "days_overdue": round(days_overdue_score, 1),
                "anomaly": round(anomaly_component, 1),
                "fault_history": round(fault_component, 1),
                "rul_inverse": round(rul_component, 1),
                "criticality": round(criticality_component, 1),
            },
            "metadata": {
                "days_since_inspection": days_since,
                "inspection_interval_days": interval,
                "anomaly_score_raw": anomaly_score,
                "fault_count_30d": fault_count_30d,
                "rul_days": rul_days,
                "criticality": criticality,
            },
            "computed_at": datetime.utcnow().isoformat(),
        }

    async def compute_fleet_priorities(self, site_id: str) -> List[Dict[str, Any]]:
        """Compute inspection priorities for all equipment at a site.

        Gathers anomaly scores, health data, and inspection records
        to produce a ranked list of equipment needing inspection.

        Returns:
            List of priority dicts, sorted highest priority first.
        """
        results = []

        # Get equipment list
        try:
            from app.services.device_abstraction import device_manager

            devices = await device_manager.list_devices_by_site(site_id)
        except Exception as e:
            logger.warning(f"Could not load devices for {site_id}: {e}")
            return []

        # Get anomaly scores in bulk
        anomaly_map: Dict[str, float] = {}
        try:
            from app.services.ml_inference import get_anomaly_service

            anomaly_svc = get_anomaly_service()
            eq_list = [
                {
                    "equipment_id": d.id,
                    "equipment_type": (d.type.value if hasattr(d.type, "value") else str(d.type)).lower(),
                }
                for d in devices
                if d.type
            ]
            all_scores = anomaly_svc.check_all_equipment(eq_list)
            for score in all_scores:
                anomaly_map[score["equipment_id"]] = score.get("anomaly_score", 0)
        except Exception as e:
            logger.debug(f"Anomaly service unavailable for fleet priorities: {e}")

        # Compute priority for each device
        for device in devices:
            eq_type = (
                (device.type.value if hasattr(device.type, "value") else str(device.type)).lower()
                if device.type
                else "unknown"
            )

            priority = await self.compute_priority(
                equipment_id=device.id,
                equipment_type=eq_type,
                anomaly_score=anomaly_map.get(device.id, 0.0),
            )
            results.append(priority)

        # Sort by priority score descending
        results.sort(key=lambda x: x["priority_score"], reverse=True)

        return results

    @staticmethod
    def _score_to_level(score: float) -> str:
        """Convert priority score to human-readable level."""
        if score >= 80:
            return "critical"
        elif score >= 60:
            return "high"
        elif score >= 40:
            return "medium"
        elif score >= 20:
            return "low"
        return "routine"
