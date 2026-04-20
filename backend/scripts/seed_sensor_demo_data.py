#!/usr/bin/env python3
"""
Seed Sensor Analysis Demo Data (Phase 41-03)

Loads demo baselines and recordings into the sensor analysis API
for demonstration and testing purposes.

Usage:
    python scripts/seed_sensor_demo_data.py
"""

import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.sensor_analysis import _baselines, _recordings


def load_demo_data():
    """Load demo baselines and recordings from JSON files."""
    data_dir = Path(__file__).parent.parent / "app" / "data" / "sensor_analysis"

    # Load baselines
    baselines_file = data_dir / "demo_baselines.json"
    if baselines_file.exists():
        with open(baselines_file) as f:
            baselines = json.load(f)

        for equipment_id, baseline in baselines.items():
            _baselines[equipment_id] = baseline

        print(f"Loaded {len(baselines)} baselines")
    else:
        print(f"Warning: {baselines_file} not found")

    # Load recordings
    recordings_file = data_dir / "demo_recordings.json"
    if recordings_file.exists():
        with open(recordings_file) as f:
            recordings = json.load(f)

        total_recordings = 0
        for equipment_id, recs in recordings.items():
            if equipment_id not in _recordings:
                _recordings[equipment_id] = []
            _recordings[equipment_id].extend(recs)
            total_recordings += len(recs)

        print(f"Loaded {total_recordings} recordings for {len(recordings)} equipment items")
    else:
        print(f"Warning: {recordings_file} not found")

    print("\nDemo data loaded successfully!")
    print(f"  Baselines: {list(_baselines.keys())}")
    print(f"  Recordings: {list(_recordings.keys())}")


def main():
    """Main entry point."""
    print("=" * 60)
    print("Sensor Analysis Demo Data Loader")
    print("Phase 41-03: Vibration & Audio Analysis via phyphox")
    print("=" * 60)
    print()

    load_demo_data()

    # Print summary for each equipment
    print("\n" + "=" * 60)
    print("Equipment Summary")
    print("=" * 60)

    for equipment_id in sorted(set(_baselines.keys()) | set(_recordings.keys())):
        baseline = _baselines.get(equipment_id, {})
        recordings = _recordings.get(equipment_id, [])

        name = baseline.get("equipment_name", "Unknown")
        eq_type = baseline.get("equipment_type", "unknown")
        condition = baseline.get("condition_at_capture", "N/A")

        print(f"\n{equipment_id}: {name} ({eq_type})")
        print(f"  Baseline condition: {condition}")
        print(f"  Baseline RMS: {baseline.get('vibration_rms_ms2', 'N/A')} m/s^2")
        print(f"  Recordings: {len(recordings)}")

        if recordings:
            latest = recordings[-1]
            print(f"  Latest RMS: {latest.get('rms_total_ms2', 'N/A')} m/s^2")
            if "anomalies" in latest:
                anom = latest["anomalies"]
                print(f"  ANOMALY: {anom['type']} ({anom['severity']})")


if __name__ == "__main__":
    main()
