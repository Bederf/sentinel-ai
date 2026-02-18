#!/usr/bin/env python3
"""
Seed sample alerts to trigger health score updates and predictions.

This script:
1. Creates sample critical and warning alerts for various equipment
2. Updates equipment health_score based on alert severity
3. Triggers prediction generation for at-risk equipment
4. Makes dashboard risk metrics visible
"""

import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.supabase_client import get_supabase_client
from app.services.prediction_generator import get_prediction_generator


async def create_sample_alerts():
    """Create sample alerts to demonstrate risk prediction."""

    client = get_supabase_client()

    # Sample equipment that will be marked as at-risk
    at_risk_equipment = [
        {
            "code": "S002-CHILLER-B1-001",
            "severity": "critical",
            "title": "Chiller Discharge Temperature Rising",
            "message": "Discharge temperature increased 3°C in 2 hours - possible compressor degradation",
        },
        {
            "code": "S002-AHU-L1-001",
            "severity": "warning",
            "title": "AHU Filter Pressure Differential High",
            "message": "Filter ΔP at 85% of maximum - recommend filter replacement soon",
        },
        {
            "code": "S002-FCU-L2-A",
            "severity": "critical",
            "title": "FCU Vibration Levels Abnormal",
            "message": "Vibration amplitude exceeds safety threshold - potential bearing failure",
        },
        {
            "code": "S002-UPS-B1-001",
            "severity": "warning",
            "title": "UPS Battery Temperature Trending High",
            "message": "Battery temp 45°C - normal range is 20-25°C, aging detected",
        },
        {
            "code": "S002-DALI-L0-A",
            "severity": "critical",
            "title": "DALI Ballast Communication Loss",
            "message": "5 ballasts no longer responding - possible RF interference or power supply issue",
        },
    ]

    print(f"Creating {len(at_risk_equipment)} sample alerts...")

    created_alerts = []
    for equipment_data in at_risk_equipment:
        # Get equipment by code
        eq_response = client.table("equipment").select("id, building_id, name").eq(
            "code", equipment_data["code"]
        ).execute()

        if not eq_response.data:
            print(f"  ✗ Equipment {equipment_data['code']} not found - skipping")
            continue

        equipment = eq_response.data[0]

        # Create alert
        alert_id = str(uuid.uuid4())
        alert_data = {
            "id": alert_id,
            "building_id": equipment["building_id"],
            "equipment_id": equipment["id"],
            "type": "health_degradation",
            "severity": equipment_data["severity"],
            "status": "active",
            "title": equipment_data["title"],
            "message": equipment_data["message"],
        }

        # Insert alert
        alert_result = client.table("alerts").insert(alert_data).execute()

        if alert_result.data:
            created_alerts.append(alert_data)
            print(f"  ✓ Alert created for {equipment_data['code']} ({equipment_data['severity']})")

            # Update equipment health score based on severity
            health_score = 30 if equipment_data["severity"] == "critical" else 60
            update_result = client.table("equipment").update({
                "health_score": health_score,
                "status": equipment_data["severity"]
            }).eq("id", equipment["id"]).execute()

            if update_result.data:
                print(f"    → Updated health_score to {health_score}")
        else:
            print(f"  ✗ Failed to create alert for {equipment_data['code']}")

    print(f"\n✓ Created {len(created_alerts)} alerts")

    # Manually trigger prediction generation
    print("\nGenerating predictions for at-risk equipment...")
    generator = get_prediction_generator()
    result = await generator.generate_predictions_for_all_sites()

    print(f"  Generated: {result.get('generated', 0)} predictions")
    print(f"  Skipped (duplicate): {result.get('skipped_duplicate', 0)}")
    print(f"  Skipped (low probability): {result.get('skipped_low_probability', 0)}")
    print(f"  Resolved: {result.get('resolved', 0)}")

    if result.get('errors'):
        print(f"  Errors: {result.get('errors')}")

    print("\n✓ Sample alerts and predictions ready!")
    print("\nNext steps:")
    print("  1. Hard refresh your browser (Ctrl+Shift+R)")
    print("  2. Risk predictions should now appear on the Dashboard")
    print("  3. System Health page should show active alerts")
    print("  4. Risk card at top should show total items at risk")


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(create_sample_alerts())
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
