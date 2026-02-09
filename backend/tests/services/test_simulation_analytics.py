"""
Tests for simulation analytics pipeline — event instrumentation fixes.

Verifies that:
1. AI optimization emits per-equipment events with equipment_id
2. Setpoint changes carry equipment context
3. Runtime tracking is populated from equipment-level events
4. Building-level events (building_wake, peak_load) are excluded from runtime
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.services.simulation_analyzer import SimulationAnalyzer
from app.models.simulation_analytics import SimulationMetrics


@pytest.fixture
def log_dir(tmp_path):
    """Create a temporary log directory."""
    return tmp_path


def _write_events(log_dir: Path, run_id: str, events: list):
    """Helper: write events JSONL + minimal metadata."""
    events_path = log_dir / f"{run_id}_events.jsonl"
    with open(events_path, "w") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")

    meta = {
        "run_id": run_id,
        "scenario": "test",
        "building_code": "site-002",
        "started_at": datetime.now().isoformat(),
        "ended_at": datetime.now().isoformat(),
        "duration_minutes": 2.0,
        "event_count": len(events),
        "events_file": str(events_path),
    }
    meta_path = log_dir / f"{run_id}_meta.json"
    meta_path.write_text(json.dumps(meta))


class TestPerEquipmentOptimizationEvents:
    """A1: AI optimization should emit per-equipment events with equipment_id."""

    def test_per_equipment_events_have_equipment_id(self, log_dir):
        events = [
            # Per-equipment optimization events (from A1 fix)
            {
                "timestamp": datetime.now().isoformat(),
                "simulated_hour": 10,
                "event_type": "ai_optimization",
                "equipment_id": "S002-AHU-L2-001",
                "equipment_name": "AHU Level 2",
                "description": "AI optimization: Reduced fan speed 10% on AHU Level 2",
                "details": {"context": "mid_morning", "adjustment": "Reduced fan speed 10%"},
            },
            {
                "timestamp": datetime.now().isoformat(),
                "simulated_hour": 10,
                "event_type": "ai_optimization",
                "equipment_id": "S002-CHILLER-B1-001",
                "equipment_name": "Chiller 1",
                "description": "AI optimization: Optimized staging on Chiller 1",
                "details": {"context": "mid_morning", "adjustment": "Optimized staging"},
            },
            # Summary event (no equipment_id) — should count as 1 ai_optimization
            {
                "timestamp": datetime.now().isoformat(),
                "simulated_hour": 10,
                "event_type": "ai_optimization",
                "description": "AI optimization cycle (mid_morning)",
                "details": {"context": "mid_morning", "summary": True, "optimizations_applied": 2},
            },
        ]
        _write_events(log_dir, "run_opt", events)
        analyzer = SimulationAnalyzer(log_dir=log_dir)
        metrics = analyzer.compute_metrics("run_opt")

        # Only the summary event should increment ai_optimizations
        assert metrics.ai_optimizations == 1

        # But runtime tracking should have both equipment
        assert "S002-AHU-L2-001" in metrics.equipment_runtime_hours
        assert "S002-CHILLER-B1-001" in metrics.equipment_runtime_hours


class TestSetpointWithEquipment:
    """A2: Setpoint changes should carry equipment_id when available."""

    def test_setpoint_events_tracked_in_runtime(self, log_dir):
        events = [
            {
                "timestamp": datetime.now().isoformat(),
                "simulated_hour": 8,
                "event_type": "setpoint_change",
                "equipment_id": "S002-FCU-L1-A",
                "equipment_name": "FCU L1 Zone A",
                "description": "Setpoint change: cooling_setpoint → 22.0",
                "details": {"point": "cooling_setpoint", "value": 22.0, "reason": "Occupied mode"},
            },
            {
                "timestamp": datetime.now().isoformat(),
                "simulated_hour": 8,
                "event_type": "setpoint_change",
                "equipment_id": "S002-DALI-L1-A",
                "equipment_name": "DALI L1 Zone A",
                "description": "Setpoint change: lighting_level → 80",
                "details": {"point": "lighting_level", "value": 80, "reason": "Occupied mode"},
            },
        ]
        _write_events(log_dir, "run_sp", events)
        analyzer = SimulationAnalyzer(log_dir=log_dir)
        metrics = analyzer.compute_metrics("run_sp")

        assert metrics.setpoint_changes == 2
        assert "S002-FCU-L1-A" in metrics.equipment_runtime_hours
        assert "S002-DALI-L1-A" in metrics.equipment_runtime_hours


class TestRuntimeTrackingPopulated:
    """A3: Runtime tracking should be populated from equipment-level events."""

    def test_fault_and_repair_contribute_to_runtime(self, log_dir):
        ts = datetime.now().isoformat()
        events = [
            {
                "timestamp": ts,
                "simulated_hour": 11,
                "event_type": "equipment_fault",
                "equipment_id": "S002-CHILLER-B1-001",
                "equipment_name": "Chiller 1",
                "description": "High vibration on Chiller 1",
                "details": {"fault_type": "High vibration detected"},
            },
            {
                "timestamp": ts,
                "simulated_hour": 13,
                "event_type": "repair_completed",
                "equipment_id": "S002-CHILLER-B1-001",
                "equipment_name": "Chiller 1",
                "description": "Repair completed on Chiller 1",
                "details": {},
            },
        ]
        _write_events(log_dir, "run_fr", events)
        analyzer = SimulationAnalyzer(log_dir=log_dir)
        metrics = analyzer.compute_metrics("run_fr")

        # equipment_fault + repair_completed = 2 runtime entries
        assert metrics.equipment_runtime_hours.get("S002-CHILLER-B1-001") == 2
        assert metrics.total_faults == 1
        assert metrics.faults_repaired == 1


class TestBuildingLevelEventsExcluded:
    """Building-level events should NOT appear in equipment_runtime_hours."""

    def test_building_events_excluded_from_runtime(self, log_dir):
        events = [
            {
                "timestamp": datetime.now().isoformat(),
                "simulated_hour": 6,
                "event_type": "building_wake",
                "description": "Building systems starting up",
                "details": {},
            },
            {
                "timestamp": datetime.now().isoformat(),
                "simulated_hour": 8,
                "event_type": "occupancy_increase",
                "description": "Staff arriving",
                "details": {"occupancy_percent": 60},
            },
            {
                "timestamp": datetime.now().isoformat(),
                "simulated_hour": 11,
                "event_type": "peak_load",
                "description": "Peak demand",
                "details": {"load_percent": 95},
            },
        ]
        _write_events(log_dir, "run_bl", events)
        analyzer = SimulationAnalyzer(log_dir=log_dir)
        metrics = analyzer.compute_metrics("run_bl")

        # None of these events have equipment_id, so runtime should be empty
        assert len(metrics.equipment_runtime_hours) == 0
        assert metrics.total_events == 3
