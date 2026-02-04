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
