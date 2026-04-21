"""Delivery tracking for parts orders."""

import asyncio
import logging
from datetime import datetime
from enum import StrEnum

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/delivery", tags=["delivery_tracking"])


class DeliveryStatus(StrEnum):
    """Delivery status enum."""

    ORDERED = "ordered"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class TrackingInfo(BaseModel):
    """Tracking information model."""

    order_id: str
    status: DeliveryStatus
    supplier: str
    tracking_number: str | None = None
    estimated_delivery: datetime | None = None
    last_updated: datetime
    location: str | None = None
    notes: str | None = None


class DeliveryTrackerResponse(BaseModel):
    """Delivery tracker response model."""

    order_id: str
    current_status: DeliveryStatus
    tracking_info: TrackingInfo
    status_history: list[dict]


# In-memory storage for tracking
_tracking_status: dict[str, dict] = {}


class DeliveryTracker:
    """Track delivery status from suppliers."""

    def __init__(self):
        """Initialize delivery tracker."""
        self.tracking_status = _tracking_status

    async def update_tracking(self, order_id: str, tracking_info: dict) -> TrackingInfo:
        """
        Update delivery tracking information.

        Called by supplier webhooks or periodic polling.
        """
        status_str = tracking_info.get("status", "ordered").lower()

        # Validate status
        try:
            status = DeliveryStatus(status_str)
        except ValueError:
            status = DeliveryStatus.ORDERED

        tracking_data = TrackingInfo(
            order_id=order_id,
            status=status,
            supplier=tracking_info.get("supplier", "Unknown"),
            tracking_number=tracking_info.get("tracking_number"),
            estimated_delivery=tracking_info.get("estimated_delivery"),
            last_updated=datetime.now(),
            location=tracking_info.get("location"),
            notes=tracking_info.get("notes"),
        )

        # Store or update tracking info
        if order_id not in self.tracking_status:
            self.tracking_status[order_id] = {
                "current_tracking": tracking_data,
                "history": [
                    {
                        "status": status.value,
                        "timestamp": datetime.now().isoformat(),
                        "notes": tracking_info.get("notes", ""),
                    }
                ],
            }
        else:
            # Add to history
            self.tracking_status[order_id]["history"].append(
                {
                    "status": status.value,
                    "timestamp": datetime.now().isoformat(),
                    "notes": tracking_info.get("notes", ""),
                }
            )
            # Update current tracking
            self.tracking_status[order_id]["current_tracking"] = tracking_data

        # Notify technician
        await self._notify_technician(order_id, tracking_data)

        return tracking_data

    async def _notify_technician(self, order_id: str, tracking_info: TrackingInfo) -> None:
        """Notify technician of delivery status update."""
        # TODO: Send push notification or email
        logger.info(f"Technician notification: Order {order_id} status updated to {tracking_info.status.value}")

    async def poll_supplier_status(self, order_id: str, supplier: str) -> dict | None:
        """
        Poll supplier for order status (fallback for suppliers without webhooks).

        Runs as background task.
        """
        # TODO: Implement supplier-specific polling logic
        logger.info(f"Polling {supplier} for order {order_id}")
        return None

    def get_tracking(self, order_id: str) -> dict | None:
        """Get tracking info for order."""
        return self.tracking_status.get(order_id)


# Global tracker instance
_tracker = DeliveryTracker()


@router.get("/{order_id}/tracking", response_model=DeliveryTrackerResponse)
async def get_tracking(order_id: str, auth: AuthContext = Depends(require_auth)) -> DeliveryTrackerResponse:
    """Get delivery tracking info for order."""
    tracking = _tracker.get_tracking(order_id)
    if not tracking:
        raise HTTPException(status_code=404, detail="Order not found")

    return DeliveryTrackerResponse(
        order_id=order_id,
        current_status=tracking["current_tracking"].status,
        tracking_info=tracking["current_tracking"],
        status_history=tracking.get("history", []),
    )


@router.post("/{order_id}/update-tracking")
async def update_tracking(
    order_id: str,
    tracking_info: dict,
    auth: AuthContext = Depends(require_auth),
) -> TrackingInfo:
    """Update tracking information for order."""
    try:
        result = await _tracker.update_tracking(order_id, tracking_info)
        return result
    except Exception as e:
        logger.error(f"Error updating tracking: {e}")
        raise HTTPException(status_code=500, detail="Failed to update tracking")


@router.post("/{order_id}/sync")
async def sync_tracking(
    order_id: str,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """
    Manually trigger tracking sync with supplier.
    """
    tracking = _tracker.get_tracking(order_id)
    if not tracking:
        raise HTTPException(status_code=404, detail="Order not found")

    supplier = tracking["current_tracking"].supplier
    background_tasks.add_task(_tracker.poll_supplier_status, order_id, supplier)

    return {
        "order_id": order_id,
        "sync_status": "in_progress",
        "message": f"Syncing with {supplier}...",
    }


@router.get("/orders/pending")
async def get_pending_orders(limit: int = 50, auth: AuthContext = Depends(require_auth)) -> list[dict]:
    """Get all pending orders for polling."""
    pending = []
    for order_id, tracking in _tracker.tracking_status.items():
        current_status = tracking["current_tracking"].status
        if current_status not in [DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED]:
            pending.append(
                {
                    "order_id": order_id,
                    "status": current_status.value,
                    "supplier": tracking["current_tracking"].supplier,
                }
            )
    return pending[:limit]


# Background task for periodic polling
async def poll_all_pending_orders() -> None:
    """Poll all pending orders for status updates."""
    logger.info("Starting periodic polling of pending orders")
    pending_orders = []

    for order_id, tracking in _tracker.tracking_status.items():
        current_status = tracking["current_tracking"].status
        if current_status not in [DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED]:
            pending_orders.append(
                {
                    "order_id": order_id,
                    "supplier": tracking["current_tracking"].supplier,
                }
            )

    for order in pending_orders:
        try:
            await _tracker.poll_supplier_status(order["order_id"], order["supplier"])
            await asyncio.sleep(0.5)  # Rate limiting
        except Exception as e:
            logger.error(f"Error polling {order['order_id']}: {e}")

    logger.info(f"Completed polling of {len(pending_orders)} pending orders")
