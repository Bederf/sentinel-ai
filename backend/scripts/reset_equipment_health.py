#!/usr/bin/env python3
"""
Reset all equipment health scores to 90% (healthy state).

This script:
1. Sets all equipment health_score to 90
2. Sets all equipment status to 'normal'
3. Resolves all active predictions
4. Clears all active alerts (optional)

Usage:
    python3 reset_equipment_health.py [--keep-alerts]
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.supabase_client import get_supabase_client


def reset_health_scores():
    """Reset all equipment health scores to 90%."""

    client = get_supabase_client()

    print("🔄 Resetting equipment health scores...")

    # Get all equipment first
    all_eq = client.table("equipment").select("id").execute()
    eq_ids = [eq["id"] for eq in (all_eq.data or [])]

    if eq_ids:
        # Update all equipment to health_score = 90, status = normal
        client.table("equipment").update({"health_score": 90, "status": "normal"}).in_("id", eq_ids).execute()

        print(f"✓ Reset {len(eq_ids)} equipment items to health_score=90, status=normal")
    else:
        print("✓ No equipment found to reset")

    # Resolve all active predictions
    print("\n🔄 Resolving active predictions...")

    # Get all active predictions
    predictions = client.table("predictions").select("id").eq("status", "active").execute()

    if predictions.data and len(predictions.data) > 0:
        pred_ids = [p["id"] for p in predictions.data]

        # Update all to resolved
        client.table("predictions").update({"status": "resolved"}).in_("id", pred_ids).execute()

        print(f"✓ Resolved {len(pred_ids)} active predictions")
    else:
        print("✓ No active predictions to resolve")

    # Get all buildings for summary
    print("\n📊 Summary by Site:")
    buildings = client.table("sites").select("id, code, name").execute()

    for building in buildings.data or []:
        eq_count = client.table("equipment").select("id").eq("site_id", building["id"]).execute()
        count = len(eq_count.data) if eq_count.data else 0
        print(f"  • {building['code']} ({building['name']}): {count} equipment")

    print("\n✅ Health reset complete!")
    print("\nNext steps:")
    print("  1. Hard refresh your browser (Ctrl+Shift+R)")
    print("  2. Risk predictions will no longer appear (all resolved)")
    print("  3. Equipment status shows normal/healthy")
    print("  4. To create new predictions, generate new alerts")


if __name__ == "__main__":
    try:
        reset_health_scores()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
