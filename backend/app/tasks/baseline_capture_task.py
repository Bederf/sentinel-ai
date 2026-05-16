"""
Deferred baseline capture task.

APScheduler 5-min task: finds equipment with NULL health_score,
calculates an age-only baseline or synthetic fallback, and updates the record.

Handles three cases:
1. Newly discovered equipment (health_score=NULL, replaced_on=NULL, has service_history)
2. Recently replaced equipment (health_score=NULL, replaced_on IS NOT NULL)
3. VAV/FCU without service_history (synthetic fallback to 82, low confidence)
"""

import logging
from datetime import datetime

from app.database.supabase_client import get_supabase_client
from app.services.health.baseline_calculator import calculate_baseline_health

logger = logging.getLogger(__name__)

# VAV/FCU types eligible for synthetic fallback baseline
SYNTHETIC_FALLBACK_TYPES = {"vav", "VAV", "FCU", "fcu"}


async def capture_baselines_for_unscored_equipment():
    """Find equipment with NULL health_score and capture baselines."""
    supabase = get_supabase_client()

    unscored = (
        supabase.table("equipment")
        .select("id,code,type,service_history_id,replaced_on,replacement_notes")
        .is_("health_score", "null")
        .execute()
    )

    items = unscored.data or []
    if not items:
        logger.debug("Baseline capture: no unscored equipment found")
        return

    logger.info("Baseline capture: found %s unscored equipment", len(items))

    captured = 0
    synthetic = 0
    failed = 0

    for eq in items:
        eq_id = eq["id"]
        code = eq.get("code", "?")
        eq_type = eq.get("type", "")
        sh_id = eq.get("service_history_id")
        replaced_on = eq.get("replaced_on")

        # Case 3: VAV/FCU synthetic fallback (no service history needed)
        if not sh_id and eq_type in SYNTHETIC_FALLBACK_TYPES:
            try:
                supabase.table("equipment").update(
                    {
                        "health_score": 82,
                        "health_score_confidence": 0.25,
                        "baseline_sourced_from": "synthetic_type_default",
                        "last_baseline_update": datetime.utcnow().isoformat(),
                    }
                ).eq("id", eq_id).execute()
                logger.info("synthetic_fallback | %s | health=82 | conf=0.25 | VAV/FCU no service history", code)
                synthetic += 1
                continue
            except Exception as e:
                logger.error("%s: synthetic fallback failed: %s", code, e)
                failed += 1
                continue

        # Cases 1 & 2: require service_history_id
        if not sh_id:
            logger.debug("%s: no service_history_id and not VAV/FCU, skipping", code)
            failed += 1
            continue

        sh = (
            supabase.table("equipment_service_history")
            .select("commissioning_date,equipment_type,baseline_calculation_method")
            .eq("id", sh_id)
            .limit(1)
            .execute()
        )
        if not sh.data:
            logger.warning("%s: service_history not found for id=%s", code, sh_id)
            failed += 1
            continue

        sh_rec = sh.data[0]
        comm_date = sh_rec.get("commissioning_date")
        if not comm_date:
            logger.warning("%s: commissioning_date missing in service_history", code)
            failed += 1
            continue

        try:
            health_score, confidence, desc = calculate_baseline_health(
                comm_date, sh_rec.get("equipment_type")
            )
        except Exception as e:
            logger.error("%s: baseline calculation failed: %s", code, e)
            failed += 1
            continue

        try:
            supabase.table("equipment").update(
                {
                    "health_score": round(health_score),
                    "health_score_confidence": confidence,
                    "baseline_sourced_from": sh_rec.get("baseline_calculation_method", "age_only"),
                    "last_baseline_update": datetime.utcnow().isoformat(),
                }
            ).eq("id", eq_id).execute()

            event_type = "baseline_captured_replacement" if replaced_on else "baseline_captured_discovery"
            context = f"replaced {replaced_on}" if replaced_on else "newly discovered"
            logger.info(
                "%s | %s | health=%.1f | conf=%.2f | %s",
                event_type, code, health_score, confidence, context,
            )
            captured += 1
        except Exception as e:
            logger.error("%s: equipment update failed: %s", code, e)
            failed += 1

    skipped = len(items) - captured - synthetic - failed
    logger.info(
        "Baseline capture done: %s age-only, %s synthetic, %s failed, %s skipped",
        captured, synthetic, failed, skipped,
    )
