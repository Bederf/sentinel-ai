"""
Pydantic models for Niagara integration (BACnet/IP and oBIX).

Defines request/response models for BACnet device discovery, point operations,
COV subscriptions, and oBIX REST API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class OBIXConfig(BaseModel):
    """Configuration for oBIX connection to Niagara server."""

    host: str = Field(..., description="Niagara server hostname or IP")
    port: int = Field(80, description="Niagara server port", ge=1, le=65535)
    username: str = Field("", description="Niagara username")
    password: str = Field("", description="Niagara password")
    use_https: bool = Field(False, description="Use HTTPS for connection")
    timeout: int = Field(30, description="Request timeout in seconds", ge=1, le=300)
    verify_ssl: bool = Field(True, description="Verify SSL certificates")


# ---------------------------------------------------------------------------
# Point Values
# ---------------------------------------------------------------------------

class OBIXPointValue(BaseModel):
    """Response for a single oBIX point value."""

    point_path: str = Field(..., description="oBIX point path")
    value: Any = Field(None, description="Current point value")
    status: str = Field("ok", description="Point status (ok, alarm, down, etc.)")
    type: str = Field("unknown", description="oBIX value type (real, int, bool, str, enum)")
    name: str = Field("", description="Point display name")
    timestamp: str = Field("", description="Timestamp of the reading (ISO 8601)")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class OBIXHistoryRequest(BaseModel):
    """Request parameters for historical data query."""

    point_path: str = Field(..., description="History path (e.g., histories/temperature1)")
    start_datetime: Optional[datetime] = Field(None, description="Start of query range")
    end_datetime: Optional[datetime] = Field(None, description="End of query range")
    limit: Optional[int] = Field(None, description="Maximum records to return", ge=1, le=10000)


class OBIXHistoryData(BaseModel):
    """A single historical data record."""

    timestamp: str = Field(..., description="Record timestamp (ISO 8601)")
    value: Any = Field(None, description="Recorded value")
    quality: str = Field("good", description="Data quality (good, bad, uncertain)")


class OBIXHistoryResponse(BaseModel):
    """Response for a history query."""

    point_path: str = Field(..., description="History path queried")
    count: int = Field(0, description="Number of records returned")
    records: List[OBIXHistoryData] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------

class OBIXAlarm(BaseModel):
    """A single oBIX alarm record."""

    alarm_id: Optional[str] = Field(None, description="Alarm identifier")
    timestamp: Optional[str] = Field(None, description="Alarm timestamp (ISO 8601)")
    severity: str = Field("unknown", description="Alarm severity (critical, warning, info)")
    priority: int = Field(5, description="Alarm priority (1=highest, 5=lowest)")
    source: str = Field("", description="Alarm source path")
    message: str = Field("", description="Alarm display message")
    ack_state: str = Field("unknown", description="Acknowledgment state (acked, unacked)")


class OBIXAlarmRequest(BaseModel):
    """Request parameters for alarm history query."""

    start_datetime: Optional[datetime] = Field(None, description="Start of query range")
    end_datetime: Optional[datetime] = Field(None, description="End of query range")
    severity_filter: Optional[str] = Field(None, description="Filter by severity")
    priority_filter: Optional[int] = Field(None, description="Filter by priority level", ge=1, le=5)
    limit: int = Field(100, description="Maximum alarms to return", ge=1, le=1000)


class OBIXAlarmResponse(BaseModel):
    """Response for an alarm query."""

    count: int = Field(0, description="Number of alarms returned")
    alarms: List[OBIXAlarm] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Connection Status
# ---------------------------------------------------------------------------

class OBIXConnectionStatus(BaseModel):
    """oBIX connection health status."""

    connected: bool = Field(False, description="Whether currently connected")
    last_auth: Optional[str] = Field(None, description="Last authentication timestamp")
    server_version: Optional[str] = Field(None, description="Niagara server version")
    base_url: str = Field("", description="Server base URL")
    message: str = Field("", description="Status message")


class OBIXConfigResponse(BaseModel):
    """Response after configuring oBIX connection."""

    success: bool = Field(..., description="Whether configuration was applied")
    message: str = Field("", description="Status message")
    connected: bool = Field(False, description="Whether connected after config")


# ===========================================================================
# BACnet/IP Models
# ===========================================================================

# ---------------------------------------------------------------------------
# BACnet Device Discovery
# ---------------------------------------------------------------------------

class BACnetDeviceInfo(BaseModel):
    """A BACnet device discovered via WhoIs/IAm."""

    device_id: int = Field(..., description="BACnet device instance number")
    ip_address: str = Field(..., description="Device IP address")
    vendor_name: str = Field("Unknown", description="Device vendor name")
    model_name: str = Field("", description="Device model name")
    firmware_version: str = Field("", description="Device firmware version")
    object_name: str = Field("", description="BACnet object name")


class BACnetDiscoverRequest(BaseModel):
    """Request parameters for BACnet device discovery."""

    timeout: float = Field(5.0, description="Discovery timeout in seconds", ge=1.0, le=30.0)


class BACnetDiscoverResponse(BaseModel):
    """Response for BACnet device discovery."""

    count: int = Field(0, description="Number of devices discovered")
    devices: List[BACnetDeviceInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# BACnet Points
# ---------------------------------------------------------------------------

class BACnetPointInfo(BaseModel):
    """A BACnet point/object discovered on a device."""

    object_type: str = Field(..., description="BACnet object type (e.g., analogInput)")
    instance: int = Field(..., description="Object instance number")
    name: str = Field("", description="Point display name")
    description: str = Field("", description="Point description")
    units: str = Field("", description="Engineering units")
    present_value: Optional[Any] = Field(None, description="Current value")
    writable: bool = Field(False, description="Whether the point is writable")


class BACnetPointDiscoveryRequest(BaseModel):
    """Request parameters for point discovery on a device."""

    object_types: Optional[List[str]] = Field(
        None,
        description="Filter by object types (e.g., ['analogInput', 'analogValue'])",
    )
    use_cache: bool = Field(True, description="Use cached point list if available")


class BACnetPointDiscoveryResponse(BaseModel):
    """Response for point discovery."""

    device_id: int = Field(..., description="BACnet device instance number")
    count: int = Field(0, description="Number of points discovered")
    points: List[BACnetPointInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# BACnet Read/Write
# ---------------------------------------------------------------------------

class BACnetPointReadResponse(BaseModel):
    """Response for reading a single BACnet point."""

    device_id: int = Field(..., description="BACnet device instance number")
    object_type: str = Field(..., description="BACnet object type")
    instance: int = Field(..., description="Object instance number")
    property_name: str = Field("presentValue", description="Property read")
    value: Optional[Any] = Field(None, description="Point value")
    timestamp: str = Field("", description="Read timestamp (ISO 8601)")


class BACnetPointWriteRequest(BaseModel):
    """Request to write a value to a BACnet point."""

    value: Any = Field(..., description="Value to write")
    priority: int = Field(8, description="BACnet priority (1-16, default 8)", ge=1, le=16)


class BACnetPointWriteResponse(BaseModel):
    """Response for a BACnet write operation."""

    success: bool = Field(..., description="Whether the write succeeded")
    device_id: int = Field(..., description="BACnet device instance number")
    object_type: str = Field(..., description="BACnet object type")
    instance: int = Field(..., description="Object instance number")
    value: Any = Field(None, description="Value written")
    priority: int = Field(8, description="Priority used")
    message: str = Field("", description="Status message")


# ---------------------------------------------------------------------------
# BACnet COV Subscriptions
# ---------------------------------------------------------------------------

class BACnetCOVPoint(BaseModel):
    """A point to include in a COV subscription."""

    object_type: str = Field(..., description="BACnet object type")
    instance: int = Field(..., description="Object instance number")


class BACnetCOVSubscribeRequest(BaseModel):
    """Request to create a COV subscription."""

    device_id: int = Field(..., description="BACnet device instance number")
    points: List[BACnetCOVPoint] = Field(..., description="Points to subscribe to")
    lifetime: int = Field(60, description="Subscription lifetime in seconds", ge=10, le=3600)


class BACnetCOVSubscriptionResponse(BaseModel):
    """Response for COV subscription creation."""

    subscription_id: str = Field(..., description="Unique subscription identifier")
    device_id: int = Field(..., description="BACnet device instance number")
    points: List[BACnetCOVPoint] = Field(default_factory=list)
    lifetime: int = Field(60, description="Subscription lifetime in seconds")
    created_at: str = Field("", description="Creation timestamp (ISO 8601)")
    expires_at: str = Field("", description="Expiration timestamp (ISO 8601)")
    active: bool = Field(True, description="Whether subscription is active")


class BACnetCOVSubscriptionListResponse(BaseModel):
    """Response listing active COV subscriptions."""

    count: int = Field(0, description="Number of active subscriptions")
    subscriptions: List[BACnetCOVSubscriptionResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# BACnet Client Status
# ---------------------------------------------------------------------------

class BACnetClientStatus(BaseModel):
    """BACnet client health and status information."""

    started: bool = Field(False, description="Whether the client is running")
    port: int = Field(47808, description="BACnet port")
    ip: Optional[str] = Field(None, description="Bound IP address")
    active_subscriptions: int = Field(0, description="Number of active COV subscriptions")
    cached_devices: int = Field(0, description="Number of cached device point lists")
