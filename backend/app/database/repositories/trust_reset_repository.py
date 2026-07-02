"""Repository for trust reset events audit trail.

PLAN-162B: Records every trust profile reset or decay with prior snapshot
for operator accountability.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

TRUST_RESET_TABLE = "trust_reset_events"


class TrustResetRepository:
    """Persists trust reset events for operator visibility and audit."""

    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from app.database.supabase_client import get_supabase_client

                self._client = get_supabase_client()
            except Exception as exc:
                logger.warning("Failed to get Supabase client for trust reset events: %s", exc)
        return self._client

    async def record_reset(
        self,
        *,
        equipment_id: str,
        site_id: str,
        trigger_type: str,
        trigger_id: str | None = None,
        prior_trust: dict | None = None,
        reset_action: str,
    ) -> str | None:
        """Record a trust reset event.

        Returns the event ID if persisted, None on failure.
        """
        client = self.client
        if not client:
            logger.warning("[TRUST-RESET] No Supabase client — skipping audit record")
            return None

        event_id = str(uuid4())
        try:
            client.table(TRUST_RESET_TABLE).insert(
                {
                    "id": event_id,
                    "equipment_id": equipment_id,
                    "site_id": site_id,
                    "trigger_type": trigger_type,
                    "trigger_id": trigger_id or "",
                    "prior_trust": prior_trust or {},
                    "reset_action": reset_action,
                    "occurred_at": datetime.utcnow().isoformat(),
                }
            ).execute()
            return event_id
        except Exception as exc:
            logger.warning("Failed to record trust reset event: %s", exc)
            return None
