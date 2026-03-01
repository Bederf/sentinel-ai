"""
Notification Background Tasks.

Periodic tasks for escalation checking and scheduled digest delivery.
In-process asyncio tasks — no external scheduler needed.
"""

import asyncio
import logging
from datetime import datetime

from app.services.sentry_notification_router import get_sentry_router

logger = logging.getLogger("sentinel.notification_tasks")

_running = False


async def start_notification_tasks():
    """Start background tasks for escalation and digest delivery."""
    global _running
    _running = True
    asyncio.create_task(_escalation_loop())
    asyncio.create_task(_digest_schedule_loop())
    logger.info("Notification background tasks started")


async def stop_notification_tasks():
    """Stop background tasks on shutdown."""
    global _running
    _running = False


async def _escalation_loop():
    """Check for overdue notifications every 60 seconds."""
    while _running:
        try:
            router = get_sentry_router()
            count = await router.check_escalations()
            if count > 0:
                logger.info("Escalation check: %d escalation(s) triggered", count)
        except Exception as e:
            logger.error("Escalation check error: %s", e)

        await asyncio.sleep(60)


async def _digest_schedule_loop():
    """Check every 5 minutes if it's time to send digests."""
    last_daily_date = None
    last_weekly_date = None

    while _running:
        try:
            now = datetime.utcnow()
            router = get_sentry_router()
            config = router._config

            today = now.date()
            if now.hour >= config.digest_hour and last_daily_date != today:
                logger.info("Sending daily digests...")
                await router.send_daily_digests()
                last_daily_date = today

            if now.weekday() == config.weekly_day and now.hour >= config.digest_hour and last_weekly_date != today:
                logger.info("Sending weekly digests...")
                await router.send_weekly_digests()
                last_weekly_date = today

        except Exception as e:
            logger.error("Digest schedule error: %s", e)

        await asyncio.sleep(300)
