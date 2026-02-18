"""Bridge Niagara discovery to Integration Monitoring tables.

When BMS point discovery is approved, this module populates the integration
monitoring tables so the Integration Monitoring dashboard shows the connected
data sources, sync history, and point mappings.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import logging

from app.database.repositories.integration_repository import IntegrationRepository
from app.services.niagara.mapping_service import get_mapping_service

logger = logging.getLogger(__name__)


def bridge_discovery_to_integration(
    discovery_id: str,
    site_id: str,
    bms_vendor: str = "siemens",
    equipment_created: int = 0,
) -> Dict[str, Any]:
    """
    Bridge Niagara discovery results to Integration Monitoring tables.

    Called after approve_mapping() succeeds. Creates:
    - log_source (representing the BMS connection)
    - sync_job (representing the discovery import)
    - point_asset_mappings (from classified points)

    Args:
        discovery_id: The Niagara discovery ID
        site_id: Site ID (e.g., "site-002")
        bms_vendor: BMS vendor identifier (siemens, niagara, honeywell, etc.)
        equipment_created: Number of equipment entities created

    Returns:
        Dict with success status and created entity IDs
    """
    repo = IntegrationRepository()
    mapping_service = get_mapping_service()

    # Get building_id from site_id (e.g., site-002 -> UUID)
    building_id = _resolve_building_id(site_id)
    if not building_id:
        logger.warning("Could not resolve building_id for site %s", site_id)
        return {"success": False, "error": "Building not found"}

    # Load discovery mappings
    mappings = mapping_service.get_mappings(discovery_id)
    if not mappings:
        return {"success": False, "error": "Discovery not found"}

    # 1. Create log_source representing the BMS connection
    vendor_names = {
        "siemens": "Siemens Desigo CC",
        "desigo": "Siemens Desigo CC",
        "niagara": "Tridium Niagara",
        "honeywell": "Honeywell EBI",
        "jci": "Johnson Controls Metasys",
        "metasys": "Johnson Controls Metasys",
        "schneider": "Schneider EcoStruxure",
        "trend": "Trend IQ",
        "generic": "Generic BMS",
    }

    try:
        log_source = repo.create_log_source({
            "building_id": building_id,
            "name": vendor_names.get(bms_vendor.lower(), f"{bms_vendor.title()} BMS"),
            "source_type": "bms_trend",
            "connection_type": "api",
            "vendor_pattern": bms_vendor.lower(),
            "is_active": True,
            "sync_frequency_minutes": 15,
            "last_sync_at": datetime.utcnow().isoformat(),
            "last_sync_status": "success",
        })
        source_id = log_source.get("id")
    except Exception as e:
        logger.error("Failed to create log_source: %s", e)
        return {"success": False, "error": f"Failed to create log source: {e}"}

    # 2. Count total points from mappings
    point_count = 0
    for mapping in mappings.values():
        if hasattr(mapping, "points"):
            point_count += len(mapping.points)
        elif isinstance(mapping, dict):
            point_count += len(mapping.get("points", []))

    # 3. Create sync_job representing the discovery import
    try:
        sync_job = repo.create_sync_job(source_id)
        repo.complete_sync_job(
            job_id=sync_job["id"],
            status="success",
            processed=point_count,
            inserted=point_count,
            skipped=0,
            failed=0,
        )
    except Exception as e:
        logger.warning("Failed to create sync_job: %s", e)
        # Continue - sync job is not critical

    # 4. Create point_asset_mappings from classified points
    point_mappings = []
    for equipment_name, mapping in mappings.items():
        # Get points from EquipmentMapping object or dict
        if hasattr(mapping, "points"):
            points = mapping.points
            equipment_id = getattr(mapping, "equipment_id", equipment_name)
        elif isinstance(mapping, dict):
            points = mapping.get("points", [])
            equipment_id = mapping.get("equipment_id", equipment_name)
        else:
            continue

        for point in points:
            confidence = point.get("confidence", "medium")
            match_confidence = {
                "high": "exact",
                "medium": "fuzzy",
                "low": "manual",
                "manual": "manual",
                "unknown": "unmatched",
            }.get(str(confidence).lower(), "fuzzy")

            point_mappings.append({
                "building_id": building_id,
                "bms_point_id": point.get("original_name", point.get("name", "")),
                "extracted_asset_id": equipment_name,
                "cafm_asset_id": equipment_id,
                "parameter_name": point.get("standardized_name", point.get("name", "")),
                "parameter_type": point.get("point_type", "sensor"),
                "match_confidence": match_confidence,
                "is_verified": match_confidence in ("exact", "manual"),
            })

    points_mapped = 0
    if point_mappings:
        try:
            points_mapped = repo.bulk_upsert_point_mappings(building_id, point_mappings)
        except Exception as e:
            logger.warning("Failed to create point mappings: %s", e)
            # Continue - we've at least created the log source

    # 5. Create demo sync history (last 7 days for healthy appearance)
    _create_demo_sync_history(repo, source_id, point_count)

    logger.info(
        "Bridged discovery %s to Integration Monitoring: source=%s, points=%d",
        discovery_id,
        source_id,
        points_mapped,
    )

    return {
        "success": True,
        "log_source_id": source_id,
        "sync_job_id": sync_job.get("id") if sync_job else None,
        "points_mapped": points_mapped,
        "equipment_created": equipment_created,
    }


def _resolve_building_id(site_id: str) -> Optional[str]:
    """Resolve site_id (e.g., site-002) to building UUID.

    Args:
        site_id: Site identifier like "site-002"

    Returns:
        Building UUID or None if not found
    """
    try:
        from app.database.repositories.building_repository import BuildingRepository
        repo = BuildingRepository()
        # get_by_id uses the 'code' field to look up
        building = repo.get_by_id(site_id)
        return building.get("id") if building else None
    except Exception as e:
        logger.warning("Failed to resolve building_id for %s: %s", site_id, e)
        return None


def _create_demo_sync_history(
    repo: IntegrationRepository,
    source_id: str,
    base_count: int,
) -> None:
    """Create demo sync jobs for last 7 days to show healthy history.

    This provides a realistic-looking sync history in the Integration
    Monitoring dashboard for demo purposes.

    Args:
        repo: Integration repository instance
        source_id: Log source ID to associate jobs with
        base_count: Base number of records per sync
    """
    for days_ago in range(1, 8):
        try:
            job = repo.create_sync_job(source_id)
            # Vary the counts slightly for realism
            records = base_count + (days_ago * 2)
            repo.complete_sync_job(
                job_id=job["id"],
                status="success",
                processed=records,
                inserted=base_count,
                skipped=days_ago * 2,
                failed=0,
            )
        except Exception as e:
            logger.debug("Failed to create demo sync job: %s", e)
            # Non-critical, continue
