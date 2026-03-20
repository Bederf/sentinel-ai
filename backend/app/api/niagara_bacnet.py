"""
Niagara BACnet/IP API endpoints.

REST API for interacting with Tridium Niagara JACE/Supervisor devices
via BACnet/IP protocol. Provides device discovery, point read/write,
and COV subscription management.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.models.niagara import (
    BACnetClientStatus,
    BACnetCOVPoint,
    BACnetCOVSubscribeRequest,
    BACnetCOVSubscriptionListResponse,
    BACnetCOVSubscriptionResponse,
    BACnetDeviceInfo,
    BACnetDiscoverRequest,
    BACnetDiscoverResponse,
    BACnetPointDiscoveryResponse,
    BACnetPointInfo,
    BACnetPointReadResponse,
    BACnetPointWriteRequest,
    BACnetPointWriteResponse,
    BACnetTestConnectionRequest,
)
from app.services.niagara.bacnet_client import (
    BACnetException,
    BACnetReadError,
    BACnetTimeoutError,
    BACnetWriteError,
    get_bacnet_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/niagara/bacnet", tags=["niagara-bacnet"])


# ---------------------------------------------------------------------------
# POST /api/niagara/bacnet/discover - Discover BACnet devices
# ---------------------------------------------------------------------------


@router.post("/discover", response_model=BACnetDiscoverResponse)
async def discover_devices(request: BACnetDiscoverRequest = BACnetDiscoverRequest()):
    """
    Discover BACnet devices on the network using WhoIs/IAm.

    Broadcasts a WhoIs request and collects IAm responses from
    Niagara JACE/Supervisor devices within the timeout period.
    """
    client = get_bacnet_client()

    if not client.is_running:
        raise HTTPException(
            status_code=503,
            detail="BACnet client is not started. Start the client first.",
        )

    try:
        discovered = await client.discover_devices(timeout=request.timeout)
        if request.host:
            normalized_host = request.host.strip().lower()
            discovered = [device for device in discovered if device.ip_address.lower().startswith(normalized_host)]

        devices = [
            BACnetDeviceInfo(
                device_id=d.device_id,
                ip_address=d.ip_address,
                vendor_name=d.vendor_name,
                model_name=d.model_name,
                firmware_version=d.firmware_version,
                object_name=d.object_name,
            )
            for d in discovered
        ]

        return BACnetDiscoverResponse(count=len(devices), devices=devices)

    except BACnetTimeoutError:
        return BACnetDiscoverResponse(count=0, devices=[])
    except BACnetException as e:
        logger.error("Device discovery failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/niagara/bacnet/test-connection - Test BACnet connectivity
# ---------------------------------------------------------------------------


@router.post("/test-connection", response_model=BACnetDiscoverResponse)
async def test_bacnet_connection(
    request: BACnetTestConnectionRequest = BACnetTestConnectionRequest(),
):
    """
    Test BACnet/IP connectivity by auto-starting the client and running WhoIs.

    Unlike POST /discover, this endpoint auto-starts the BACnet client if not
    running, making it suitable for the wizard's connection test step.
    """
    client = get_bacnet_client()

    if not client.is_running:
        try:
            await client.start()
        except BACnetException as e:
            raise HTTPException(
                status_code=503,
                detail=f"BACnet client failed to start: {e}",
            )

    try:
        discovered = await client.discover_devices(timeout=request.timeout)
        if request.host:
            normalized_host = request.host.strip().lower()
            discovered = [device for device in discovered if device.ip_address.lower().startswith(normalized_host)]

        devices = [
            BACnetDeviceInfo(
                device_id=d.device_id,
                ip_address=d.ip_address,
                vendor_name=d.vendor_name,
                model_name=d.model_name,
                firmware_version=d.firmware_version,
                object_name=d.object_name,
            )
            for d in discovered
        ]

        return BACnetDiscoverResponse(count=len(devices), devices=devices)

    except BACnetTimeoutError:
        return BACnetDiscoverResponse(count=0, devices=[])
    except BACnetException as e:
        logger.error("BACnet connection test failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/niagara/bacnet/devices/{device_id}/points - Discover points
# ---------------------------------------------------------------------------


@router.get(
    "/devices/{device_id}/points",
    response_model=BACnetPointDiscoveryResponse,
)
async def discover_device_points(
    device_id: int,
    object_type: str | None = Query(None, alias="type", description="Filter by BACnet object type"),
    use_cache: bool = Query(True, description="Use cached point list"),
):
    """
    Discover all BACnet objects/points on a device.

    Reads the device's objectList property to enumerate available
    points. Supports filtering by object type.
    """
    client = get_bacnet_client()

    if not client.is_running:
        raise HTTPException(
            status_code=503,
            detail="BACnet client is not started.",
        )

    try:
        object_types = [object_type] if object_type else None
        discovered = await client.read_point_list(
            device_id=device_id,
            object_types=object_types,
            use_cache=use_cache,
        )

        points = [
            BACnetPointInfo(
                object_type=p.object_type,
                instance=p.instance,
                name=p.name,
                description=p.description,
                units=p.units,
                present_value=p.present_value,
                writable=p.writable,
            )
            for p in discovered
        ]

        return BACnetPointDiscoveryResponse(
            device_id=device_id,
            count=len(points),
            points=points,
        )

    except BACnetException as e:
        logger.error("Point discovery failed for device %s: %s", device_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/niagara/bacnet/devices/{device_id}/points/{object_type}/{instance}
# ---------------------------------------------------------------------------


@router.get(
    "/devices/{device_id}/points/{object_type}/{instance}",
    response_model=BACnetPointReadResponse,
)
async def read_point(
    device_id: int,
    object_type: str,
    instance: int,
    property_name: str = Query("presentValue", description="BACnet property to read"),
):
    """
    Read a single point value from a BACnet device.

    Returns the current value of the specified object property.
    """
    client = get_bacnet_client()

    if not client.is_running:
        raise HTTPException(
            status_code=503,
            detail="BACnet client is not started.",
        )

    try:
        value = await client.read_point(
            device_id=device_id,
            object_type=object_type,
            instance=instance,
            property_name=property_name,
        )

        return BACnetPointReadResponse(
            device_id=device_id,
            object_type=object_type,
            instance=instance,
            property_name=property_name,
            value=value,
            timestamp=datetime.utcnow().isoformat(),
        )

    except BACnetTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Read timed out: {e}")
    except BACnetReadError as e:
        raise HTTPException(status_code=502, detail=f"Read error: {e}")
    except BACnetException as e:
        logger.error("Point read failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/niagara/bacnet/devices/{device_id}/points/{object_type}/{instance}/write
# ---------------------------------------------------------------------------


@router.post(
    "/devices/{device_id}/points/{object_type}/{instance}/write",
    response_model=BACnetPointWriteResponse,
)
async def write_point(
    device_id: int,
    object_type: str,
    instance: int,
    request: BACnetPointWriteRequest,
):
    """
    Write a value to a BACnet point with priority array support.

    Uses BACnet priority arrays for conflict resolution.
    Default priority 8 (manual operator commands).
    """
    client = get_bacnet_client()

    if not client.is_running:
        raise HTTPException(
            status_code=503,
            detail="BACnet client is not started.",
        )

    try:
        success = await client.write_point(
            device_id=device_id,
            object_type=object_type,
            instance=instance,
            value=request.value,
            priority=request.priority,
        )

        return BACnetPointWriteResponse(
            success=success,
            device_id=device_id,
            object_type=object_type,
            instance=instance,
            value=request.value,
            priority=request.priority,
            message=f"Value written to {object_type},{instance} on device {device_id}",
        )

    except BACnetTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Write timed out: {e}")
    except BACnetWriteError as e:
        raise HTTPException(status_code=502, detail=f"Write error: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except BACnetException as e:
        logger.error("Point write failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /api/niagara/bacnet/subscribe - Create COV subscription
# ---------------------------------------------------------------------------


@router.post("/subscribe", response_model=BACnetCOVSubscriptionResponse)
async def create_cov_subscription(request: BACnetCOVSubscribeRequest):
    """
    Create a Change-of-Value (COV) subscription for real-time updates.

    Subscribes to value changes on the specified points.
    Subscriptions are automatically renewed before expiry.
    """
    client = get_bacnet_client()

    if not client.is_running:
        raise HTTPException(
            status_code=503,
            detail="BACnet client is not started.",
        )

    try:
        # Convert model points to tuples for the client
        point_tuples = [(p.object_type, p.instance) for p in request.points]

        # Use a default callback that logs updates
        async def _log_callback(point_key: str, value):
            logger.info("COV update: %s = %s", point_key, value)

        sub = await client.subscribe_to_points(
            device_id=request.device_id,
            points=point_tuples,
            callback=_log_callback,
            lifetime=request.lifetime,
        )

        return BACnetCOVSubscriptionResponse(
            subscription_id=sub.subscription_id,
            device_id=sub.device_id,
            points=[BACnetCOVPoint(object_type=ot, instance=inst) for ot, inst in sub.points],
            lifetime=sub.lifetime,
            created_at=sub.created_at.isoformat(),
            expires_at=sub.expires_at.isoformat(),
            active=sub.active,
        )

    except BACnetException as e:
        logger.error("COV subscription failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/niagara/bacnet/subscriptions - List active subscriptions
# ---------------------------------------------------------------------------


@router.get("/subscriptions", response_model=BACnetCOVSubscriptionListResponse)
async def list_cov_subscriptions():
    """
    List all active COV subscriptions.
    """
    client = get_bacnet_client()
    active_subs = client.list_subscriptions()

    subscriptions = [
        BACnetCOVSubscriptionResponse(
            subscription_id=sub.subscription_id,
            device_id=sub.device_id,
            points=[BACnetCOVPoint(object_type=ot, instance=inst) for ot, inst in sub.points],
            lifetime=sub.lifetime,
            created_at=sub.created_at.isoformat(),
            expires_at=sub.expires_at.isoformat(),
            active=sub.active,
        )
        for sub in active_subs
    ]

    return BACnetCOVSubscriptionListResponse(
        count=len(subscriptions),
        subscriptions=subscriptions,
    )


# ---------------------------------------------------------------------------
# DELETE /api/niagara/bacnet/subscribe/{subscription_id} - Cancel subscription
# ---------------------------------------------------------------------------


@router.delete("/subscribe/{subscription_id}")
async def cancel_cov_subscription(subscription_id: str):
    """
    Cancel an active COV subscription.

    Stops automatic renewal and removes the subscription.
    """
    client = get_bacnet_client()

    cancelled = await client.cancel_subscription(subscription_id)

    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail=f"Subscription {subscription_id} not found",
        )

    return {"success": True, "message": f"Subscription {subscription_id} cancelled"}


# ---------------------------------------------------------------------------
# GET /api/niagara/bacnet/status - Client status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=BACnetClientStatus)
async def get_bacnet_status():
    """
    Get BACnet client health and status information.
    """
    client = get_bacnet_client()
    status = client.get_status()

    return BACnetClientStatus(
        started=status["started"],
        port=status["port"],
        ip=status.get("ip"),
        active_subscriptions=status["active_subscriptions"],
        cached_devices=status["cached_devices"],
    )
