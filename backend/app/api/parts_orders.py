from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/parts-orders", tags=["parts-orders"])


class PartsOrderItem(BaseModel):
    part_name: str
    part_number: str
    manufacturer: str
    supplier: str
    quantity: int
    unit_price: str


class PartsOrder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    items: List[PartsOrderItem]
    total_amount: str
    technician_id: str
    site_id: str
    status: str = "pending_approval"  # pending_approval | approved | rejected | ordered | delivered
    created_at: datetime = Field(default_factory=datetime.now)
    requires_approval: bool = True
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    order_reference: Optional[str] = None


# In-memory storage for demo (TODO: replace with Supabase)
_orders_db: dict[str, PartsOrder] = {}


@router.post("/", response_model=PartsOrder)
async def create_parts_order(order: PartsOrder) -> PartsOrder:
    """
    Create parts order with approval workflow.

    Orders over R5,000 require supervisor approval.
    Orders under R5,000 are auto-approved.
    """
    # Parse total amount
    try:
        amount_str = order.total_amount.replace("R", "").replace(",", "").strip()
        amount = float(amount_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid total_amount format")

    # Check if approval needed
    requires_approval = amount > 5000

    order.status = "pending_approval" if requires_approval else "approved"
    order.requires_approval = requires_approval

    if not requires_approval:
        # Auto-approve and place order
        order.status = "approved"
        order.approved_at = datetime.now()
        order.order_reference = await _place_order_with_supplier(order)
        order.status = "ordered"

    # Save order to in-memory storage
    _orders_db[order.id] = order

    return order


@router.get("/", response_model=List[PartsOrder])
async def get_parts_orders(technician_id: str, status: Optional[str] = None) -> List[PartsOrder]:
    """Get parts orders for technician, optionally filtered by status"""
    orders = [order for order in _orders_db.values() if order.technician_id == technician_id]

    if status:
        orders = [order for order in orders if order.status == status]

    return orders


@router.get("/{order_id}", response_model=PartsOrder)
async def get_parts_order(order_id: str) -> PartsOrder:
    """Get a specific parts order"""
    if order_id not in _orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    return _orders_db[order_id]


@router.put("/{order_id}/approve", response_model=PartsOrder)
async def approve_order(order_id: str, approver_id: str) -> PartsOrder:
    """Approve pending order (supervisor action)"""
    if order_id not in _orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    order = _orders_db[order_id]

    if order.status != "pending_approval":
        raise HTTPException(status_code=400, detail="Order is not pending approval")

    # Update status to approved
    order.status = "approved"
    order.approved_by = approver_id
    order.approved_at = datetime.now()

    # Place order with supplier
    order.order_reference = await _place_order_with_supplier(order)
    order.status = "ordered"

    return order


@router.put("/{order_id}/reject", response_model=PartsOrder)
async def reject_order(order_id: str, reason: Optional[str] = None) -> PartsOrder:
    """Reject pending order (supervisor action)"""
    if order_id not in _orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    order = _orders_db[order_id]

    if order.status != "pending_approval":
        raise HTTPException(status_code=400, detail="Order is not pending approval")

    # Update status to rejected
    order.status = "rejected"

    return order


@router.get("/{order_id}/tracking", response_model=dict)
async def get_order_tracking(order_id: str) -> dict:
    """Get order tracking information"""
    if order_id not in _orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    order = _orders_db[order_id]

    # Build tracking info
    tracking = {
        "order_reference": order.order_reference or "N/A",
        "status": order.status,
        "supplier": order.items[0].supplier if order.items else "Unknown",
        "items": [{"name": item.part_name, "qty": item.quantity} for item in order.items],
        "tracking_number": f"TRK-{order.id[:8].upper()}" if order.status in ["shipped", "delivered"] else None,
        "estimated_delivery": "2-3 business days" if order.status == "ordered" else None,
    }

    return tracking


@router.post("/{order_id}/sync")
async def sync_order_status(order_id: str) -> dict:
    """
    Sync order status with supplier (called by webhook/polling).
    """
    if order_id not in _orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    order = _orders_db[order_id]

    # In production: Check order status with supplier via API
    # For now: simulate status progression
    status_progression = {"ordered": "shipped", "shipped": "delivered"}

    if order.status in status_progression:
        order.status = status_progression[order.status]

    return {"order_id": order_id, "status": order.status, "updated_at": datetime.now().isoformat()}


async def _place_order_with_supplier(order: PartsOrder) -> str:
    """
    Place order with supplier (mock implementation).
    Returns order reference number.
    """
    # In production: integrate with supplier APIs
    # For now: generate mock reference
    return f"ORD-{datetime.now().strftime('%Y%m%d')}-{order.id[:6].upper()}"
