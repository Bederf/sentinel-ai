from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.adapters.residential import build_adapter
from app.database.supabase_client import get_supabase_client
from app.middleware.auth_middleware import require_role
from app.services.encryption_service import get_encryption_service
from app.services.residential.bridge_scheduler import (
    add_residential_polling_job,
    remove_residential_polling_job,
)
from app.services.residential.mqtt_provisioner import get_mqtt_provisioner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/residential", tags=["residential-onboarding"])

_PLATFORMS: dict[str, dict[str, Any]] = {
    "solarman": {
        "label": "SOLARMAN",
        "description": "SOLARMAN Global OpenAPI (inverters, batteries, loggers)",
        "auth_fields": [
            {"key": "email", "label": "Account Email", "type": "email", "required": True},
            {"key": "password", "label": "Account Password", "type": "password", "required": True},
        ],
    },
    "victron": {
        "label": "Victron VRM",
        "description": "Victron Energy Remote Monitoring (VRM portal)",
        "auth_fields": [
            {"key": "username", "label": "VRM Portal username/email", "type": "email", "required": True},
            {"key": "password", "label": "VRM Account Password", "type": "password", "required": True},
        ],
    },
    "growatt": {
        "label": "Growatt",
        "description": "Growatt server API",
        "auth_fields": [
            {"key": "username", "label": "Growatt Username", "type": "text", "required": True},
            {"key": "password", "label": "Growatt Password", "type": "password", "required": True},
        ],
    },
    "fronius": {
        "label": "Fronius Solar.web",
        "description": "Fronius Solar.web cloud monitoring",
        "auth_fields": [
            {"key": "access_key_id", "label": "Access Key ID", "type": "text", "required": True},
            {"key": "access_key_value", "label": "Access Key Value", "type": "password", "required": True},
            {"key": "pv_system_id", "label": "PV System ID", "type": "text", "required": True},
        ],
    },
    "other": {
        "label": "Other",
        "description": "Unsupported platform — manual configuration required",
        "auth_fields": [],
    },
}

_DISCOVERY_TIMEOUT_SECONDS = 30

# Retained MQTT topics cleared on site deactivation
_RETAINED_TOPIC_PATTERNS = [
    "sentinel/{site_id}/energy/pv_power_w",
    "sentinel/{site_id}/energy/battery_soc_pct",
    "sentinel/{site_id}/energy/battery_power_w",
    "sentinel/{site_id}/energy/grid_power_w",
    "sentinel/{site_id}/energy/load_power_w",
    "sentinel/{site_id}/energy/grid_voltage_v",
    "sentinel/{site_id}/energy/last_updated",
    "sentinel/{site_id}/loadshedding/stage",
    "sentinel/{site_id}/loadshedding/next_slot",
    "sentinel/{site_id}/loadshedding/source",
]


def _encrypt_site_config(config: dict) -> str:
    return get_encryption_service().encrypt(json.dumps(config))


class OnboardRequest(BaseModel):
    site_id: str
    platform: str
    deployment_tier: str  # full_simbiot | cloud_only
    site_config: dict  # credentials + platform-specific config — encrypted before DB write
    eskom_area_code: str | None = None
    tariff_type: str | None = None
    polling_interval_seconds: int = 300
    chat_id: int | None = None


@router.get("/platforms")
async def get_platforms() -> dict:
    return {
        "platforms": [
            {"id": pid, **meta}
            for pid, meta in _PLATFORMS.items()
        ]
    }


