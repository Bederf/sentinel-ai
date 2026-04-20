#!/usr/bin/env python3
"""Check equipment health scores distribution in Supabase."""

import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    print("=" * 70)
    print("EQUIPMENT HEALTH SCORE ANALYSIS")
    print("=" * 70)

    # Get all equipment with health scores
    print("\n[1] Querying all equipment health scores...")
    equipment_result = (
        client.table("equipment").select("code, name, type, health_score, status", count="exact").execute()
    )

    print(f"✓ Total equipment: {equipment_result.count}")

    # Analyze health score distribution
    print("\n[2] Analyzing health score distribution...")

    health_distribution = defaultdict(int)
    status_with_health = defaultdict(list)

    for eq in equipment_result.data or []:
        health = eq.get("health_score", "NULL")
        status = eq.get("status", "unknown")

        health_distribution[health] += 1
        status_with_health[f"{health}_{status}"].append(eq["code"])

    # Show health score distribution
    print("\nHealth Score Distribution:")
    for health_score in sorted(health_distribution.keys()):
        count = health_distribution[health_score]
        pct = (count / equipment_result.count * 100) if equipment_result.count > 0 else 0
        print(f"  {health_score}%: {count} equipment ({pct:.1f}%)")

    # Show breakdown by status
    print("\n[3] Health Score Breakdown by Status:")
    status_health = defaultdict(lambda: defaultdict(int))
    for eq in equipment_result.data or []:
        health = eq.get("health_score", "NULL")
        status = eq.get("status", "unknown")
        status_health[status][health] += 1

    for status in sorted(status_health.keys()):
        print(f"\n  Status: {status.upper()}")
        for health in sorted(status_health[status].keys()):
            count = status_health[status][health]
            print(f"    Health {health}%: {count} items")

    # Show unique health score values
    print("\n[4] Unique Health Score Values:")
    unique_scores = sorted(set(eq.get("health_score") for eq in (equipment_result.data or [])))
    print(f"  Found {len(unique_scores)} unique health score values:")
    for score in unique_scores:
        count = health_distribution[score]
        print(f"    {score}%: {count} equipment")

    # Check if all are 60%
    if len(unique_scores) == 1 and unique_scores[0] == 60:
        print("\n⚠️  ISSUE DETECTED: All equipment has the same health score of 60%!")
        print("   This means health scores were NOT properly calculated from device data.")
        print("   Expected: Varied health scores based on equipment condition.")
        print("   Impact: All predictions show 60% probability (minimum threshold).")

    # Sample some equipment
    print("\n[5] Sample Equipment:")
    for eq in (equipment_result.data or [])[:10]:
        print(
            f"  {eq['code']}: {eq['name']} ({eq['type']}) - "
            f"Health: {eq.get('health_score', 'N/A')}%, Status: {eq.get('status')}"
        )

    print("\n" + "=" * 70)

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
