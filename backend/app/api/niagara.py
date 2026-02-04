"""
Niagara oBIX API endpoints.

REST API for interacting with Tridium Niagara via oBIX protocol.
Provides point reading, historical data retrieval, alarm history,
and connection management.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.niagara import (
    OBIXAlarm,
    OBIXAlarmRequest,
    OBIXAlarmResponse,
    OBIXConfig,
    OBIXConfigResponse,
    OBIXConnectionStatus,
    OBIXHistoryData,
    OBIXHistoryResponse,
    OBIXPointValue,
)
from app.services.niagara.obix_client import (
    OBIXAuthenticationError,
    OBIXConnectionError,
    OBIXParseError,
    OBIXPointNotFoundError,
    get_obix_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/niagara/obix", tags=["niagara-obix"])


# ---------------------------------------------------------------------------
# POST /api/niagara/obix/config - Configure oBIX connection
# ---------------------------------------------------------------------------

@router.post("/config", response_model=OBIXConfigResponse)
async def configure_obix(config: OBIXConfig):
    """
    Configure the oBIX connection to a Niagara server.

    Applies the configuration and attempts to authenticate.
    """
    try:
        client = get_obix_client()

        protocol = "https" if config.use_https else "http"
        base_url = f"{protocol}://{config.host}:{config.port}"

        client.configure(
            base_url=base_url,
            username=config.username,
            password=config.password,
            use_https=config.use_https,
            timeout=config.timeout,
        )

        # Attempt authentication
        try:
            client.authenticate()
            return OBIXConfigResponse(
                success=True,
                message=f"Connected to Niagara at {base_url}",
                connected=True,
            )
        except OBIXAuthenticationError as e:
            return OBIXConfigResponse(
                success=True,
                message=f"Configuration saved but authentication failed: {e}",
                connected=False,
            )

    except Exception as e:
        logger.error("Failed to configure oBIX: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/niagara/obix/status - Connection status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=OBIXConnectionStatus)
async def get_obix_status():
    """
    Check oBIX connection health and authentication status.
    """
    client = get_obix_client()
    status = client.check_connection()

    return OBIXConnectionStatus(
        connected=status.get("connected", False),
        last_auth=status.get("last_auth"),
        server_version=status.get("server_version"),
        base_url=status.get("base_url", ""),
        message=status.get("message", ""),
    )


# ---------------------------------------------------------------------------
# GET /api/niagara/obix/points/{point_path:path} - Read point value
# ---------------------------------------------------------------------------

@router.get("/points/{point_path:path}", response_model=OBIXPointValue)
async def read_obix_point(point_path: str):
    """
    Read a single point value via oBIX.

    The point_path is the oBIX path relative to /obix/config/.
    Example: config/points/temperature1
    """
    client = get_obix_client()

    if not client.is_authenticated:
        raise HTTPException(
            status_code=503,
            detail="oBIX client not authenticated. Configure connection first.",
        )

    try:
        result = client.read_point(point_path)

        return OBIXPointValue(
            point_path=result.get("path", point_path),
            value=result.get("value"),
            status=result.get("status", "ok"),
            type=result.get("type", "unknown"),
            name=result.get("name", ""),
            timestamp=result.get("timestamp", ""),
        )

    except OBIXPointNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OBIXParseError as e:
        raise HTTPException(status_code=502, detail=f"XML parse error: {e}")
    except OBIXConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Connection error: {e}")
    except OBIXAuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/niagara/obix/history - Get historical data
# ---------------------------------------------------------------------------

@router.get("/history", response_model=OBIXHistoryResponse)
async def read_obix_history(
    point_path: str = Query(..., description="History path (e.g., histories/temperature1)"),
    start: Optional[datetime] = Query(None, description="Start datetime (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="End datetime (ISO 8601)"),
    limit: Optional[int] = Query(None, description="Maximum records", ge=1, le=10000),
):
    """
    Retrieve historical data for a point via oBIX history service.

    Returns timestamped value records within the specified date range.
    """
    client = get_obix_client()

    if not client.is_authenticated:
        raise HTTPException(
            status_code=503,
            detail="oBIX client not authenticated. Configure connection first.",
        )

    try:
        records = client.read_history(
            history_path=point_path,
            start=start,
            end=end,
            limit=limit,
        )

        history_data = [
            OBIXHistoryData(
                timestamp=r.get("timestamp", ""),
                value=r.get("value"),
                quality=r.get("quality", "good"),
            )
            for r in records
        ]

        return OBIXHistoryResponse(
            point_path=point_path,
            count=len(history_data),
            records=history_data,
        )

    except OBIXPointNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OBIXParseError as e:
        raise HTTPException(status_code=502, detail=f"XML parse error: {e}")
    except OBIXConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Connection error: {e}")
    except OBIXAuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/niagara/obix/alarms - Get alarm history
# ---------------------------------------------------------------------------

@router.get("/alarms", response_model=OBIXAlarmResponse)
async def read_obix_alarms(
    start: Optional[datetime] = Query(None, description="Start datetime filter"),
    end: Optional[datetime] = Query(None, description="End datetime filter"),
    severity: Optional[str] = Query(None, description="Filter by severity (critical, warning, info)"),
    priority: Optional[int] = Query(None, description="Filter by priority (1-5)", ge=1, le=5),
    limit: int = Query(100, description="Maximum alarms to return", ge=1, le=1000),
):
    """
    Retrieve alarm history via oBIX alarm service.

    Supports filtering by date range, severity, and priority level.
    """
    client = get_obix_client()

    if not client.is_authenticated:
        raise HTTPException(
            status_code=503,
            detail="oBIX client not authenticated. Configure connection first.",
        )

    try:
        alarms = client.read_alarms(
            start=start,
            end=end,
            limit=limit,
            severity_filter=severity,
            priority_filter=priority,
        )

        alarm_models = [
            OBIXAlarm(
                alarm_id=a.get("alarm_id"),
                timestamp=a.get("timestamp"),
                severity=a.get("severity", "unknown"),
                priority=a.get("priority", 5),
                source=a.get("source", ""),
                message=a.get("message", ""),
                ack_state=a.get("ack_state", "unknown"),
            )
            for a in alarms
        ]

        return OBIXAlarmResponse(
            count=len(alarm_models),
            alarms=alarm_models,
        )

    except OBIXParseError as e:
        raise HTTPException(status_code=502, detail=f"XML parse error: {e}")
    except OBIXConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Connection error: {e}")
    except OBIXAuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))
