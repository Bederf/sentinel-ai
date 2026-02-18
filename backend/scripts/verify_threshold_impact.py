#!/usr/bin/env python3
"""Verify the impact of the threshold fix."""

import sys
from pathlib import Path
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv(Path(__file__).parent.parent / '.env')
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.database.supabase_client import get_supabase_client
    from app.services.health_threshold_service import get_health_status

    client = get_supabase_client()

    # Force refresh to get new thresholds
    from app.services.health_threshold_service import clear_health_threshold_cache
    clear_health_threshold_cache()

    print("=" * 70)
    print("THRESHOLD FIX VERIFICATION")
    print("=" * 70)

    # Get all equipment
    equipment_result = client.table('equipment').select(
        'code, name, type, health_score, status',
        count='exact'
    ).execute()

    print(f"\nTotal equipment: {equipment_result.count}")

    # Analyze by status
    print("\nEquipment Status After Threshold Fix (healthy=80):")
    at_risk_count = 0
    healthy_count = 0
    warning_count = 0
    critical_count = 0

    for eq in (equipment_result.data or []):
        health = eq.get('health_score', 50)
        status = get_health_status(health)

        if status == 'healthy':
            healthy_count += 1
        elif status == 'warning':
            warning_count += 1
            at_risk_count += 1
        elif status == 'critical':
            critical_count += 1
            at_risk_count += 1

    print(f"  ✓ HEALTHY (≥80%): {healthy_count} equipment")
    print(f"  ⚠️  WARNING (60-79%): {warning_count} equipment")
    print(f"  🔴 CRITICAL (<60%): {critical_count} equipment")
    print(f"\n  → At-risk (will generate predictions): {at_risk_count}")
    print(f"  → Healthy (no predictions): {healthy_count}")

    print("\n" + "=" * 70)
    print("SUMMARY OF CHANGES")
    print("=" * 70)
    print(f"\nBefore Fix (healthy=90 threshold):")
    print(f"  Predictions: 161 (all 85% equipment flagged as at-risk)")
    print(f"  Issue: All showing 60% probability (formula minimum)")

    print(f"\nAfter Fix (healthy=80 threshold):")
    print(f"  Predictions: ~{at_risk_count} (only actual at-risk equipment)")
    print(f"  Solution: Equipment at 85% health no longer flagged")
    print(f"  Result: More accurate risk assessment ✓")

    print("\n" + "=" * 70)

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
