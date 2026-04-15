"""
Sentry Notification Router API Routes.

Monitoring, acknowledgement, and digest management for the importance-based
notification system. Separate from Phase 102 technician channel management
(notifications.py).

All endpoints require AUTHENTICATED access.
"""

import logging

from fastapi import APIRouter, Depends

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.config.settings import settings
from app.services.sentry_notification_router import get_sentry_router
from app.services.n8n_service import get_n8n_service

logger = logging.getLogger("sentinel.api.notification_router")

router = APIRouter(prefix="/api/notification-router", tags=["notification-router"])


@router.get("/status")
async def get_notification_status(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Notification router status for System Health dashboard.

    Shows: recipient count, push/digest metrics, pending escalations, and per-channel status.
    """
    sentry_router = get_sentry_router()
    status = sentry_router.get_status()

    # Email channel status: determined by n8n connectivity + configured recipients
    n8n_svc = get_n8n_service()
    n8n_status = n8n_svc.status
    has_email_recipients = bool(settings.notification_email_recipients or settings.block_booking_concierge_email)
    email_configured = n8n_status.status.value in ("connected", "not_configured") and has_email_recipients

    status["channels"] = {
        "telegram": {"status": "active"},  # Sentry always active if router running
        "whatsapp": {"status": "active"},  # Sentry always active if router running
        "email": {
            "status": "active" if email_configured else "inactive",
            "n8n_status": n8n_status.status.value,
            "n8n_reachable": n8n_status.status.value == "connected",
            "recipients_configured": has_email_recipients,
        },
        "sms": {"status": "inactive"},
    }

    return status


@router.get("/escalations/pending")
async def get_pending_escalations(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """List notifications awaiting acknowledgement.

    Dashboard shows countdown timers for each pending notification.
    """
    sentry_router = get_sentry_router()
    return {
        "pending": sentry_router._escalation.get_pending(),
        "stats": sentry_router._escalation.get_stats(),
    }


@router.post("/acknowledge/{event_id}")
async def acknowledge_notification(
    event_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Manually acknowledge a notification from the dashboard.

    Normally done via Sentry bot, but provides a web fallback.
    """
    sentry_router = get_sentry_router()
    found = sentry_router.acknowledge(event_id)
    return {"acknowledged": found, "event_id": event_id}


@router.post("/digest/send-daily")
async def trigger_daily_digest(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Manually trigger daily digest delivery."""
    sentry_router = get_sentry_router()
    await sentry_router.send_daily_digests()
    return {"status": "sent"}


@router.post("/digest/send-weekly")
async def trigger_weekly_digest(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Manually trigger weekly digest delivery."""
    sentry_router = get_sentry_router()
    await sentry_router.send_weekly_digests()
    return {"status": "sent"}


@router.get("/digest/stats")
async def get_digest_stats(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """How many events are queued for the next digest delivery."""
    sentry_router = get_sentry_router()
    return sentry_router._digest.get_stats()


@router.post("/escalations/check")
async def check_escalations(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Manually trigger escalation check.

    Normally runs every 60 seconds via background task.
    """
    sentry_router = get_sentry_router()
    count = await sentry_router.check_escalations()
    return {"escalations_triggered": count}
