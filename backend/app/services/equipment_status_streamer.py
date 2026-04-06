"""Equipment Status Streamer for Digital Twin SSE endpoint.

Streams real-time equipment status updates and predictive fault overlays
via Server-Sent Events (SSE). Follows the existing events.py pattern.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime

from app.models.equipment_status import (
    EquipmentStatusFrame,
    EquipmentStatusUpdate,
)
from app.services.prediction_overlay_service import get_prediction_overlay_service

logger = logging.getLogger(__name__)


class EquipmentStatusStreamer:
    """Streams equipment status + predictions as SSE frames."""

    # Interval between status pushes (seconds)
    STATUS_INTERVAL = 5
    # Interval between heartbeats when no data changes (seconds)
    HEARTBEAT_INTERVAL = 15

    def __init__(self):
        """Initialize the streamer."""
        self._equipment_repo = None

    def _get_equipment_repo(self):
        """Lazy-load equipment repository."""
        if self._equipment_repo is None:
            from app.database.repositories.equipment_repository import EquipmentRepository

            self._equipment_repo = EquipmentRepository()
        return self._equipment_repo

    async def _fetch_equipment_updates(self, site_id: str) -> list[EquipmentStatusUpdate]:
        """Fetch current equipment status for a site.

        Uses 3-tier fallback: Supabase -> Redis cache -> JSON fallback.
        The equipment repository already implements caching internally.

        Args:
            site_id: Site UUID

        Returns:
            List of equipment status updates
        """
        try:
            repo = self._get_equipment_repo()
            equipment_list = repo.get_all(site_id=site_id)

            updates = []
            for eq in equipment_list:
                update = EquipmentStatusUpdate(
                    equipment_id=eq.get("id", ""),
                    code=eq.get("code", ""),
                    type=eq.get("type", "unknown"),
                    health_score=eq.get("health_score", 100) or 100,
                    status=eq.get("status", "unknown"),
                    power_kw=eq.get("power_kw"),
                    temperatures=eq.get("temperatures"),
                    timestamp=datetime.utcnow(),
                )
                updates.append(update)

            return updates

        except Exception as e:
            logger.error(f"Failed to fetch equipment for site {site_id}: {e}")
            return []

    async def stream_status(self, site_id: str) -> AsyncGenerator[str, None]:
        """Stream equipment status frames as SSE events.

        Yields SSE-formatted strings every STATUS_INTERVAL seconds.
        Sends heartbeat comments every HEARTBEAT_INTERVAL to keep connection alive.

        Args:
            site_id: Site UUID to stream status for

        Yields:
            SSE-formatted event strings
        """
        prediction_service = get_prediction_overlay_service()
        heartbeat_counter = 0

        # Send initial connected event
        yield 'data: {"type": "connected", "data": {}}\n\n'

        while True:
            try:
                # Fetch equipment status and predictions concurrently
                equipment_updates, predictions = await asyncio.gather(
                    self._fetch_equipment_updates(site_id),
                    prediction_service.get_predictions_for_site(site_id),
                )

                # Build frame
                frame = EquipmentStatusFrame(
                    site_id=site_id,
                    equipment_updates=equipment_updates,
                    predictions=predictions,
                    timestamp=datetime.utcnow(),
                )

                # Serialize and yield as SSE event
                frame_json = frame.model_dump_json()
                yield f"data: {frame_json}\n\n"

                heartbeat_counter = 0

            except asyncio.CancelledError:
                logger.info(f"Equipment status stream cancelled for site {site_id}")
                return

            except Exception as e:
                logger.error(f"Error in equipment status stream for site {site_id}: {e}")
                heartbeat_counter += 1

                # Send heartbeat on error to keep connection alive
                if heartbeat_counter * self.STATUS_INTERVAL >= self.HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    heartbeat_counter = 0

            # Wait before next push
            try:
                await asyncio.sleep(self.STATUS_INTERVAL)
            except asyncio.CancelledError:
                return
