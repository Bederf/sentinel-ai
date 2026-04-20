#!/usr/bin/env python3
"""Fix health threshold configuration in Supabase."""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    print("=" * 70)
    print("FIXING HEALTH THRESHOLD CONFIGURATION")
    print("=" * 70)

    # The correct thresholds (from settings.json)
    correct_thresholds = {"healthy": 80, "warning": 60, "critical": 0}

    print("\n[1] Current Supabase system_settings:")
    current = client.table("system_settings").select("value").eq("key", "health_thresholds").execute()
    if current.data:
        old_value = current.data[0]["value"]
        print(f"  healthy: {old_value.get('healthy', 'N/A')}")
        print(f"  warning: {old_value.get('warning', 'N/A')}")
        print(f"  critical: {old_value.get('critical', 'N/A')}")

    print("\n[2] Correct Thresholds (from settings.json):")
    print(f"  healthy: {correct_thresholds['healthy']}")
    print(f"  warning: {correct_thresholds['warning']}")
    print(f"  critical: {correct_thresholds['critical']}")

    print("\n[3] Updating Supabase...")
    result = (
        client.table("system_settings").update({"value": correct_thresholds}).eq("key", "health_thresholds").execute()
    )

    if result.data:
        print("  ✓ Successfully updated system_settings")
        updated = result.data[0]["value"]
        print(f"  New values: {updated}")
    else:
        print("  ✗ No rows updated - creating new entry...")
        result = (
            client.table("system_settings").insert({"key": "health_thresholds", "value": correct_thresholds}).execute()
        )
        if result.data:
            print("  ✓ Successfully created system_settings entry")
        else:
            print("  ✗ Failed to create entry")

    print("\n[4] Expected Impact:")
    print("  Predictions before: 161 (all at 60% probability)")
    print("  Predictions after: ~20 (equipment with health < 60%)")
    print("  Reason: Equipment at 85% health now considered 'healthy'")

    print("\n[5] To activate the fix:")
    print("  - Clear Python cache: health_threshold_service.clear_cache()")
    print("  - Restart backend service")
    print("  - Frontend will automatically reload")

    print("\n" + "=" * 70)

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
