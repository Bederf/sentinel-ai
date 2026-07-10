"""SIMBIOT capabilities API.

Exposes normalized control capabilities for site/device point maps so UI and
policy systems can render/write from one BMS-agnostic contract.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)

from app.core.site_resolver import get_registered_site_ids
from app.database.supabase_client import get_supabase_client
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.services.simbiot import BmsConnectionConfig, create_bms_adapter
from app.services.simbiot_capability_sync_service import sync_site_capabilities_to_supabase
from app.services.site_onboarding_lifecycle import (
    begin_discovery,
    capability_sync,
    discovery_completed,
    discovery_failed,
    EntityNotFound,
    TransitionDenied,
    VersionConflict,
)

router = APIRouter(prefix="/api/simbiot", tags=["simbiot-capabilities"])


@router.get("/sites/{site_id}/capabilities")
async def get_site_capabilities(
    site_id: str,
    bms_vendor: str = Query("bacnet", description="BMS vendor/adapter alias"),
    host: str | None = Query(None, description="Optional BMS host/IP"),
    port: int | None = Query(None, description="Optional BMS port"),
    device_id: str | None = Query(None, description="Optional single-device filter"),
    commissioning: bool = Query(True, description="Allow onboarding-time capability discovery"),
    username: str | None = Query(None, description="Optional credential for bridge/Niagara auth"),
    password: str | None = Query(None, description="Optional credential or token for bridge/Niagara auth"),
) -> dict:
    """Return normalized capability map for a site."""
    adapter = create_bms_adapter(adapter_type=bms_vendor, bms_vendor=bms_vendor, device_ip=host)
    cfg = BmsConnectionConfig(
        site_id=site_id,
        source_type=bms_vendor,
        host=host,
        port=port,
        metadata={
            "commissioning": commissioning,
            "bms_vendor": bms_vendor,
            "token": password or username or "",
        },
    )

    # ── PLS: begin discovery intent ──────────────────────────
    pls_intent_id: str | None = None
    try:
        pls_res = await begin_discovery(
            site_id,
            actor="system",
            actor_type="service",
            reason="Capability discovery via API",
        )
        pls_intent_id = pls_res.get("intent_id")
    except (TransitionDenied, EntityNotFound, VersionConflict) as exc:
        logger.info("PLS skip for %s: %s", site_id, exc)
    except Exception as exc:
        logger.warning("PLS begin_discovery failed for %s: %s", site_id, exc)

    try:
        status = await adapter.connect(cfg)
        if not status.connected:
            raise HTTPException(status_code=503, detail=status.message or "SIMBIOT adapter unavailable")

        devices = await adapter.discover_devices()
        if device_id:
            devices = [d for d in devices if d.device_id == device_id]

        out_devices = []
        total_points = 0
        writable_points = 0

        for dev in devices:
            points = await adapter.discover_points(dev.device_id)
            point_items = []
            dev_writable = 0
            for p in points:
                total_points += 1
                if p.writable:
                    writable_points += 1
                    dev_writable += 1
                point_items.append(
                    {
                        "point_id": p.point_id,
                        "point_name": p.point_name,
                        "point_type": p.point_type,
                        "unit": p.unit,
                        "writable": p.writable,
                        "metadata": p.metadata,
                    }
                )

            out_devices.append(
                {
                    "device_id": dev.device_id,
                    "display_name": dev.display_name,
                    "protocol": dev.protocol,
                    "address": dev.address,
                    "metadata": dev.metadata,
                    "controllable": dev_writable > 0,
                    "point_count": len(point_items),
                    "writable_point_count": dev_writable,
                    "points": point_items,
                }
            )

        # Persist discovery session for attestation + freshness validation
        discovery_id = None
        try:
            payload_for_hash = json.dumps(
                {"devices": out_devices, "summary": {"devices": len(out_devices), "points": total_points}},
                sort_keys=True,
                separators=(",", ":"),
            )
            raw_hash = hashlib.sha256(payload_for_hash.encode("utf-8")).hexdigest()
            client = get_supabase_client()
            result = (
                client.table("site_discovery_sessions")
                .insert(
                    {
                        "site_id": site_id,
                        "adapter_type": adapter.adapter_id,
                        "host": host,
                        "port": port,
                        "device_count": len(out_devices),
                        "point_count": total_points,
                        "writable_point_count": writable_points,
                        "raw_response_hash": raw_hash,
                        "status": "active",
                    }
                )
                .execute()
            )
            if result.data:
                discovery_id = str(result.data[0]["discovery_id"])
                discovered_at = result.data[0]["discovered_at"]
        except Exception as exc:
            # Discovery session persistence is advisory — do not fail the capability call
            import logging

            logging.getLogger(__name__).warning("Failed to persist discovery session for %s: %s", site_id, exc)

        # ---- PLS: complete discovery outcome ------------------------
        if pls_intent_id:
            try:
                await discovery_completed(
                    site_id,
                    intent_id=pls_intent_id,
                    evidence_ref={
                        "devices": len(out_devices),
                        "points": total_points,
                        "writable_points": writable_points,
                        "discovery_id": str(discovery_id) if discovery_id else None,
                    },
                )
            except Exception as pls_exc:
                logger.warning("PLS discovery_completed failed for %s: %s", site_id, pls_exc)

        return {
            "site_id": site_id,
            "discovery_id": discovery_id,
            "discovered_at": discovered_at if discovery_id else None,
            "adapter_id": adapter.adapter_id,
            "adapter_type": adapter.adapter_id,
            "adapter_capabilities": {
                "supports_device_discovery": adapter.capabilities.supports_device_discovery,
                "supports_point_discovery": adapter.capabilities.supports_point_discovery,
                "supports_hierarchy_discovery": adapter.capabilities.supports_hierarchy_discovery,
                "supports_reads": adapter.capabilities.supports_reads,
                "supports_writes": adapter.capabilities.supports_writes,
                "supports_subscriptions": adapter.capabilities.supports_subscriptions,
                "supports_history": adapter.capabilities.supports_history,
            },
            "summary": {
                "devices": len(out_devices),
                "points": total_points,
                "writable_points": writable_points,
                "controllable_devices": sum(1 for d in out_devices if d["controllable"]),
            },
            "devices": out_devices,
        }
    except HTTPException:
        if pls_intent_id:
            with contextlib.suppress(Exception):
                await discovery_failed(site_id, intent_id=pls_intent_id, reason="Capability discovery rejected")
        raise
    except PermissionError as exc:
        if pls_intent_id:
            with contextlib.suppress(Exception):
                await discovery_failed(site_id, intent_id=pls_intent_id, reason=str(exc))
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConnectionError as exc:
        if pls_intent_id:
            with contextlib.suppress(Exception):
                await discovery_failed(site_id, intent_id=pls_intent_id, reason=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        if pls_intent_id:
            with contextlib.suppress(Exception):
                await discovery_failed(site_id, intent_id=pls_intent_id, reason=str(exc))
        raise HTTPException(status_code=500, detail=f"Capability discovery failed: {exc}") from exc
    finally:
        with contextlib.suppress(Exception):
            await adapter.disconnect()


@router.post("/sites/{site_id}/capabilities/sync")
async def sync_site_capabilities(
    site_id: str,
    bms_vendor: str = Query("bacnet", description="BMS vendor/adapter alias"),
    host: str | None = Query(None, description="Optional BMS host/IP"),
    port: int | None = Query(None, description="Optional BMS port"),
    commissioning: bool = Query(True, description="Allow onboarding-time capability discovery"),
) -> dict:
    """Backfill existing site equipment with latest SIMBIOT capability snapshot."""
    try:
        result = await sync_site_capabilities_to_supabase(
            site_code=site_id,
            bms_vendor=bms_vendor,
            host=host,
            port=port,
            commissioning=commissioning,
        )
        # ---- PLS: capability sync transition -----------------------
        try:
            await capability_sync(site_id)
        except Exception as pls_exc:
            logger.warning("PLS capability_sync failed for %s: %s", site_id, pls_exc)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Capability sync failed: {exc}") from exc


@router.post("/capabilities/sync-all")
async def sync_all_registered_sites_capabilities(
    bms_vendor: str = Query("bacnet", description="BMS vendor/adapter alias"),
    commissioning: bool = Query(True, description="Allow onboarding-time capability discovery"),
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
) -> dict:
    """Backfill all registered sites using currently configured adapter defaults."""
    site_ids = get_registered_site_ids()
    results = []
    for site_id in site_ids:
        try:
            result = await sync_site_capabilities_to_supabase(
                site_code=site_id,
                bms_vendor=bms_vendor,
                commissioning=commissioning,
            )
            results.append({"site_id": site_id, "ok": True, "result": result})
        except Exception as exc:
            results.append({"site_id": site_id, "ok": False, "error": str(exc)})

    return {
        "total_sites": len(site_ids),
        "success_count": sum(1 for r in results if r["ok"]),
        "failure_count": sum(1 for r in results if not r["ok"]),
        "results": results,
    }
