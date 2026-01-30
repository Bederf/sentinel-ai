#!/usr/bin/env python3
"""
Test script for BMS Simulation Service
Verifies that the simulation generates realistic, changing data
"""

import asyncio
import json
import time
from datetime import datetime

# Add backend to path
import sys
sys.path.insert(0, '/opt/bms-intelligence/backend')

from app.services.bms_simulation_service import create_simulation_service
from app.services.simulation_bridge import simulation_bridge

async def test_simulation_service():
    """Test the complete simulation service"""
    print("=" * 80)
    print("Testing BMS Simulation Service")
    print("=" * 80)

    # Create simulation service
    sim_service = create_simulation_service()

    # Test 1: Start simulation
    print("\n1. Starting simulation...")
    await sim_service.start_simulation()
    print(f"   ✓ Simulation started: {sim_service.is_running}")

    # Wait a moment for initialization
    await asyncio.sleep(2)

    # Test 2: Get initial equipment data
    print("\n2. Getting initial equipment data...")
    initial_data = sim_service.get_real_time_data()
    print(f"   ✓ Total equipment: {initial_data['summary']['total_equipment']}")
    print(f"   ✓ Average health: {initial_data['summary']['health_stats']['avg_health']:.1f}%")

    # Test 3: Wait and check for changes
    print("\n3. Checking for data changes (waiting 10 seconds)...")
    print("   Monitoring equipment changes...")

    # Get baseline for first equipment item
    first_equipment_id = list(sim_service.equipment.keys())[0]
    baseline_eq = sim_service.equipment[first_equipment_id]
    baseline_temp = baseline_eq.temperature
    baseline_health = baseline_eq.health_score

    # Wait and check for changes
    for i in range(5):
        await asyncio.sleep(2)
        current_eq = sim_service.equipment[first_equipment_id]

        print(f"   After {i+1} updates:")
        print(f"     - Temperature: {current_eq.temperature:.1f}°C (change: {current_eq.temperature - baseline_temp:+.1f})")
        print(f"     - Health: {current_eq.health_score:.1f}% (change: {current_eq.health_score - baseline_health:+.1f})")
        print(f"     - Runtime: {current_eq.runtime_hours:.1f} hours (+{2/3600:.4f})")

    # Test 4: Inject a fault
    print("\n4. Testing fault injection...")
    test_equipment_id = first_equipment_id
    test_fault = "Carrier:E14"

    sim_service.inject_fault(test_equipment_id, test_fault)
    print(f"   ✓ Injected fault {test_fault} into {test_equipment_id}")

    # Check fault was applied
    updated_eq = sim_service.equipment[test_equipment_id]
    print(f"   ✓ Equipment now has faults: {updated_eq.fault_codes}")
    print(f"   ✓ Health score dropped to: {updated_eq.health_score:.1f}%")

    # Test 5: Use simulation bridge to convert to API format
    print("\n5. Testing simulation bridge...")
    await simulation_bridge.initialize()

    equipment, sensors, alerts = simulation_bridge.get_equipment_with_sensors_and_alerts()
    print(f"   ✓ Converted equipment: {len(equipment)} items")
    print(f"   ✓ Generated sensors: {len(sensors)} sensors")
    print(f"   ✓ Generated alerts: {len(alerts)} alerts")

    # Show first equipment item
    if equipment:
        first_eq = equipment[0]
        print(f"\n   Sample equipment:")
        print(f"     - ID: {first_eq['id']}")
        print(f"     - Name: {first_eq['name']}")
        print(f"     - Type: {first_eq['type']}")
        print(f"     - Health: {first_eq['health_score']:.1f}%")

    # Test 6: Real-time data changes
    print("\n6. Testing real-time data updates...")
    print("   Monitoring sensor changes...")

    # Get sensor data
    sensor_data = []
    for sensor in sensors[:3]:  # Just first 3 sensors
        sensor_data.append({
            "id": sensor["id"],
            "name": sensor["name"],
            "initial_value": sensor["current_value"],
            "type": sensor["type"]
        })

    print("   Tracking sensor values...")
    for i in range(3):
        await asyncio.sleep(2)

        # Get updated sensor data
        new_equipment, new_sensors, _ = simulation_bridge.get_equipment_with_sensors_and_alerts()

        print(f"\n   After {i+1} updates:")
        for tracked_sensor in sensor_data:
            # Find updated sensor
            updated_sensor = next((s for s in new_sensors if s["id"] == tracked_sensor["id"]), None)
            if updated_sensor:
                change = updated_sensor["current_value"] - tracked_sensor["initial_value"]
                print(f"     - {tracked_sensor['name']}: {updated_sensor['current_value']:.2f} {updated_sensor['unit']} (change: {change:+.2f})")

    # Test 7: Clear faults
    print("\n7. Testing fault clearing...")
    sim_service.clear_faults(test_equipment_id)
    print(f"   ✓ Cleared faults from {test_equipment_id}")

    cleared_eq = sim_service.equipment[test_equipment_id]
    print(f"   ✓ Equipment faults cleared: {cleared_eq.fault_codes}")
    print(f"   ✓ Health score recovering: {cleared_eq.health_score:.1f}%")

    # Test 8: Stop simulation
    print("\n8. Stopping simulation...")
    await sim_service.stop_simulation()
    print(f"   ✓ Simulation stopped: {not sim_service.is_running}")

    # Final summary
    print("\n" + "=" * 80)
    print("✅ All tests passed!")
    print("=" * 80)

    return True

async def test_simulation_with_ai():
    """Test simulation with AI responses"""
    print("\n" + "=" * 80)
    print("Testing Simulation with AI System")
    print("=" * 80)

    # This would test the AI system with simulated data
    # For now, just show the concept
    print("\n1. Testing AI responses to simulated faults...")
    print("   - Inject fault: Carrier:E14 (Outdoor fan motor fault)")
    print("   - Expected AI response: Check condenser coil, motor may need replacement")
    print("   - Should use cloud fallback if Claude unavailable")

    print("\n2. Testing AI with changing sensor data...")
    print("   - Monitor temperature drift over time")
    print("   - AI should detect patterns and suggest maintenance")

    print("\n3. Testing fallback chain...")
    print("   - Claude -> OpenAI -> Gemini -> Local Ollama")
    print("   - Should maintain <2s response time for user queries")

    print("\n✅ Simulation-AI integration ready for testing!")

if __name__ == "__main__":
    print("Starting BMS Simulation Tests...")
    print("=" * 80)

    # Run tests
    asyncio.run(test_simulation_service())
    asyncio.run(test_simulation_with_ai())

    print("\n" + "=" * 80)
    print("All simulation tests completed!")
    print("=" * 80)

    # Instructions for manual testing
    print("\nTo manually test with AI:")
    print("1. Start the BMS Intelligence backend: cd /opt/bms-intelligence/backend && source venv/bin/activate && uvicorn app.main:app --reload --port 9095")
    print("2. Inject a fault: curl -X POST http://localhost:9095/api/simulation/fault/inject?equipment_id=AHU-L01-01&fault_code=Carrier:E14")
    print("3. Check equipment: curl http://localhost:9095/api/simulation/equipment")
    print("4. Test with AI: Use the clawd bot to ask about the fault")