@router.post("/onboard", dependencies=[Depends(require_role(4))])
async def onboard_residential_site(request: OnboardRequest) -> dict:
    if request.platform not in _PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {request.platform}")

    extra: dict = {}
    if request.platform == "solarman":
        from app.config.settings import settings as _settings
        extra = {"app_id": _settings.solarman_app_id, "app_secret": _settings.solarman_app_secret}

    try:
        adapter = build_adapter(request.platform, request.site_config, **extra)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        ok = await asyncio.wait_for(adapter.authenticate(), timeout=_DISCOVERY_TIMEOUT_SECONDS)
        if not ok:
            raise HTTPException(status_code=401, detail="Platform authentication failed — check credentials")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Platform authentication timed out (30s)") from None

    try:
        manifests = await asyncio.wait_for(
            adapter.discover_devices(), timeout=_DISCOVERY_TIMEOUT_SECONDS
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Device discovery timed out (30s)") from None

    supabase = get_supabase_client()

    site_row = {
        "site_id": request.site_id,
        "platform": request.platform,
        "deployment_tier": request.deployment_tier,
        "site_config": _encrypt_site_config(request.site_config),  # encrypted at rest
        "eskom_area_code": request.eskom_area_code,
        "tariff_type": request.tariff_type,
        "polling_interval_seconds": request.polling_interval_seconds,
        "is_active": True,
        "chat_id": request.chat_id,
        "notification_channel": "telegram",
        "onboarding_method": "wizard",
    }

    result = supabase.table("residential_sites").upsert(site_row, on_conflict="site_id").execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create residential site record")

    residential_site_id = result.data[0]["id"]

    device_rows = [
        {
            "residential_site_id": residential_site_id,
            "device_id": m.device_id,
            "device_name": m.device_name,
            "device_type": m.device_type,
            "capabilities": m.capabilities,
        }
        for m in manifests
    ]
    if device_rows:
        supabase.table("residential_devices").insert(device_rows).execute()

    try:
        get_mqtt_provisioner().provision_site(request.site_id)
    except Exception as exc:
        logger.warning("MQTT ACL provisioning failed for %s: %s", request.site_id, exc)

    if request.deployment_tier == "cloud_only":
        try:
            add_residential_polling_job(
                site_id=request.site_id,
                adapter=adapter,
                interval_seconds=request.polling_interval_seconds,
            )
        except Exception as exc:
            logger.warning("Failed to schedule residential polling for %s: %s", request.site_id, exc)

    return {
        "status": "onboarded",
        "site_id": request.site_id,
        "residential_site_id": residential_site_id,
        "devices_discovered": len(manifests),
        "platform": request.platform,
        "deployment_tier": request.deployment_tier,
        "polling_interval_seconds": request.polling_interval_seconds,
    }


@router.post("/deactivate/{site_id}", dependencies=[Depends(require_role(4))])
async def deactivate_residential_site(site_id: str) -> dict:
    """Full teardown of a residential site — stops polling, revokes ACL, clears retained MQTT, marks inactive."""
    supabase = get_supabase_client()

    # Check current state
    existing = supabase.table("residential_sites").select("id,is_active").eq("site_id", site_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"Residential site not found: {site_id}")

    if not existing.data[0]["is_active"]:
        return {"status": "already_inactive", "site_id": site_id}

    # 1. Stop APScheduler polling job
    try:
        remove_residential_polling_job(site_id)
    except Exception as exc:
        logger.warning("Could not remove polling job for %s: %s", site_id, exc)

    # 2. Revoke Mosquitto ACL
    try:
        get_mqtt_provisioner().revoke_site(site_id)
    except Exception as exc:
        logger.error("MQTT ACL revocation failed for %s (continuing): %s", site_id, exc)

    # 3. Clear all retained MQTT topics
    topics_cleared = 0
    try:
        from app.config.settings import settings as _settings

        if mqtt is not None:
            client = mqtt.Client(client_id=f"sentinel-residential-deactivate-{site_id}")
            if _settings.residential_mqtt_username:
                client.username_pw_set(_settings.residential_mqtt_username, _settings.residential_mqtt_password)
            client.connect(_settings.residential_mqtt_broker or "127.0.0.1", _settings.residential_mqtt_port, keepalive=10)
            for pattern in _RETAINED_TOPIC_PATTERNS:
                topic = pattern.format(site_id=site_id)
                info = client.publish(topic, None, qos=1, retain=True)
                info.wait_for_publish(timeout=2.0)
                topics_cleared += 1
            client.disconnect()
    except Exception as exc:
        logger.warning("Failed to clear retained MQTT topics for %s: %s", site_id, exc)

    # 4. Mark inactive in DB
    import datetime as _dt
    deactivated_at = _dt.datetime.utcnow().isoformat()
    supabase.table("residential_sites").update({"is_active": False}).eq("site_id", site_id).execute()

    logger.info("Residential site deactivated: %s (topics_cleared=%d)", site_id, topics_cleared)

    return {
        "status": "deactivated",
        "site_id": site_id,
        "deactivated_at": deactivated_at,
        "topics_cleared": topics_cleared,
    }


# paho imported at module level for deactivation's null-publish use
try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # type: ignore[assignment]
