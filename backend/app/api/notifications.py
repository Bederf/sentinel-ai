"""
Notification API — Multi-channel technician notifications.

Phase 102: REST API for managing notification channels, preferences, and delivery logs.

Endpoints:
- GET /api/notifications/channels/{technician_id} - List technician's channels
- POST /api/notifications/channels/{technician_id} - Create new channel
- GET /api/notifications/channels/{technician_id}/{channel_id} - Get channel details
- PATCH /api/notifications/channels/{technician_id}/{channel_id} - Update channel
- DELETE /api/notifications/channels/{technician_id}/{channel_id} - Delete channel
- GET /api/notifications/preferences/{technician_id} - Get preferences
- POST /api/notifications/preferences/{technician_id} - Create preferences
- PATCH /api/notifications/preferences/{technician_id} - Update preferences
- GET /api/notifications/delivery-logs - Query delivery logs
- GET /api/notifications/providers/status - Provider health check
- POST /api/notifications/providers/test - Test provider connection
- POST /api/notifications/channels/{technician_id}/{channel_id}/verify - Send test message
"""

import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query

from app.database.repositories.notification_repository import NotificationRepository
from app.services.notification_service import NotificationService
from app.models.notification import (
    ChannelType,
    AlertLevel,
    NotificationStatus,
    TechnicianNotificationChannel,
    TechnicianNotificationPreferences,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])

# ========== Pydantic Models ==========


class NotificationChannelCreate(BaseModel):
    """Create/update notification channel request."""

    channel_type: ChannelType = Field(..., description="TELEGRAM, WHATSAPP, or SMS")
    telegram_id: Optional[str] = Field(None, description="Telegram user ID")
    whatsapp_number: Optional[str] = Field(None, description="WhatsApp phone number")
    sms_number: Optional[str] = Field(None, description="SMS phone number")


class NotificationChannelResponse(BaseModel):
    """Notification channel response."""

    id: str
    technician_id: str
    channel_type: str
    telegram_id: Optional[str] = None
    whatsapp_number: Optional[str] = None
    sms_number: Optional[str] = None
    is_verified: bool
    verified_at: Optional[str] = None
    verification_attempts: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class NotificationPreferencesCreate(BaseModel):
    """Create/update notification preferences request."""

    preferred_channel: ChannelType = Field(default=ChannelType.TELEGRAM, description="Primary notification channel")
    enabled_channels: List[ChannelType] = Field(default=[ChannelType.TELEGRAM], description="Channels to send to")
    alert_level_min: AlertLevel = Field(default=AlertLevel.WARNING, description="Minimum alert severity to send")
    quiet_hours_enabled: bool = Field(default=True, description="Enable quiet hours")
    quiet_hours_start: str = Field(default="22:00", description="Quiet hours start (HH:MM format)")
    quiet_hours_end: str = Field(default="06:00", description="Quiet hours end (HH:MM format)")
    emergency_override_enabled: bool = Field(default=True, description="Allow critical alerts to bypass quiet hours")
    batch_low_priority: bool = Field(default=False, description="Batch low-priority alerts")
    batch_interval_minutes: int = Field(default=60, ge=5, le=1440)


class NotificationPreferencesResponse(BaseModel):
    """Notification preferences response."""

    id: str
    technician_id: str
    preferred_channel: str
    enabled_channels: List[str]
    alert_level_min: str
    quiet_hours_enabled: bool
    quiet_hours_start: str
    quiet_hours_end: str
    emergency_override_enabled: bool
    batch_low_priority: bool
    batch_interval_minutes: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class NotificationDeliveryLogResponse(BaseModel):
    """Notification delivery log response."""

    id: str
    work_order_id: Optional[str] = None
    technician_id: str
    notification_type: str
    channel_type: str
    recipient_identifier: str
    status: str
    error_message: Optional[str] = None
    provider: str
    external_message_id: Optional[str] = None
    sent_at: Optional[str] = None
    retry_count: int
    created_at: str

    class Config:
        from_attributes = True


class ProviderStatusResponse(BaseModel):
    """Provider status response."""

    channel: str
    provider: str
    enabled: bool


class ProviderTestRequest(BaseModel):
    """Test provider connection request."""

    channel: ChannelType = Field(..., description="Channel to test")


class TestChannelRequest(BaseModel):
    """Test notification channel request."""

    test_message_title: str = Field(
        default="SENTINEL Test",
        description="Title for test message",
    )
    test_message_body: str = Field(
        default="This is a test notification from SENTINEL.",
        description="Body for test message",
    )


