"""Visit Notification Service — WhatsApp alerts to hosts.

Orchestrates WhatsApp notifications for the visit lifecycle:
- notify_host_arrival: sent when visitor scans at reception
- notify_access_issued: sent when reception issues an access card
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.integrations.whatsapp_service import WhatsAppService

if TYPE_CHECKING:
    from app.models.visit import Visit

logger = logging.getLogger(__name__)

# Singleton instance
_notification_service: VisitNotificationService | None = None


def get_notification_service() -> VisitNotificationService:
    """Get or create the notification service singleton."""
    global _notification_service
    if _notification_service is None:
        _notification_service = VisitNotificationService()
    return _notification_service


class VisitNotificationService:
    """Sends WhatsApp notifications to hosts during the visit lifecycle."""

    def __init__(self) -> None:
        self.whatsapp = WhatsAppService()

    def _get_building_name(self, building_id: str) -> str:
        """Resolve building_id to a human-readable name."""
        try:
            from app.data.settings import settings

            # Try to find building name from sites data
            sites = getattr(settings, "sites", [])
            for site in sites:
                if site.get("code") == building_id or site.get("id") == building_id:
                    return site.get("name", building_id)
        except Exception:
            pass
        # Fallback: return the building_id as-is
        return building_id

    def _get_host_mobile(self, host_email: str, host_mobile: str | None) -> str | None:
        """Get host mobile number from AD or pre-registered data.

        Returns pre-registered mobile if available, otherwise queries AD.
        """
        if host_mobile:
            return host_mobile

        # Try Active Directory service
        try:
            from app.services.active_directory_service import get_active_directory_service

            ad = get_active_directory_service()
            host_record = ad.get_host_by_email(host_email)
            if host_record:
                return host_record.get("mobile")
        except ImportError:
            logger.debug("ActiveDirectoryService not available")
        except Exception as e:
            logger.warning(f"AD lookup failed for {host_email}: {e}")

        return None

    async def _send_whatsapp(self, host_mobile: str, message: str) -> bool:
        """Send a WhatsApp message. Returns True on success."""
        try:
            result = await self.whatsapp.send_text_message(host_mobile, message)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"[VisitNotification] WhatsApp send failed: {e}")
            return False

    def notify_host_arrival(self, visit: Visit) -> bool:
        """Send WhatsApp notification to host when visitor scans at reception.

        This is a sync wrapper. Use _notify_host_arrival_async for async contexts.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — create a new one (sync context)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._notify_host_arrival_async(visit))
                return future.result()
        else:
            # Running loop exists — schedule as background task
            loop.create_task(self._notify_host_arrival_async(visit))
            return True

    async def _notify_host_arrival_async(self, visit: Visit) -> bool:
        """Async implementation of host arrival notification."""
        host_mobile = self._get_host_mobile(visit.host_email, visit.host_mobile)
        if not host_mobile:
            logger.warning(
                f"[VisitNotification] No mobile for host {visit.host_email}, "
                f"cannot send arrival notification for visit {visit.id}"
            )
            return False

        visitor_display = visit.visitor_name or "Your visitor"
        building_name = self._get_building_name(visit.building_id)

        message = (
            f"\U0001f514 Visitor Alert\n\n"
            f"{visitor_display} has arrived at {building_name}.\n\n"
            f"Meeting: {visit.meeting_start.strftime('%H:%M')} - {visit.meeting_end.strftime('%H:%M')}\n\n"
            f"Reply YES to approve or NO to deny."
        )

        success = await self._send_whatsapp(host_mobile, message)
        logger.info(
            f"[VisitNotification] Arrival notification {'sent' if success else 'failed'} "
            f"to {host_mobile} for visit {visit.id}"
        )
        return success

    def notify_access_issued(self, visit: Visit) -> bool:
        """Send WhatsApp notification that access card was issued.

        This is a sync wrapper. Use _notify_access_issued_async for async contexts.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._notify_access_issued_async(visit))
                return future.result()
        else:
            loop.create_task(self._notify_access_issued_async(visit))
            return True

    async def _notify_access_issued_async(self, visit: Visit) -> bool:
        """Async implementation of access issued notification."""
        host_mobile = self._get_host_mobile(visit.host_email, visit.host_mobile)
        if not host_mobile:
            logger.warning(
                f"[VisitNotification] No mobile for host {visit.host_email}, "
                f"cannot send access issued notification for visit {visit.id}"
            )
            return False

        building_name = self._get_building_name(visit.building_id)
        visitor_display = visit.visitor_name or "visitor"

        message = f"\u2705 Access approved.\n\nCard issued to {visitor_display} at {building_name}."

        success = await self._send_whatsapp(host_mobile, message)
        logger.info(
            f"[VisitNotification] Access issued notification {'sent' if success else 'failed'} "
            f"to {host_mobile} for visit {visit.id}"
        )
        return success
