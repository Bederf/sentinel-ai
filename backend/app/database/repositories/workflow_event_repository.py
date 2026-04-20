"""
Workflow Event Repository - Workflow event logging.
"""

import logging
from typing import Any

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class WorkflowEventRepository:
    """Repository for workflow events."""

    def __init__(self):
        self.client = get_supabase_client()

    def create(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            result = self.client.table("workflow_events").insert(data).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error creating workflow event: {e}")
            return None

    def list(
        self, equipment_id: str | None = None, trigger_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if not self.client:
            return []

        try:
            query = self.client.table("workflow_events").select("*").order("created_at", desc=True).limit(limit)
            if equipment_id:
                query = query.eq("equipment_id", equipment_id)
            if trigger_type:
                query = query.eq("trigger_type", trigger_type)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error listing workflow events: {e}")
            return []


_repository: WorkflowEventRepository | None = None


def get_workflow_event_repository() -> WorkflowEventRepository:
    global _repository
    if _repository is None:
        _repository = WorkflowEventRepository()
    return _repository