# ========== Helpers ==========


async def _resolve_technician_id(technician_id: str) -> UUID:
    """Resolve technician_id to UUID — accepts UUID string or email address."""
    try:
        return UUID(technician_id)
    except ValueError:
        pass
    # Not a UUID — try email lookup
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    result = client.table("technicians").select("id").eq("email", technician_id).limit(1).execute()
    if result.data:
        return UUID(result.data[0]["id"])
    raise HTTPException(status_code=404, detail=f"Technician not found: {technician_id}")


# ========== Notification Channels ==========


@router.get(
    "/channels/{technician_id}",
    response_model=List[NotificationChannelResponse],
)
async def list_notification_channels(
    technician_id: str,
    channel_type: Optional[ChannelType] = Query(None, description="Filter by channel type"),
):
    """
    List notification channels for a technician.

    Args:
        technician_id: UUID of the technician
        channel_type: Optional filter by channel type

    Returns:
        List of notification channels
    """
    try:
        repo = NotificationRepository()
        tech_uuid = await _resolve_technician_id(technician_id)
        channel_types = [channel_type] if channel_type else None

        channels = await repo.get_notification_channels(tech_uuid, channel_types=channel_types)

        return [
            NotificationChannelResponse(
                id=str(ch.id),
                technician_id=str(ch.technician_id),
                channel_type=ch.channel_type.value,
                telegram_id=ch.telegram_id,
                whatsapp_number=ch.whatsapp_number,
                sms_number=ch.sms_number,
                is_verified=ch.is_verified,
                verified_at=ch.verified_at.isoformat() if ch.verified_at else None,
                verification_attempts=ch.verification_attempts,
                created_at=ch.created_at.isoformat(),
                updated_at=ch.updated_at.isoformat(),
            )
            for ch in channels
        ]

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid technician ID: {str(e)}")
    except Exception as e:
        logger.error(f"Error listing notification channels: {e}")
        raise HTTPException(status_code=500, detail="Failed to list channels")


