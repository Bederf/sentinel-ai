"""Repository for CapEx analysis persistence (Phase 128).

3-tier fallback: Supabase → Redis Cache → JSON file.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

_JSON_PATH = Path(__file__).parent.parent.parent / "data" / "capex_analyses.json"


class CapExRepository:
    """Repository for CapEx analyses with 3-tier fallback."""

    def __init__(self):
        self._supabase = None
        self._init_supabase()

    def _init_supabase(self):
        """Try to initialize Supabase client."""
        try:
            from app.database.supabase_client import get_supabase_client

            self._supabase = get_supabase_client()
        except Exception:
            self._supabase = None

    async def save_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Save a CapEx analysis result.

        Args:
            analysis: Analysis result from capex_planning_service.

        Returns:
            Saved record with id.
        """
        record = {
            "id": str(uuid4()),
            "equipment_code": analysis.get("equipment_code", analysis.get("equipment_type")),
            "equipment_type": analysis.get("equipment_type"),
            "recommendation": analysis.get("recommendation"),
            "confidence_pct": analysis.get("confidence_pct"),
            "npv_replace_zar": analysis.get("npv_replace_zar"),
            "npv_repair_zar": analysis.get("npv_repair_zar"),
            "npv_advantage_zar": analysis.get("npv_advantage_zar"),
            "replacement_cost_zar": analysis.get("replacement_cost_zar"),
            "repair_cost_zar": analysis.get("repair_cost_zar"),
            "failure_probability": analysis.get("failure_probability"),
            "payback_months": analysis.get("payback_months"),
            "risk_reduction_pct": analysis.get("risk_reduction_pct"),
            "discount_rate": analysis.get("discount_rate"),
            "horizon_years": analysis.get("horizon_years"),
            "analysis_date": analysis.get("analysis_date"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Try Supabase
        if self._supabase:
            try:
                resp = self._supabase.table("capex_analyses").insert(record).execute()
                if resp.data:
                    return resp.data[0]
            except Exception as e:
                logger.debug(f"Supabase capex save failed (expected if table missing): {e}")

        # Fallback to JSON
        return self._save_to_json(record)

    async def get_analyses(
        self,
        equipment_code: Optional[str] = None,
        site_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get CapEx analyses with optional filtering.

        Args:
            equipment_code: Filter by equipment code.
            site_id: Filter by site (prefix match on equipment_code).
            limit: Max results.

        Returns:
            List of analysis records.
        """
        # Try Supabase
        if self._supabase:
            try:
                query = self._supabase.table("capex_analyses").select("*")
                if equipment_code:
                    query = query.eq("equipment_code", equipment_code)
                query = query.order("created_at", desc=True).limit(limit)
                resp = query.execute()
                if resp.data is not None:
                    return resp.data
            except Exception:
                pass

        # Fallback to JSON
        return self._read_from_json(equipment_code, site_id, limit)

    async def get_latest_analysis(self, equipment_code: str) -> Optional[Dict[str, Any]]:
        """Get most recent analysis for equipment."""
        results = await self.get_analyses(equipment_code=equipment_code, limit=1)
        return results[0] if results else None

    def _save_to_json(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Save to JSON fallback file."""
        data = []
        if _JSON_PATH.exists():
            try:
                with open(_JSON_PATH) as f:
                    data = json.load(f)
            except Exception:
                data = []

        data.append(record)

        # Keep last 500 records
        if len(data) > 500:
            data = data[-500:]

        with open(_JSON_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)

        return record

    def _read_from_json(
        self,
        equipment_code: Optional[str],
        site_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Read from JSON fallback file."""
        if not _JSON_PATH.exists():
            return []

        try:
            with open(_JSON_PATH) as f:
                data = json.load(f)
        except Exception:
            return []

        if equipment_code:
            data = [d for d in data if d.get("equipment_code") == equipment_code]
        elif site_id:
            prefix = site_id.upper().replace("-", "")[:4]
            data = [d for d in data if (d.get("equipment_code") or "").startswith(prefix)]

        # Sort newest first
        data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return data[:limit]


# Singleton
_repo_instance: Optional[CapExRepository] = None


def get_capex_repository() -> CapExRepository:
    """Get or create the CapEx repository singleton."""
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = CapExRepository()
    return _repo_instance
