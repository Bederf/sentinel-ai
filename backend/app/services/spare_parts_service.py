"""Service for spare parts population — post-onboarding, manual, and fallback."""

import logging
from typing import Any

from app.database.repositories.spare_parts_repository import SparePartsRepository

logger = logging.getLogger(__name__)


CURATED_MANUFACTURER_PARTS: dict[str, list[dict[str, Any]]] = {
    "carrier_chiller": [
        {
            "part_name": "Compressor oil filter",
            "part_number": "30GX-502012-XX",
            "unit_cost_zar": 950.00,
            "typical_replacement_interval_days": 365,
            "criticality": "critical",
        },
        {
            "part_name": "Refrigerant filter drier",
            "part_number": "30GX-503214-XX",
            "unit_cost_zar": 1350.00,
            "typical_replacement_interval_days": 730,
            "criticality": "critical",
        },
        {
            "part_name": "Oil pressure sensor",
            "part_number": "HH79NZ005",
            "unit_cost_zar": 720.00,
            "typical_replacement_interval_days": 1095,
            "criticality": "essential",
        },
        {
            "part_name": "Chilled water temp sensor",
            "part_number": "CEA-2002-10K",
            "unit_cost_zar": 480.00,
            "typical_replacement_interval_days": 1460,
            "criticality": "essential",
        },
    ],
    "trane_chiller": [
        {
            "part_name": "Compressor oil filter",
            "part_number": "CHH-123-456",
            "unit_cost_zar": 890.00,
            "typical_replacement_interval_days": 365,
            "criticality": "critical",
        },
        {
            "part_name": "Refrigerant filter",
            "part_number": "CHH-789-012",
            "unit_cost_zar": 1200.00,
            "typical_replacement_interval_days": 730,
            "criticality": "critical",
        },
        {
            "part_name": "Oil pressure transducer",
            "part_number": "SEN-OP-101",
            "unit_cost_zar": 680.00,
            "typical_replacement_interval_days": 1095,
            "criticality": "essential",
        },
    ],
    "york_chiller": [
        {
            "part_name": "Compressor oil filter",
            "part_number": "YF-502-001",
            "unit_cost_zar": 920.00,
            "typical_replacement_interval_days": 365,
            "criticality": "critical",
        },
        {
            "part_name": "Filter drier",
            "part_number": "YF-503-002",
            "unit_cost_zar": 1100.00,
            "typical_replacement_interval_days": 730,
            "criticality": "critical",
        },
    ],
    "daikin_chiller": [
        {
            "part_name": "Oil filter element",
            "part_number": "DK-OF-100",
            "unit_cost_zar": 780.00,
            "typical_replacement_interval_days": 365,
            "criticality": "critical",
        },
        {
            "part_name": "Strainer set",
            "part_number": "DK-ST-200",
            "unit_cost_zar": 450.00,
            "typical_replacement_interval_days": 730,
            "criticality": "essential",
        },
    ],
    "grundfos_pump": [
        {
            "part_name": "Mechanical seal",
            "part_number": "GR-SEAL-CR45",
            "unit_cost_zar": 520.00,
            "typical_replacement_interval_days": 730,
            "criticality": "essential",
        },
        {
            "part_name": "Bearing set",
            "part_number": "GR-BRG-CR45",
            "unit_cost_zar": 750.00,
            "typical_replacement_interval_days": 1095,
            "criticality": "essential",
        },
    ],
}


async def populate_parts_for_equipment(
    equipment_id: str,
    equipment_type: str,
    manufacturer: str | None = None,
    model: str | None = None,
) -> int:
    """Populate spare parts for equipment after onboarding.

    Strategy:
    1. Firecrawl OEM scraping (if API key configured) — gets real OEM part numbers
    2. Manufacturer-specific curated parts fallback
    3. Equipment-type generic curated parts fallback
    4. Skip if parts already exist for this equipment
    """
    repo = SparePartsRepository()

    existing = repo.get_parts_for_equipment(equipment_id)
    if existing:
        logger.info("[PARTS] Equipment %s already has %d parts — skipping", equipment_id, len(existing))
        return 0

    count = 0

    if manufacturer and model:
        from app.services.oem_parts_scraper import scrape_oem_parts

        scraped = await scrape_oem_parts(manufacturer, model, equipment_type)
        if scraped:
            for part in scraped:
                part_data = {
                    "equipment_id": equipment_id,
                    "equipment_type": equipment_type,
                    "manufacturer": manufacturer,
                    "model": model,
                    "source": "scraped",
                    "part_name": part["part_name"],
                    "part_number": part.get("part_number"),
                    "unit_cost_zar": part.get("unit_cost_zar"),
                    "criticality": part.get("criticality", "consumable"),
                    "initial_stock": 0,
                    "min_threshold": 1,
                    "max_threshold": 5,
                }
                created = repo.create_part(part_data)
                if created:
                    count += 1
            if count:
                logger.info("[PARTS] Firecrawl populated %d OEM parts for %s", count, equipment_id)
                return count

    if manufacturer:
        mfr_key = f"{manufacturer.lower()}_{equipment_type}"
        curated = CURATED_MANUFACTURER_PARTS.get(mfr_key)
        if curated:
            for part in curated:
                part_data = {
                    "equipment_id": equipment_id,
                    "equipment_type": equipment_type,
                    "manufacturer": manufacturer,
                    "model": model,
                    "source": "curated",
                    **part,
                }
                repo.create_part(part_data)
                count += 1
            logger.info("[PARTS] Populated %d manufacturer-specific parts for %s", count, equipment_id)
            return count

    generic = repo.get_parts_for_type(equipment_type)
    if generic:
        linked = 0
        for part in generic:
            repo.link_to_equipment(part["id"], equipment_id)
            linked += 1
        logger.info("[PARTS] Linked %d generic parts to %s", linked, equipment_id)
        return linked

    logger.info("[PARTS] No parts available for %s (type=%s)", equipment_id, equipment_type)
    return 0