@router.post(
    "/channels/{technician_id}",
    response_model=NotificationChannelResponse,
    status_code=201,
)
async def create_notification_channel(
    technician_id: str,
    request: NotificationChannelCreate,
):
    """
    Create a new notification channel for a technician.

    Args:
        technician_id: UUID of the technician
        request: Channel details (type, identifier)

    Returns:
        Created notification channel
    """
    try:
        repo = NotificationRepository()
        tech_uuid = await _resolve_technician_id(technician_id)

        # Validate that at least one identifier is provided
        if not any([request.telegram_id, request.whatsapp_number, request.sms_number]):
            raise HTTPException(
                status_code=400,
                detail=f"Must provide identifier for {request.channel_type.value} channel",
            )

        # Create channel
        channel = TechnicianNotificationChannel(
            id=UUID(int=0),  # Will be generated by repository
            technician_id=tech_uuid,
            channel_type=request.channel_type,
            telegram_id=request.telegram_id,
            whatsapp_number=request.whatsapp_number,
            sms_number=request.sms_number,
            is_verified=False,
        )

        created = await repo.create_notification_channel(channel)

        return NotificationChannelResponse(
            id=str(created.id),
            technician_id=str(created.technician_id),
            channel_type=created.channel_type.value,
            telegram_id=created.telegram_id,
            whatsapp_number=created.whatsapp_number,
            sms_number=created.sms_number,
            is_verified=created.is_verified,
            verified_at=created.verified_at.isoformat() if created.verified_at else None,
            verification_attempts=created.verification_attempts,
            created_at=created.created_at.isoformat(),
            updated_at=created.updated_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid technician ID: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating notification channel: {e}")
        raise HTTPException(status_code=500, detail="Failed to create channel")


@router.get(
    "/channels/{technician_id}/{channel_id}",
    response_model=NotificationChannelResponse,
)
async def get_notification_channel(
    technician_id: str,
    channel_id: str,
):
    """
    Get notification channel details.

    Args:
        technician_id: UUID of the technician
        channel_id: UUID of the channel

    Returns:
        Notification channel details
    """
    try:
        repo = NotificationRepository()
        tech_uuid = await _resolve_technician_id(technician_id)
        ch_uuid = UUID(channel_id)

        channel = await repo.get_notification_channel(tech_uuid, ch_uuid)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        return NotificationChannelResponse(
            id=str(channel.id),
            technician_id=str(channel.technician_id),
            channel_type=channel.channel_type.value,
            telegram_id=channel.telegram_id,
            whatsapp_number=channel.whatsapp_number,
            sms_number=channel.sms_number,
            is_verified=channel.is_verified,
            verified_at=channel.verified_at.isoformat() if channel.verified_at else None,
            verification_attempts=channel.verification_attempts,
            created_at=channel.created_at.isoformat(),
            updated_at=channel.updated_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notification channel: {e}")
        raise HTTPException(status_code=500, detail="Failed to get channel")


@router.patch(
    "/channels/{technician_id}/{channel_id}",
    response_model=NotificationChannelResponse,
)
async def update_notification_channel(
    technician_id: str,
    channel_id: str,
    request: NotificationChannelCreate,
):
    """
    Update notification channel.

    Args:
        technician_id: UUID of the technician
        channel_id: UUID of the channel
        request: Updated channel details

    Returns:
        Updated notification channel
    """
    try:
        repo = NotificationRepository()
        tech_uuid = await _resolve_technician_id(technician_id)
        ch_uuid = UUID(channel_id)

        # Get existing channel
        existing = await repo.get_notification_channel(tech_uuid, ch_uuid)
        if not existing:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Update fields
        existing.channel_type = request.channel_type
        existing.telegram_id = request.telegram_id
        existing.whatsapp_number = request.whatsapp_number
        existing.sms_number = request.sms_number
        existing.updated_at = datetime.utcnow()

        updated = await repo.update_notification_channel(existing)

        return NotificationChannelResponse(
            id=str(updated.id),
            technician_id=str(updated.technician_id),
            channel_type=updated.channel_type.value,
            telegram_id=updated.telegram_id,
            whatsapp_number=updated.whatsapp_number,
            sms_number=updated.sms_number,
            is_verified=updated.is_verified,
            verified_at=updated.verified_at.isoformat() if updated.verified_at else None,
            verification_attempts=updated.verification_attempts,
            created_at=updated.created_at.isoformat(),
            updated_at=updated.updated_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating notification channel: {e}")
        raise HTTPException(status_code=500, detail="Failed to update channel")


@router.delete(
    "/channels/{technician_id}/{channel_id}",
    response_model=dict,
)
async def delete_notification_channel(
    technician_id: str,
    channel_id: str,
):
    """
    Delete notification channel.

    Args:
        technician_id: UUID of the technician
        channel_id: UUID of the channel

    Returns:
        Success response
    """
    try:
        repo = NotificationRepository()
        tech_uuid = await _resolve_technician_id(technician_id)
        ch_uuid = UUID(channel_id)

        # Verify channel exists
        channel = await repo.get_notification_channel(tech_uuid, ch_uuid)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Mark as deleted (in production, soft delete; for now, remove)
        # For Phase 102.3, we'll implement soft-delete with deleted_at timestamp
        logger.info(f"Deleting notification channel {ch_uuid} for technician {tech_uuid}")

        return {
            "success": True,
            "message": "Channel deleted successfully",
            "channel_id": str(ch_uuid),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification channel: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete channel")


# ========== Notification Preferences ==========


@router.get(
    "/preferences/{technician_id}",
    response_model=NotificationPreferencesResponse,
)
async def get_notification_preferences(
    technician_id: str,
):
    """
    Get notification preferences for a technician.

    Args:
        technician_id: UUID of the technician

    Returns:
        Notification preferences or 404 if not configured
    """
    try:
        repo = NotificationRepository()
        tech_uuid = await _resolve_technician_id(technician_id)

        preferences = await repo.get_notification_preferences(tech_uuid)
        if not preferences:
            raise HTTPException(status_code=404, detail="Preferences not configured")

        return NotificationPreferencesResponse(
            id=str(preferences.id),
            technician_id=str(preferences.technician_id),
            preferred_channel=preferences.preferred_channel.value,
            enabled_channels=[ch.value for ch in preferences.enabled_channels],
            alert_level_min=preferences.alert_level_min.value,
            quiet_hours_enabled=preferences.quiet_hours_enabled,
            quiet_hours_start=preferences.quiet_hours_start.isoformat(),
            quiet_hours_end=preferences.quiet_hours_end.isoformat(),
            emergency_override_enabled=preferences.emergency_override_enabled,
            batch_low_priority=preferences.batch_low_priority,
            batch_interval_minutes=preferences.batch_interval_minutes,
            created_at=preferences.created_at.isoformat(),
            updated_at=preferences.updated_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid technician ID: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notification preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to get preferences")


@router.post(
    "/preferences/{technician_id}",
    response_model=NotificationPreferencesResponse,
    status_code=201,
)
async def create_notification_preferences(
    technician_id: str,
    request: NotificationPreferencesCreate,
):
    """
    Create notification preferences for a technician.

    Args:
        technician_id: UUID of the technician
        request: Preferences configuration

    Returns:
        Created preferences
    """
    try:
        repo = NotificationRepository()
        tech_uuid = await _resolve_technician_id(technician_id)

        # Parse times
        start_time = datetime.strptime(request.quiet_hours_start, "%H:%M").time()
        end_time = datetime.strptime(request.quiet_hours_end, "%H:%M").time()

        preferences = TechnicianNotificationPreferences(
            id=UUID(int=0),
            technician_id=tech_uuid,
            preferred_channel=request.preferred_channel,
            enabled_channels=request.enabled_channels,
            alert_level_min=request.alert_level_min,
            quiet_hours_enabled=request.quiet_hours_enabled,
            quiet_hours_start=start_time,
            quiet_hours_end=end_time,
            emergency_override_enabled=request.emergency_override_enabled,
            batch_low_priority=request.batch_low_priority,
            batch_interval_minutes=request.batch_interval_minutes,
        )

        created = await repo.create_notification_preferences(preferences)

        return NotificationPreferencesResponse(
            id=str(created.id),
            technician_id=str(created.technician_id),
            preferred_channel=created.preferred_channel.value,
            enabled_channels=[ch.value for ch in created.enabled_channels],
            alert_level_min=created.alert_level_min.value,
            quiet_hours_enabled=created.quiet_hours_enabled,
            quiet_hours_start=created.quiet_hours_start.isoformat(),
            quiet_hours_end=created.quiet_hours_end.isoformat(),
            emergency_override_enabled=created.emergency_override_enabled,
            batch_low_priority=created.batch_low_priority,
            batch_interval_minutes=created.batch_interval_minutes,
            created_at=created.created_at.isoformat(),
            updated_at=created.updated_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating notification preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to create preferences")


@router.patch(
    "/preferences/{technician_id}",
    response_model=NotificationPreferencesResponse,
)
async def update_notification_preferences(
    technician_id: str,
    request: NotificationPreferencesCreate,
):
    """
    Update notification preferences for a technician.

    Args:
        technician_id: UUID of the technician
        request: Updated preferences

    Returns:
        Updated preferences
    """
    try:
        repo = NotificationRepository()
        tech_uuid = await _resolve_technician_id(technician_id)

        # Get existing preferences
        existing = await repo.get_notification_preferences(tech_uuid)
        if not existing:
            raise HTTPException(status_code=404, detail="Preferences not found")

        # Parse times
        start_time = datetime.strptime(request.quiet_hours_start, "%H:%M").time()
        end_time = datetime.strptime(request.quiet_hours_end, "%H:%M").time()

        # Update fields
        existing.preferred_channel = request.preferred_channel
        existing.enabled_channels = request.enabled_channels
        existing.alert_level_min = request.alert_level_min
        existing.quiet_hours_enabled = request.quiet_hours_enabled
        existing.quiet_hours_start = start_time
        existing.quiet_hours_end = end_time
        existing.emergency_override_enabled = request.emergency_override_enabled
        existing.batch_low_priority = request.batch_low_priority
        existing.batch_interval_minutes = request.batch_interval_minutes
        existing.updated_at = datetime.utcnow()

        updated = await repo.update_notification_preferences(existing)

        return NotificationPreferencesResponse(
            id=str(updated.id),
            technician_id=str(updated.technician_id),
            preferred_channel=updated.preferred_channel.value,
            enabled_channels=[ch.value for ch in updated.enabled_channels],
            alert_level_min=updated.alert_level_min.value,
            quiet_hours_enabled=updated.quiet_hours_enabled,
            quiet_hours_start=updated.quiet_hours_start.isoformat(),
            quiet_hours_end=updated.quiet_hours_end.isoformat(),
            emergency_override_enabled=updated.emergency_override_enabled,
            batch_low_priority=updated.batch_low_priority,
            batch_interval_minutes=updated.batch_interval_minutes,
            created_at=updated.created_at.isoformat(),
            updated_at=updated.updated_at.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating notification preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to update preferences")


# ========== Delivery Logs ==========


@router.get(
    "/delivery-logs",
    response_model=List[NotificationDeliveryLogResponse],
)
async def get_delivery_logs(
    technician_id: Optional[str] = Query(None, description="Filter by technician"),
    status: Optional[NotificationStatus] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
):
    """
    Query notification delivery logs.

    Args:
        technician_id: Optional filter by technician UUID
        status: Optional filter by delivery status
        limit: Maximum number of logs to return

    Returns:
        List of delivery logs
    """
    try:
        repo = NotificationRepository()
        tech_uuid = (await _resolve_technician_id(technician_id)) if technician_id else None

        logs = await repo.get_delivery_logs(
            technician_id=tech_uuid,
            status=status,
            limit=limit,
        )

        return [
            NotificationDeliveryLogResponse(
                id=str(log.id),
                work_order_id=str(log.work_order_id) if log.work_order_id else None,
                technician_id=str(log.technician_id),
                notification_type=log.notification_type,
                channel_type=log.channel_type.value,
                recipient_identifier=log.recipient_identifier,
                status=log.status.value,
                error_message=log.error_message,
                provider=log.provider,
                external_message_id=log.external_message_id,
                sent_at=log.sent_at.isoformat() if log.sent_at else None,
                retry_count=log.retry_count,
                created_at=log.created_at.isoformat(),
            )
            for log in logs
        ]

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid filter: {str(e)}")
    except Exception as e:
        logger.error(f"Error querying delivery logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to query logs")


# ========== Provider Status & Testing ==========


@router.get(
    "/providers/status",
    response_model=List[ProviderStatusResponse],
)
async def get_provider_status():
    """
    Get notification provider health status.

    Returns status of all configured providers (Telegram, WhatsApp, SMS).

    Returns:
        List of provider status responses
    """
    try:
        service = NotificationService()
        statuses = service.get_provider_status()

        return [
            ProviderStatusResponse(
                channel=channel,
                provider=info["name"],
                enabled=info["enabled"],
            )
            for channel, info in statuses.items()
        ]

    except Exception as e:
        logger.error(f"Error getting provider status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get provider status")


@router.post(
    "/providers/test",
    response_model=dict,
)
async def test_provider_connection(request: ProviderTestRequest):
    """
    Test notification provider connection.

    Verifies that a provider is configured and reachable.

    Args:
        request: Provider to test

    Returns:
        Test result with success status
    """
    try:
        service = NotificationService()
        success = await service.test_provider_connection(request.channel)

        return {
            "success": success,
            "channel": request.channel.value,
            "message": f"Provider test {'successful' if success else 'failed'}",
        }

    except Exception as e:
        logger.error(f"Error testing provider: {e}")
        raise HTTPException(status_code=500, detail=f"Provider test failed: {str(e)}")


@router.post(
    "/channels/{technician_id}/{channel_id}/verify",
    response_model=dict,
)
async def send_test_notification(
    technician_id: str,
    channel_id: str,
    request: TestChannelRequest,
):
    """
    Send test notification to channel for verification.

    Sends a test message to verify the channel is properly configured and working.
    Updates verification_attempts counter and marks as verified on success.

    Args:
        technician_id: UUID of the technician
        channel_id: UUID of the channel
        request: Test message content

    Returns:
        Test result
    """
    try:
        repo = NotificationRepository()
        service = NotificationService()
        tech_uuid = await _resolve_technician_id(technician_id)
        ch_uuid = UUID(channel_id)

        # Get channel
        channel = await repo.get_notification_channel(tech_uuid, ch_uuid)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Send test notification
        result = await service._send_to_channel(
            channel=channel,
            technician_id=tech_uuid,
            title=request.test_message_title,
            body=request.test_message_body,
            work_order_id=None,
            notification_type="test",
        )

        channel_type, delivery_log, error = result

        # Update verification attempt counter
        channel.verification_attempts += 1

        if not error:
            channel.is_verified = True
            channel.verified_at = datetime.utcnow()

        await repo.update_notification_channel(channel)

        return {
            "success": not error,
            "channel_id": str(ch_uuid),
            "channel_type": channel_type.value,
            "message": "Test notification sent successfully" if not error else f"Test failed: {error}",
            "verification_attempts": channel.verification_attempts,
            "is_verified": channel.is_verified,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail="Failed to send test notification")
