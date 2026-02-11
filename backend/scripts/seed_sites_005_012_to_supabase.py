#!/usr/bin/env python3
"""
Seed site-005 and site-012 from local JSON files to Supabase.

Usage:
    python backend/scripts/seed_sites_005_012_to_supabase.py

This script:
1. Reads building.json from site-005 and site-012
2. Reads all equipment JSON files
3. Inserts buildings into Supabase
4. Inserts equipment into Supabase
"""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Any
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database.supabase_client import get_supabase_client


def load_building_json(site_id: str) -> Dict[str, Any]:
    """Load building.json for a site."""
    building_file = Path(f"app/data/buildings/{site_id}/building.json")
    with open(building_file) as f:
        return json.load(f)


def load_equipment_files(site_id: str) -> List[Dict[str, Any]]:
    """Load all equipment JSON files for a site."""
    equipment_dir = Path(f"app/data/buildings/{site_id}/equipment")
    equipment_list = []
    
    for file_path in sorted(equipment_dir.glob("*.json")):
        with open(file_path) as f:
            equipment_list.append(json.load(f))
    
    return equipment_list


def prepare_building_for_supabase(building_data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform building JSON to Supabase schema."""
    return {
        "id": str(uuid.uuid4()),  # Generate UUID if not present
        "code": building_data.get("id"),  # e.g., "site-005"
        "name": building_data.get("name", ""),
        "display_name": building_data.get("display_name", building_data.get("name", "")),
        "address": building_data.get("address", ""),
        "type": building_data.get("type", "office"),
        "region": building_data.get("region", ""),
        "timezone": building_data.get("timezone", "Africa/Johannesburg"),
        "floors": building_data.get("floors", []),
        "features": building_data.get("features", {}),
        "metadata": {
            **(building_data.get("metadata", {})),
            "sqm": building_data.get("sqm", 0),
        },
        "bms": building_data.get("bms", {}),
        "contacts": building_data.get("contacts", {}),
        "optimization": building_data.get("optimization", {}),
    }


def prepare_equipment_for_supabase(
    equipment_data: Dict[str, Any],
    building_uuid: str
) -> Dict[str, Any]:
    """Transform equipment JSON to Supabase schema."""
    
    # Extract equipment type from equipment_id
    # e.g., "site-005-UMH-GEN-B1-002.run" -> "GEN" or "S012-GEN-G-001" -> "GEN"
    equipment_id = equipment_data.get("id", "")
    
    # Try to extract type (usually the third segment)
    parts = equipment_id.split("-")
    if len(parts) >= 3:
        equipment_type = parts[2]  # "GEN", "AHU", "FCU", etc.
    else:
        equipment_type = equipment_data.get("equipment_type", "unknown")
    
    return {
        "id": str(uuid.uuid4()),
        "code": equipment_data.get("id", ""),
        "name": equipment_data.get("name", ""),
        "building_id": building_uuid,
        "type": equipment_type.lower(),
        "device_type": equipment_data.get("device_type", "unknown"),
        "equipment_type": equipment_data.get("equipment_type", "").lower(),
        "protocol": equipment_data.get("protocol", "mock"),
        "status": equipment_data.get("status", "unknown"),
        "health_score": float(equipment_data.get("health_score", 50)),
        "metadata": {
            **(equipment_data.get("metadata", {})),
            **(equipment_data.get("device_location", {})),
            **(equipment_data.get("equipment", {})),
        },
        "points": equipment_data.get("points", {}),
    }


def seed_site(site_id: str, client) -> bool:
    """Seed a single site to Supabase."""
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Seeding {site_id}...")
        logger.info(f"{'='*60}")
        
        # Load building data
        logger.info(f"Loading building data for {site_id}...")
        building_data = load_building_json(site_id)
        building_supabase = prepare_building_for_supabase(building_data)
        
        # Check if building already exists
        existing = client.table('buildings').select('id').eq('code', site_id).execute()
        if existing.data:
            logger.warning(f"Building {site_id} already exists in Supabase. Skipping...")
            building_uuid = existing.data[0]['id']
        else:
            # Insert building
            logger.info(f"Inserting building {site_id}...")
            response = client.table('buildings').insert(building_supabase).execute()
            if not response.data:
                logger.error(f"Failed to insert building {site_id}")
                return False
            building_uuid = response.data[0]['id']
            logger.info(f"✅ Building inserted: {site_id} (UUID: {building_uuid})")
        
        # Load and insert equipment
        logger.info(f"Loading equipment files for {site_id}...")
        equipment_list = load_equipment_files(site_id)
        logger.info(f"Found {len(equipment_list)} equipment items")
        
        for i, equipment_data in enumerate(equipment_list, 1):
            equipment_supabase = prepare_equipment_for_supabase(equipment_data, building_uuid)
            
            # Check if equipment already exists
            existing = client.table('equipment').select('id').eq(
                'code', equipment_supabase['code']
            ).execute()
            
            if existing.data:
                logger.debug(f"  Equipment {equipment_supabase['code']} already exists. Skipping...")
            else:
                try:
                    response = client.table('equipment').insert(equipment_supabase).execute()
                    if response.data:
                        logger.debug(f"  [{i}/{len(equipment_list)}] ✅ {equipment_supabase['code']}")
                    else:
                        logger.error(f"  [{i}/{len(equipment_list)}] ❌ Failed to insert {equipment_supabase['code']}")
                except Exception as e:
                    logger.error(f"  [{i}/{len(equipment_list)}] ❌ Error inserting {equipment_supabase['code']}: {e}")
        
        logger.info(f"✅ Completed seeding {site_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error seeding {site_id}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    logger.info("Starting seed script for site-005 and site-012...")
    
    # Connect to Supabase
    client = get_supabase_client()
    
    success = True
    
    # Seed both sites
    for site_id in ["site-005", "site-012"]:
        if not seed_site(site_id, client):
            success = False
    
    logger.info(f"\n{'='*60}")
    if success:
        logger.info("✅ ALL SITES SEEDED SUCCESSFULLY!")
    else:
        logger.error("❌ Some sites failed to seed. Check logs above.")
    logger.info(f"{'='*60}\n")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
