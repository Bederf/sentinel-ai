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
    "home_assistant": {
        "label": "Home Assistant",
        "description": "Home Assistant via WireGuard VPN (local gateway)",
        "auth_fields": [],
        # No auth fields — WireGuard handles network auth; entity mapping via bot
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
    return {"platforms": [{"id": pid, **meta} for pid, meta in _PLATFORMS.items()]}


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
        manifests = await asyncio.wait_for(adapter.discover_devices(), timeout=_DISCOVERY_TIMEOUT_SECONDS)
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
    # Schedule morning summary for all residential platforms
    try:
        from app.services.residential.bridge_scheduler import schedule_morning_summary

        schedule_morning_summary(request.site_id)
    except Exception as exc:
        logger.warning("Failed to schedule morning summary for %s: %s", request.site_id, exc)

    return {
        "status": "onboarded",
        "site_id": request.site_id,
        "residential_site_id": residential_site_id,
        "devices_discovered": len(manifests),
        "platform": request.platform,
        "deployment_tier": request.deployment_tier,
        "polling_interval_seconds": request.polling_interval_seconds,
    }


# ── setarea ─────────────────────────────────────────────────────────────────────

from app.services.residential.eskomsepush_client import validate_area_code as _validate_area_code  # noqa: E402


class SetareaRequest(BaseModel):
    site_id: str
    eskom_area_code: str


@router.patch("/setarea", dependencies=[Depends(require_role(4))])
async def setarea_residential_site(request: SetareaRequest) -> dict:
    """
    Update eskom_area_code on a residential site.
    Validates the area code via validate_area_code() (cached list, NOT live API)
    before saving.
    """
    # Validate area code first — checks _area_cache, not live API
    is_valid = await _validate_area_code(request.eskom_area_code)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Area code not found. Check eskomsepush.co.za and try again.")

    supabase = get_supabase_client()

    existing = supabase.table("residential_sites").select("id,is_active").eq("site_id", request.site_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"Residential site not found: {request.site_id}")

    if not existing.data[0]["is_active"]:
        raise HTTPException(status_code=400, detail="Site is not active.")

    supabase.table("residential_sites").update({"eskom_area_code": request.eskom_area_code}).eq(
        "site_id", request.site_id
    ).execute()

    logger.info("Updated eskom_area_code=%s for site_id=%s", request.eskom_area_code, request.site_id)

    return {"status": "updated", "eskom_area_code": request.eskom_area_code}


# ── deactivate ─────────────────────────────────────────────────────────────────


@router.post("/deactivate/{site_id}", dependencies=[Depends(require_role(4))])
async def deactivate_residential_site(site_id: str) -> dict:
    """Full teardown of a residential site — stops polling, revokes ACL, clears retained MQTT, marks inactive."""
    supabase = get_supabase_client()

    # Check current state
    existing = supabase.table("residential_sites").select("id,is_active,platform,ha_deployment_type").eq("site_id", site_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail=f"Residential site not found: {site_id}")

    if not existing.data[0]["is_active"]:
        return {"status": "already_inactive", "site_id": site_id}

    # 1. Mark inactive in DB first
    import datetime as _dt

    deactivated_at = _dt.datetime.utcnow().isoformat()
    supabase.table("residential_sites").update({"is_active": False}).eq("site_id", site_id).execute()

    # 2. Stop APScheduler jobs (poll + morning) — idempotent
    try:
        remove_residential_polling_job(site_id)
    except Exception as exc:
        logger.warning("Could not remove polling job for %s: %s", site_id, exc)
    try:
        from app.services.residential.bridge_scheduler import cancel_morning_summary

        cancel_morning_summary(site_id)
    except Exception as exc:
        logger.warning("Could not cancel morning job for %s: %s", site_id, exc)

    # 3. Revoke VPS MQTT credentials if applicable
    try:
        platform = existing.data[0].get("platform")
        deploy = existing.data[0].get("ha_deployment_type")
        if platform == "home_assistant" and deploy == "vps":
            get_mqtt_provisioner().revoke_vps_client(site_id)
    except Exception as exc:
        logger.warning("VPS credential revoke failed for %s: %s", site_id, exc)

    # 4. Revoke Mosquitto ACL (idempotent)
    try:
        get_mqtt_provisioner().revoke_site(site_id)
    except Exception as exc:
        logger.error("MQTT ACL revocation failed for %s (continuing): %s", site_id, exc)

    # 5. Clear all retained MQTT topics
    topics_cleared = 0
    try:
        from app.config.settings import settings as _settings

        if mqtt is not None:
            client = mqtt.Client(client_id=f"sentinel-residential-deactivate-{site_id}")
            if _settings.residential_mqtt_username:
                client.username_pw_set(_settings.residential_mqtt_username, _settings.residential_mqtt_password)
            client.connect(
                _settings.residential_mqtt_broker or "127.0.0.1", _settings.residential_mqtt_port, keepalive=10
            )
            for pattern in _RETAINED_TOPIC_PATTERNS:
                topic = pattern.format(site_id=site_id)
                info = client.publish(topic, None, qos=1, retain=True)
                info.wait_for_publish(timeout=2.0)
                topics_cleared += 1
            client.disconnect()
    except Exception as exc:
        logger.warning("Failed to clear retained MQTT topics for %s: %s", site_id, exc)

    logger.info("Residential site deactivated: %s (topics_cleared=%d)", site_id, topics_cleared)

    return {
        "status": "deactivated",
        "site_id": site_id,
        "deactivated_at": deactivated_at,
        "topics_cleared": topics_cleared,
    }


# ── WireGuard peer admin endpoints ────────────────────────────────────────────────

from app.services.residential.wireguard_peer_manager import WireGuardPeerManager  # noqa: E402


@router.post("/wireguard/activate/{site_id}", dependencies=[Depends(require_role(4))])
async def activate_wireguard_peer(site_id: str) -> dict:
    """
    Mark a WireGuard peer as active.

    Called by the operator AFTER adding the [Peer] block to /etc/wireguard/wg0.conf.
    This is a manual step — it's the operator who confirms the peer is in wg0.conf.

    Returns 400 if no pending peer exists for this site_id.
    """
    wg = WireGuardPeerManager()
    peer = wg.get_peer(site_id)

    if peer is None:
        raise HTTPException(status_code=404, detail=f"No WireGuard peer found for site: {site_id}")
    if peer.status == "active":
        return {"status": "already_active", "site_id": site_id, "assigned_ip": peer.assigned_ip}
    if peer.status == "revoked":
        raise HTTPException(
            status_code=400, detail=f"Peer for {site_id} is revoked. User must /connect again to register a new peer."
        )

    wg.activate_peer(site_id)

    logger.info("WireGuard peer activated: site_id=%s assigned_ip=%s", site_id, peer.assigned_ip)
    return {
        "status": "activated",
        "site_id": site_id,
        "assigned_ip": peer.assigned_ip,
    }


@router.get("/wireguard/pending", dependencies=[Depends(require_role(4))])
async def list_pending_wireguard_peers() -> dict:
    """
    List all pending WireGuard peers awaiting wg0.conf activation.
    Used by the operator to know which peers to add.
    """
    wg = WireGuardPeerManager()
    peers = wg.list_pending()
    return {
        "pending": [
            {
                "site_id": p.site_id,
                "assigned_ip": p.assigned_ip,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in peers
        ]
    }


# paho imported at module level for deactivation's null-publish use
try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # type: ignore[assignment]
