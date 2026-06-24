"""Backfill site-005 phase promotion gates and bridge adapter config.

Site-005 was onboarded via SQL migrations before the SIMBIOT wizard was
updated to seed phase promotion gates and create adapter configs. This
script backfills both so site-005 can progress through the phased
onboarding pipeline (shadow_live -> advisory -> supervised -> automatic).

Run:  backend/venv/bin/python backend/scripts/backfill_site005_onboarding.py
"""

import asyncio
import logging
import os
import sys

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("backfill_site005")

SITE_ID = "site-005"


async def main():
    logger.info("=== Backfilling site-005 onboarding ===")

    # 1. Seed phase promotion gates (shadow_live -> advisory -> supervised -> automatic)
    try:
        from app.services.site_creation_service import SiteCreationService

        service = SiteCreationService()
        service.seed_phase_promotion_gates(SITE_ID)
        logger.info("Seeded phase promotion gates for %s", SITE_ID)
    except Exception as e:
        logger.error("Failed to seed phase promotion gates: %s", e)
        raise

    # 2. Create bridge adapter config if not exists
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()

        # Check if adapter config already exists
        existing = sb.table("site_adapter_config").select("id, protocol").eq("site_id", SITE_ID).execute()
        if existing.data:
            protocols = [r["protocol"] for r in existing.data]
            logger.info("Adapter configs already exist for %s: %s", SITE_ID, protocols)
        else:
            # Use the global bridge token; site-005 shares the same bridge infrastructure
            bridge_token = (
                os.environ.get("BRIDGE_API_TOKEN_SITE005")
                or os.environ.get("BRIDGE_API_TOKEN_SITE_005")
                or os.environ.get("BRIDGE_API_TOKEN")
                or os.environ.get("SIMBIOT_API_KEY", "")
            )

            connection_config = {
                "base_url": "http://10.99.0.1:8080",
                "token": bridge_token,
                "supports_writes": False,
                "write_enabled": False,
                "timeout_seconds": 30.0,
            }

            sb.table("site_adapter_config").upsert(
                {
                    "site_id": SITE_ID,
                    "protocol": "bridge",
                    "enabled": True,
                    "connection_config": connection_config,
                    "poll_interval_seconds": 300,
                },
                on_conflict="site_id,protocol",
            ).execute()
            logger.info("Created bridge adapter config for %s", SITE_ID)

    except Exception as e:
        logger.error("Failed to create adapter config: %s", e)
        raise

    logger.info("=== site-005 onboarding backfill complete ===")
    logger.info("Next steps:")
    logger.info("  1. Verify bridge telemetry flows in logs")
    logger.info("  2. Phase promotion evaluator will check gates hourly")
    logger.info("  3. Promote to advisory via settings page when ready")


if __name__ == "__main__":
    asyncio.run(main())
