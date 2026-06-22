"""Notification Queue — decouple alert creation from CLI latency.

Phase 228: Database-backed queue so POST /api/alerts returns <500ms
while CLI execution runs asynchronously via APScheduler worker.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class NotificationQueueService:
    """Database-backed notification queue.

    One row per queued notification. Worker picks up pending rows
    in FIFO order and processes them via AlertNotifier.
    """

    def __init__(self):
        self.client = get_supabase_client()

    def enqueue(
        self,
        payload: dict[str, Any],
        alert_id: str | None = None,
        notification_type: str = "alert",
        max_attempts: int = 3,
    ) -> str | None:
        """Insert a notification into the queue.

        Returns the queue entry ID on success, None on failure.
        """
        entry = {
            "id": str(uuid4()),
            "alert_id": alert_id,
            "notification_type": notification_type,
            "payload": payload,
            "status": "pending",
            "attempts": 0,
            "max_attempts": max_attempts,
        }

        try:
            self.client.table("notification_queue").insert(entry).execute()
            return entry["id"]
        except Exception as e:
            logger.error("Failed to enqueue notification: %s", e)
            return None

    def claim_pending(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch pending entries and mark as processing."""
        try:
            entries = (
                self.client.table("notification_queue")
                .select("*")
                .eq("status", "pending")
                .order("created_at")
                .limit(limit)
                .execute()
            )
            entries = entries.data or []
            if not entries:
                return []

            ids = [e["id"] for e in entries]
            self.client.table("notification_queue").update({"status": "processing"}).in_("id", ids).execute()

            return entries
        except Exception as e:
            logger.error("Failed to claim pending notifications: %s", e)
            return []

    def mark_sent(self, entry_id: str, attempts: int) -> None:
        """Mark a queue entry as sent."""
        try:
            self.client.table("notification_queue").update(
                {
                    "status": "sent",
                    "attempts": attempts + 1,
                    "processed_at": datetime.utcnow().isoformat(),
                }
            ).eq("id", entry_id).execute()
        except Exception as e:
            logger.warning("Failed to mark notification %s as sent: %s", entry_id[:8], e)

    def mark_failed(self, entry_id: str, attempts: int, max_attempts: int, error: str) -> None:
        """Mark a queue entry as failed, or reset to pending if retries remain."""
        try:
            attempts += 1
            if attempts >= max_attempts:
                self.client.table("notification_queue").update(
                    {
                        "status": "failed",
                        "attempts": attempts,
                        "last_error": error,
                        "processed_at": datetime.utcnow().isoformat(),
                    }
                ).eq("id", entry_id).execute()
            else:
                self.client.table("notification_queue").update(
                    {
                        "status": "pending",
                        "attempts": attempts,
                        "last_error": error,
                    }
                ).eq("id", entry_id).execute()
        except Exception as e:
            logger.warning("Failed to update notification %s: %s", entry_id[:8], e)

    def depth(self) -> int:
        """Return the number of pending notifications (for metrics)."""
        try:
            result = (
                self.client.table("notification_queue").select("id", count="exact").eq("status", "pending").execute()
            )
            return result.count or 0
        except Exception:
            return 0
