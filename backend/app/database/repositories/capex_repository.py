"""Repository for canonical CapEx analysis persistence."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class CapExRepository:
    """Repository for CapEx analyses with Postgres as the canonical store."""

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
        """Save a CapEx analysis result to the canonical DB store."""
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

        if self._supabase:
            try:
                resp = self._supabase.table("capex_analyses").insert(record).execute()
                if resp.data:
                    return resp.data[0]
            except Exception as e:
                logger.warning("CapEx save failed against canonical DB store: %s", e)

        return record

    async def get_analyses(
        self,
        equipment_code: Optional[str] = None,
        site_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get CapEx analyses with optional filtering from the canonical DB store."""
        if self._supabase:
            try:
                query = self._supabase.table("capex_analyses").select("*")
                if equipment_code:
                    query = query.eq("equipment_code", equipment_code)
                elif site_id:
                    prefix = site_id.upper().replace("-", "")[:4]
                    query = query.ilike("equipment_code", f"{prefix}%")
                query = query.order("created_at", desc=True).limit(limit)
                resp = query.execute()
                if resp.data is not None:
                    return resp.data
            except Exception as e:
                logger.warning("CapEx query failed against canonical DB store: %s", e)

        return []

    async def get_latest_analysis(self, equipment_code: str) -> Optional[Dict[str, Any]]:
        """Get most recent analysis for equipment."""
        results = await self.get_analyses(equipment_code=equipment_code, limit=1)
        return results[0] if results else None


_repo_instance: Optional[CapExRepository] = None


def get_capex_repository() -> CapExRepository:
    """Get or create the CapEx repository singleton."""
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = CapExRepository()
    return _repo_instance
