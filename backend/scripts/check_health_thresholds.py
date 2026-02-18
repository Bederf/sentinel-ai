#!/usr/bin/env python3
"""Check which health thresholds are being used."""

import sys
from pathlib import Path
from dotenv import load_dotenv
import json

load_dotenv(Path(__file__).parent.parent / '.env')
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.database.supabase_client import get_supabase_client
    from app.services.health_threshold_service import get_health_thresholds, DEFAULT_THRESHOLDS

    print("=" * 70)
    print("HEALTH THRESHOLD SOURCE ANALYSIS")
    print("=" * 70)

    # Show defaults in code
    print("\n[1] Hardcoded Python Defaults:")
    print(f"  healthy: {DEFAULT_THRESHOLDS['healthy']}")
    print(f"  warning: {DEFAULT_THRESHOLDS['warning']}")
    print(f"  critical: {DEFAULT_THRESHOLDS['critical']}")

    # Show JSON file settings
    print("\n[2] JSON Settings File (backend/app/data/settings.json):")
    try:
        with open(Path(__file__).parent.parent / 'app/data/settings.json') as f:
            settings = json.load(f)
            json_thresholds = settings.get('healthThresholds', {})
            print(f"  healthy: {json_thresholds.get('healthy', 'NOT SET')}")
            print(f"  warning: {json_thresholds.get('warning', 'NOT SET')}")
            print(f"  critical: {json_thresholds.get('critical', 'NOT SET')}")
    except FileNotFoundError:
        print("  settings.json not found")

    # Check Supabase
    print("\n[3] Supabase system_settings Table:")
    client = get_supabase_client()
    try:
        result = client.table('system_settings').select('key, value').eq(
            'key', 'health_thresholds'
        ).execute()
        if result.data:
            print(f"  Found: {result.data[0]['value']}")
        else:
            print("  No entry found in system_settings")
    except Exception as e:
        print(f"  Error querying: {e}")

    # Check what's actually being used
    print("\n[4] Currently Active Thresholds:")
    active = get_health_thresholds(force_refresh=True)
    print(f"  healthy: {active['healthy']}")
    print(f"  warning: {active['warning']}")
    print(f"  critical: {active['critical']}")

    # Impact analysis
    print("\n[5] Impact Analysis:")
    print("  Equipment at 85% health:")
    print("    If healthy=90: Status='warning' (BELOW threshold) → Generates predictions")
    print("    If healthy=80: Status='healthy' (ABOVE threshold) → No predictions ✓")
    print("  Current predictions: 161 (expected to drop to ~20 if threshold fixed)")

    print("\n" + "=" * 70)

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
