"""
SIMBIOT Concept Connector — Usage Example
==========================================
Demonstrates the full SENTINEL → MRI Evolution flow:

1. SENTINEL AI detects chiller anomaly from BMS telemetry
2. SIMBIOT connector translates to structured work order
3. POSTs to FSI Public API → appears on technician's iPad
4. Polls for status updates → feeds back to SENTINEL ML

Run: python -m examples.usage_example
"""

import asyncio
from datetime import datetime

from simbiot_concept import ConceptConnector, SentinelAnomaly
from simbiot_concept.models.anomaly import AnomalySource
from examples.config_firstrand import create_firstrand_config


async def main():
    # ── 1. Create connector with FirstRand config ──
    config = create_firstrand_config()
    connector = ConceptConnector(config)

    # ── 2. Initialise (authenticate + sync assets) ──
    # In production this happens once at startup
    await connector.initialise()
    print(f"Connector status: {connector.status}")

    # ── 3. SENTINEL detects a BMS anomaly ──
    # This would come from SENTINEL's AI engine in production
    chiller_anomaly = SentinelAnomaly(
        source=AnomalySource.BMS_ANOMALY,
        segment_id="SEG--001",
        building_id="bld--main",
        building_name=" Campus — Main Building",
        location_id=5042,
        location_description="Basement Level 2 — Plant Room A",
        asset_id=8891,
        asset_tag="CH-001-FA",
        asset_type="chiller",
        asset_name="Chiller #1 — York YCAL",
        severity_score=0.82,
        summary="Chiller #1 compressor discharge temperature rising abnormally — "
                "potential refrigerant loss or condenser fouling",
        diagnostics=(
            "SENTINEL detected a progressive increase in compressor discharge "
            "temperature on Chiller #1 (York YCAL, Asset CH-001-FA) at  "
            "Campus. The discharge temp has risen from a 30-day baseline of 62°C "
            "to 78°C over the past 72 hours, representing a 25.8% deviation. "
            "Simultaneously, the condenser approach temperature has widened from "
            "3.2°C to 7.1°C, suggesting either refrigerant charge loss or "
            "condenser tube fouling. The suction pressure has dropped from 4.2 bar "
            "to 3.6 bar, consistent with low refrigerant charge. "
            "If uncorrected, this pattern typically leads to compressor trip on "
            "high-pressure cutout within 48-72 hours."
        ),
        sensor_readings={
            "discharge_temp_c": 78.2,
            "suction_pressure_bar": 3.6,
            "condenser_approach_c": 7.1,
            "supply_water_temp_c": 7.8,
            "return_water_temp_c": 13.2,
            "compressor_current_a": 142.5,
            "cop": 3.1,
        },
        trend_summary=(
            "72-hour trend: Discharge temp +25.8%, suction pressure -14.3%, "
            "condenser approach +121.9%. COP declined from 4.2 to 3.1 (-26.2%). "
            "Pattern consistent with progressive refrigerant loss."
        ),
        recommended_action=(
            "1. Inspect for refrigerant leaks (check compressor shaft seal, "
            "expansion valve, and suction line joints). "
            "2. Check condenser coils for fouling (last cleaned 6 months ago). "
            "3. Verify refrigerant charge level against nameplate specification. "
            "4. Monitor compressor vibration for bearing degradation."
        ),
    )

    # ── 4. Create work order in MRI Evolution ──
    try:
        result = await connector.create_work_order(chiller_anomaly)
        print(f"\n✓ Work order created!")
        print(f"  MRI Evolution ID: {result.work_order_id}")
        print(f"  Reference: {result.reference}")
        print(f"  Status: {result.status.value}")
        print(f"  Correlation ID: {result.correlation_id}")
        print(f"\n  → Technician will see this on their iPad in FSI GO")
        print(f"  → Full diagnostic report in the notes field")
    except Exception as e:
        print(f"✗ Work order creation failed: {e}")

    # ── 5. Example: Occupant request via WhatsApp ──
    whatsapp_request = SentinelAnomaly(
        source=AnomalySource.OCCUPANT_REQUEST,
        segment_id="SEG--001",
        building_id="bld--main",
        building_name=" Campus — Main Building",
        location_id=5108,
        location_description="3rd Floor — Meeting Room 3B",
        asset_type="hvac",
        severity_score=0.5,
        summary="Aircon not cooling in Meeting Room 3B — reported by occupant via WhatsApp",
        diagnostics=(
            "Occupant reported via WhatsApp that Meeting Room 3B on the 3rd floor "
            "is uncomfortably warm. SENTINEL cross-referenced with BMS data and "
            "confirmed that the FCU serving this zone (FCU-03-12) is running but "
            "supply air temperature is 22°C vs setpoint of 18°C. The VAV damper "
            "position shows 100% open, suggesting the FCU is struggling to meet "
            "load. Possible causes: dirty filter, low refrigerant in split unit "
            "feeding the FCU, or faulty actuator on chilled water valve."
        ),
        requester_name="Sarah Nkosi",
        requester_contact="+27821234567",
        original_message="Hi, the aircon in meeting room 3B isn't working. "
                        "We have a client presentation in 2 hours. Please help!",
        recommended_action=(
            "Check FCU-03-12 filter condition. Verify chilled water valve actuator "
            "operation. Check split unit refrigerant pressure if applicable."
        ),
    )

    try:
        result2 = await connector.create_work_order(whatsapp_request)
        print(f"\n✓ WhatsApp request → Work order created!")
        print(f"  MRI Evolution ID: {result2.work_order_id}")
        print(f"  → Sarah will get a WhatsApp confirmation with the WO reference")
    except Exception as e:
        print(f"✗ WhatsApp WO creation failed: {e}")

    # ── 6. Poll for status updates (would run continuously in production) ──
    print(f"\nTracking {len(connector._tracked_work_orders)} open work orders...")
    updates = await connector.poll_work_order_statuses()
    if updates:
        for u in updates:
            print(f"  WO#{u.work_order_id}: {u.previous_status} → {u.current_status}")

    # ── 7. Shutdown ──
    await connector.shutdown()
    print("\nConnector shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
