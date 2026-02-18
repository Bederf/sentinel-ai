#!/usr/bin/env python3
"""
Demo Workflow Data Setup Script

Phase 53-03: Setup demo data for SENTINEL asset management workflow

Creates a complete demo building with 3 equipment at different lifecycle stages:
- Chiller-001: Degradation story (active monitoring → anomaly → repair validated)
- Generator-002: Success story (healthy with routine inspections)
- AHU-003: Current issue story (anomaly detected, inspection pending)

Usage:
    cd backend
    python scripts/setup_demo_workflow_data.py
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.baseline import (
    BaselineStatus,
    BaselineSource
)
from app.models.inspection import (
    InspectionScheduleFrequency,
    InspectionOverallStatus,
    DeficiencySeverity,
    DeficiencyCategory
)


# ============================================================================
# Demo Building Configuration
# ============================================================================

DEMO_BUILDING = {
    "building_id": "sandton-mall-demo",
    "name": "Sandton City Mall",
    "address": "83 5th St, Sandton, South Africa",
    "description": "Demo building for SENTINEL asset management workflow"
}

DEMO_EQUIPMENT = [
    {
        "equipment_id": "chiller-001",
        "equipment_type": "chiller",
        "name": "Main Chiller",
        "manufacturer": "York",
        "model": "YCIV",
        "capacity_kw": 450,
        "install_date": "2005-08-01",
        "criticality": "high",
        "location": "Basement Plant Room",
        "serial_number": "YRK-YCIV-2005-001",
        "story": "degradation"  # Active monitoring → Anomaly → Repair validated
    },
    {
        "equipment_id": "generator-002",
        "equipment_type": "generator",
        "name": "Standby Generator #2",
        "manufacturer": "Cummins",
        "model": "C500D5",
        "capacity_kw": 500,
        "install_date": "2018-03-15",
        "criticality": "high",
        "location": "Generator Yard",
        "serial_number": "CUM-C500D5-2018-002",
        "story": "success"  # Healthy with routine inspections
    },
    {
        "equipment_id": "ahu-003",
        "equipment_type": "ahu",
        "name": "Level 3 AHU",
        "manufacturer": "Carrier",
        "model": "39M-120",
        "capacity_kw": 120,
        "install_date": "2019-06-10",
        "criticality": "medium",
        "location": "Level 3 Plant Room",
        "serial_number": "CAR-39M120-2019-003",
        "story": "current_issue"  # Anomaly just detected, inspection pending
    }
]


# ============================================================================
# Chiller-001: Degradation Story Baselines
# ============================================================================

CHILLER_001_BASELINES = [
    {
        "baseline_type": "initial",
        "captured_date": "2025-08-01T10:00:00Z",
        "captured_by": "Mike Chen",
        "baseline_values": {
            "vibration_rms": 1.8,
            "motor_current": 145.2,
            "bearing_temp": 45.1,
            "chw_supply_temp": 7.2,
            "chw_return_temp": 12.5,
            "suction_pressure": 4.2,
            "discharge_pressure": 15.8
        },
        "measurement_conditions": {
            "ambient_temp": 22.0,
            "load_percentage": 75,
            "weather": "clear"
        },
        "notes": "Commissioning baseline - all values normal"
    },
    {
        "baseline_type": "periodic",
        "captured_date": "2025-11-01T10:00:00Z",
        "captured_by": "Sarah Johnson",
        "baseline_values": {
            "vibration_rms": 2.5,  # +39%
            "motor_current": 148.1,
            "bearing_temp": 48.3,
            "chw_supply_temp": 7.5,
            "chw_return_temp": 12.8,
            "suction_pressure": 4.1,
            "discharge_pressure": 15.5
        },
        "measurement_conditions": {
            "ambient_temp": 24.0,
            "load_percentage": 80,
            "weather": "partly_cloudy"
        },
        "notes": "Scheduled quarterly check - vibration elevated 39% from baseline"
    },
    {
        "baseline_type": "periodic",
        "captured_date": "2026-01-15T14:30:00Z",
        "captured_by": "Mike Chen",
        "baseline_values": {
            "vibration_rms": 4.2,  # +133% from initial
            "motor_current": 168.0,  # +16%
            "bearing_temp": 85.0,  # Critical!
            "chw_supply_temp": 8.8,
            "chw_return_temp": 14.2,
            "suction_pressure": 3.8,
            "discharge_pressure": 14.2
        },
        "measurement_conditions": {
            "ambient_temp": 28.0,
            "load_percentage": 85,
            "weather": "hot"
        },
        "notes": "Special inspection - critical bearing failure imminent. Vibration 133% above baseline."
    },
    {
        "baseline_type": "post_repair",
        "captured_date": "2026-01-20T16:00:00Z",
        "captured_by": "Sarah Johnson",
        "baseline_values": {
            "vibration_rms": 1.9,  # Back to normal!
            "motor_current": 146.0,
            "bearing_temp": 46.0,  # Normal
            "chw_supply_temp": 7.1,
            "chw_return_temp": 12.4,
            "suction_pressure": 4.2,
            "discharge_pressure": 15.7
        },
        "measurement_conditions": {
            "ambient_temp": 23.0,
            "load_percentage": 75,
            "weather": "clear"
        },
        "notes": "Post-repair baseline after compressor bearing replacement. All values normal."
    }
]


# ============================================================================
# Generator-002: Healthy Baseline
# ============================================================================

GENERATOR_002_BASELINES = [
    {
        "baseline_type": "initial",
        "captured_date": "2018-03-15T11:00:00Z",
        "captured_by": "John Smith",
        "baseline_values": {
            "engine_temperature": 82.0,
            "oil_pressure": 65.0,
            "fuel_pressure": 35.0,
            "battery_voltage": 13.8,
            "frequency": 50.0,
            "voltage_l1": 400.0,
            "voltage_l2": 400.0,
            "voltage_l3": 400.0
        },
        "measurement_conditions": {
            "ambient_temp": 25.0,
            "load_kw": 250,
            "fuel_level": 85
        },
        "notes": "Commissioning baseline after installation"
    },
    {
        "baseline_type": "periodic",
        "captured_date": "2026-01-10T09:00:00Z",
        "captured_by": "John Smith",
        "baseline_values": {
            "engine_temperature": 83.5,
            "oil_pressure": 64.0,
            "fuel_pressure": 34.5,
            "battery_voltage": 13.6,
            "frequency": 49.95,
            "voltage_l1": 398.0,
            "voltage_l2": 399.0,
            "voltage_l3": 398.5
        },
        "measurement_conditions": {
            "ambient_temp": 24.0,
            "load_kw": 275,
            "fuel_level": 80
        },
        "notes": "Annual inspection - all values within normal range. No deviations."
    }
]


# ============================================================================
# AHU-003: Current Issue Baseline
# ============================================================================

AHU_003_BASELINES = [
    {
        "baseline_type": "initial",
        "captured_date": "2019-06-10T10:00:00Z",
        "captured_by": "Mike Chen",
        "baseline_values": {
            "fan_motor_current": 12.5,
            "fan_speed_rpm": 1450,
            "filter_pressure_drop": 75,
            "supply_air_temp": 14.0,
            "return_air_temp": 24.0,
            "vibration_level": 2.2
        },
        "measurement_conditions": {
            "ambient_temp": 23.0,
            "damper_position": 80
        },
        "notes": "Commissioning baseline"
    },
    {
        "baseline_type": "periodic",
        "captured_date": "2026-01-28T11:30:00Z",
        "captured_by": "Automated",
        "baseline_values": {
            "fan_motor_current": 14.8,  # +18%
            "fan_speed_rpm": 1420,
            "filter_pressure_drop": 180,  # +140%
            "supply_air_temp": 16.5,
            "return_air_temp": 25.0,
            "vibration_level": 3.8  # +73%
        },
        "measurement_conditions": {
            "ambient_temp": 26.0,
            "damper_position": 85
        },
        "notes": "Automated baseline - ML detected anomaly. Fan motor showing early bearing degradation."
    }
]


# ============================================================================
# Chiller-001: Inspection History
# ============================================================================

CHILLER_001_INSPECTIONS = [
    {
        "inspection_date": "2025-09-01T10:00:00Z",
        "inspector": "Mike Chen",
        "status": InspectionOverallStatus.PASS,
        "findings": "All parameters normal. No issues detected.",
        "deficiencies": []
    },
    {
        "inspection_date": "2025-10-01T10:00:00Z",
        "inspector": "Sarah Johnson",
        "status": InspectionOverallStatus.PASS,
        "findings": "All parameters normal. Minor cleaning required on condenser coils.",
        "deficiencies": []
    },
    {
        "inspection_date": "2025-11-01T10:00:00Z",
        "inspector": "Mike Chen",
        "status": InspectionOverallStatus.PASS,
        "findings": "Vibration elevated (2.5 vs 1.8 baseline). Recommend monitoring.",
        "deficiencies": []
    },
    {
        "inspection_date": "2025-12-01T10:00:00Z",
        "inspector": "Sarah Johnson",
        "status": InspectionOverallStatus.PASS,
        "findings": "Vibration increasing (3.1 vs 1.8 baseline). Recommend trending analysis.",
        "deficiencies": []
    },
    {
        "inspection_date": "2026-01-01T10:00:00Z",
        "inspector": "Mike Chen",
        "status": InspectionOverallStatus.FAIL,
        "findings": "Vibration critical (3.8 vs 1. baseline). Frequency analysis confirms bearing defect.",
        "deficiencies": [
            {
                "title": "Critical Compressor Bearing Wear",
                "severity": DeficiencySeverity.CRITICAL,
                "category": DeficiencyCategory.MECHANICAL,
                "description": "Vibration at 3.8 mm/s is 111% above baseline. Frequency analysis confirms bearing defect.",
                "recommended_action": "Replace compressor bearing before catastrophic failure",
                "estimated_repair_cost_min": 5000,
                "estimated_repair_cost_max": 8000,
                "estimated_repair_hours": 6
            }
        ]
    },
    {
        "inspection_date": "2026-01-22T10:00:00Z",
        "inspector": "Sarah Johnson",
        "status": InspectionOverallStatus.PASS,
        "findings": "Post-repair verification. Vibration back to normal (1.9 mm/s). Repair successful.",
        "deficiencies": []
    }
]


# ============================================================================
# ML Predictions for Demo Equipment
# ============================================================================

ML_PREDICTIONS = {
    "chiller-001": {
        "prediction_type": "failure",
        "failure_probability": 0.85,
        "timeframe": "7 days",
        "confidence": "high",
        "contributing_factors": [
            {"factor": "Bearing vibration trend", "weight": 0.40, "value": "+111% from baseline"},
            {"factor": "Motor current increase", "weight": 0.25, "value": "+16% from baseline"},
            {"factor": "Bearing temperature", "weight": 0.20, "value": "85°C vs 45°C baseline"},
            {"factor": "Asset age", "weight": 0.10, "value": "21 years (exceeds 20-year life)"},
            {"factor": "Repeat calls", "weight": 0.05, "value": "3 vibration complaints in 6 months"}
        ],
        "explanation": "The chiller shows declining efficiency indicating refrigerant leak and bearing wear. Vibration levels are 111% above baseline with bearing temperature at critical 85°C. Asset age exceeds recommended 20-year lifespan.",
        "actions": [
            {
                "description": "Replace compressor bearing",
                "urgency": "critical",
                "estimated_time_hours": 6,
                "estimated_cost": 6500
            }
        ]
    },
    "generator-002": {
        "prediction_type": "healthy",
        "failure_probability": 0.05,
        "timeframe": "90 days",
        "confidence": "high",
        "contributing_factors": [],
        "explanation": "All parameters within normal range. No anomalies detected. Asset is 7 years old with no significant wear indicators.",
        "actions": []
    },
    "ahu-003": {
        "prediction_type": "failure",
        "failure_probability": 0.72,
        "timeframe": "14 days",
        "confidence": "medium",
        "contributing_factors": [
            {"factor": "Fan motor vibration", "weight": 0.45, "value": "+73% from baseline"},
            {"factor": "Motor current increase", "weight": 0.30, "value": "+18% from baseline"},
            {"factor": "Filter pressure drop", "weight": 0.15, "value": "+140% (clogged)"},
            {"factor": "Age-related wear", "weight": 0.10, "value": "7 years moderate usage"}
        ],
        "explanation": "Fan motor showing early signs of bearing degradation. Vibration up 73% with elevated current draw. Filter severely clogged - replace immediately.",
        "actions": [
            {
                "description": "Replace fan motor bearings",
                "urgency": "high",
                "estimated_time_hours": 4,
                "estimated_cost": 2800
            },
            {
                "description": "Replace air filter",
                "urgency": "high",
                "estimated_time_hours": 0.5,
                "estimated_cost": 150
            }
        ]
    }
}


# ============================================================================
# Data Storage Helpers
# ============================================================================

class DemoDataStore:
    """In-memory storage for demo workflow data."""

    def __init__(self):
        self.baselines: Dict[str, List[Dict]] = {}
        self.inspections: Dict[str, List[Dict]] = {}
        self.inspection_schedules: Dict[str, List[Dict]] = {}
        self.deficiencies: Dict[str, List[Dict]] = {}
        self.work_orders: Dict[str, List[Dict]] = {}
        self.ml_predictions: Dict[str, Dict] = {}
        self.equipment: Dict[str, Dict] = {}

    def add_baseline(self, equipment_id: str, baseline: Dict):
        """Add baseline for equipment."""
        if equipment_id not in self.baselines:
            self.baselines[equipment_id] = []
        baseline["id"] = f"bl-{equipment_id}-{len(self.baselines[equipment_id]) + 1}"
        baseline["created_at"] = datetime.now().isoformat()
        baseline["updated_at"] = datetime.now().isoformat()
        self.baselines[equipment_id].append(baseline)

    def add_inspection(self, equipment_id: str, inspection: Dict):
        """Add inspection result for equipment."""
        if equipment_id not in self.inspections:
            self.inspections[equipment_id] = []
        inspection["id"] = f"ins-{equipment_id}-{len(self.inspections[equipment_id]) + 1}"
        inspection["created_at"] = datetime.now().isoformat()
        self.inspections[equipment_id].append(inspection)

    def add_schedule(self, equipment_id: str, schedule: Dict):
        """Add inspection schedule for equipment."""
        if equipment_id not in self.inspection_schedules:
            self.inspection_schedules[equipment_id] = []
        schedule["id"] = f"sch-{equipment_id}-{len(self.inspection_schedules[equipment_id]) + 1}"
        schedule["created_at"] = datetime.now().isoformat()
        schedule["updated_at"] = datetime.now().isoformat()
        self.inspection_schedules[equipment_id].append(schedule)

    def add_deficiency(self, equipment_id: str, deficiency: Dict):
        """Add deficiency for equipment."""
        if equipment_id not in self.deficiencies:
            self.deficiencies[equipment_id] = []
        deficiency["id"] = f"def-{equipment_id}-{len(self.deficiencies[equipment_id]) + 1}"
        deficiency["created_at"] = datetime.now().isoformat()
        self.deficiencies[equipment_id].append(deficiency)

    def add_work_order(self, equipment_id: str, work_order: Dict):
        """Add work order for equipment."""
        if equipment_id not in self.work_orders:
            self.work_orders[equipment_id] = []
        work_order["id"] = f"wo-{equipment_id}-{len(self.work_orders[equipment_id]) + 1}"
        work_order["created_at"] = datetime.now().isoformat()
        self.work_orders[equipment_id].append(work_order)

    def add_prediction(self, equipment_id: str, prediction: Dict):
        """Add ML prediction for equipment."""
        prediction["id"] = f"pred-{equipment_id}"
        prediction["created_at"] = datetime.now().isoformat()
        self.ml_predictions[equipment_id] = prediction

    def add_equipment(self, equipment: Dict):
        """Add equipment to registry."""
        equipment_id = equipment["equipment_id"]
        equipment["created_at"] = datetime.now().isoformat()
        self.equipment[equipment_id] = equipment


# ============================================================================
# Setup Functions
# ============================================================================

async def setup_chiller_001_lifecycle(store: DemoDataStore):
    """Create complete lifecycle data for chiller-001 degradation story."""
    print("  Setting up Chiller-001 lifecycle data...")

    equipment_id = "chiller-001"

    # 1. Add baselines showing degradation
    for bl_data in CHILLER_001_BASELINES:
        baseline = {
            "equipment_id": equipment_id,
            "baseline_date": bl_data["captured_date"],
            "captured_by": bl_data["captured_by"],
            "baseline_type": bl_data["baseline_type"],
            "status": BaselineStatus.ACTIVE if bl_data["baseline_type"] == "post_repair" else BaselineStatus.SUPERSEDED,
            "baseline_values": bl_data["baseline_values"],
            "measurement_conditions": bl_data["measurement_conditions"],
            "source_type": BaselineSource.MANUAL,
            "notes": bl_data["notes"]
        }
        store.add_baseline(equipment_id, baseline)

    # 2. Add inspection history
    for insp_data in CHILLER_001_INSPECTIONS:
        inspection = {
            "equipment_id": equipment_id,
            "inspection_date": insp_data["inspection_date"],
            "inspector": insp_data["inspector"],
            "overall_status": insp_data["status"],
            "findings": insp_data["findings"],
            "checklist_results": {},
            "deficiencies": insp_data["deficiencies"]
        }
        store.add_inspection(equipment_id, inspection)

        # Track deficiencies separately
        for def_data in insp_data.get("deficiencies", []):
            store.add_deficiency(equipment_id, {
                **def_data,
                "equipment_id": equipment_id,
                "discovered_date": insp_data["inspection_date"]
            })

    # 3. Add monthly inspection schedule
    schedule = {
        "equipment_id": equipment_id,
        "schedule_name": "Monthly Chiller Inspection",
        "schedule_description": "Monthly inspection with vibration analysis",
        "frequency_type": InspectionScheduleFrequency.MONTHLY,
        "estimated_duration_minutes": 90,
        "assigned_to": "Mike Chen",
        "is_active": True
    }
    store.add_schedule(equipment_id, schedule)

    # 4. Add ML prediction (pre-repair state)
    prediction = ML_PREDICTIONS["chiller-001"].copy()
    prediction["generated_at"] = "2026-01-15T12:00:00Z"
    prediction["status"] = "resolved"  # Resolved after repair
    store.add_prediction(equipment_id, prediction)

    # 5. Add work order for bearing replacement
    work_order = {
        "equipment_id": equipment_id,
        "title": "Replace Compressor Bearing",
        "description": "Critical bearing wear detected. Replace bearing assembly.",
        "priority": "urgent",
        "status": "completed",
        "created_date": "2026-01-15T14:00:00Z",
        "assigned_to": "Sarah Johnson",
        "estimated_cost": 6500,
        "actual_cost": 6200,
        "estimated_hours": 6,
        "actual_hours": 5.5,
        "completion_date": "2026-01-20T16:00:00Z"
    }
    store.add_work_order(equipment_id, work_order)

    print(f"    ✓ {len(CHILLER_001_BASELINES)} baselines")
    print(f"    ✓ {len(CHILLER_001_INSPECTIONS)} inspections")
    print("    ✓ 1 schedule")
    print("    ✓ 1 ML prediction")
    print("    ✓ 1 work order (completed)")


async def setup_generator_002_healthy(store: DemoDataStore):
    """Create healthy baseline data for generator-002 success story."""
    print("  Setting up Generator-002 healthy data...")

    equipment_id = "generator-002"

    # 1. Add stable baselines
    for bl_data in GENERATOR_002_BASELINES:
        baseline = {
            "equipment_id": equipment_id,
            "baseline_date": bl_data["captured_date"],
            "captured_by": bl_data["captured_by"],
            "baseline_type": bl_data["baseline_type"],
            "status": BaselineStatus.ACTIVE if bl_data["baseline_type"] == "periodic" else BaselineStatus.SUPERSEDED,
            "baseline_values": bl_data["baseline_values"],
            "measurement_conditions": bl_data["measurement_conditions"],
            "source_type": BaselineSource.MANUAL,
            "notes": bl_data["notes"]
        }
        store.add_baseline(equipment_id, baseline)

    # 2. Add quarterly inspection schedule
    schedule = {
        "equipment_id": equipment_id,
        "schedule_name": "Quarterly Generator Inspection",
        "schedule_description": "Quarterly preventive maintenance inspection",
        "frequency_type": InspectionScheduleFrequency.QUARTERLY,
        "estimated_duration_minutes": 120,
        "assigned_to": "John Smith",
        "is_active": True
    }
    store.add_schedule(equipment_id, schedule)

    # 3. Add healthy ML prediction
    prediction = ML_PREDICTIONS["generator-002"].copy()
    prediction["generated_at"] = datetime.now().isoformat()
    prediction["status"] = "active"
    store.add_prediction(equipment_id, prediction)

    print(f"    ✓ {len(GENERATOR_002_BASELINES)} baselines")
    print("    ✓ 1 schedule")
    print("    ✓ 1 ML prediction (healthy)")


async def setup_ahu_003_issue(store: DemoDataStore):
    """Create current issue data for ahu-003 active problem story."""
    print("  Setting up AHU-003 current issue data...")

    equipment_id = "ahu-003"

    # 1. Add baselines (initial + recent deviation)
    for bl_data in AHU_003_BASELINES:
        baseline = {
            "equipment_id": equipment_id,
            "baseline_date": bl_data["captured_date"],
            "captured_by": bl_data["captured_by"],
            "baseline_type": bl_data["baseline_type"],
            "status": BaselineStatus.ACTIVE if bl_data["baseline_type"] == "periodic" else BaselineStatus.SUPERSEDED,
            "baseline_values": bl_data["baseline_values"],
            "measurement_conditions": bl_data["measurement_conditions"],
            "source_type": BaselineSource.AUTOMATED if bl_data["captured_by"] == "Automated" else BaselineSource.MANUAL,
            "notes": bl_data["notes"]
        }
        store.add_baseline(equipment_id, baseline)

    # 2. Add monthly inspection schedule
    schedule = {
        "equipment_id": equipment_id,
        "schedule_name": "Monthly AHU Inspection",
        "schedule_description": "Monthly inspection with filter check",
        "frequency_type": InspectionScheduleFrequency.MONTHLY,
        "estimated_duration_minutes": 60,
        "assigned_to": "Mike Chen",
        "is_active": True
    }
    store.add_schedule(equipment_id, schedule)

    # 3. Add active ML prediction
    prediction = ML_PREDICTIONS["ahu-003"].copy()
    prediction["generated_at"] = datetime.now().isoformat()
    prediction["status"] = "active"
    store.add_prediction(equipment_id, prediction)

    # 4. Create pending inspection task (triggered by ML)
    inspection_task = {
        "equipment_id": equipment_id,
        "task_type": "special",
        "priority": "high",
        "status": "scheduled",
        "due_date": (datetime.now() + timedelta(days=1)).isoformat(),
        "assigned_to": "Mike Chen",
        "triggered_by": "ml_anomaly",
        "description": "ML detected fan motor bearing degradation. Verify and inspect."
    }
    # Store as inspection
    store.add_inspection(equipment_id, {
        "equipment_id": equipment_id,
        "inspection_date": inspection_task["due_date"],
        "inspector": inspection_task["assigned_to"],
        "overall_status": InspectionOverallStatus.PASS,
        "findings": "Scheduled inspection pending",
        "checklist_results": {},
        "deficiencies": [],
        "_task": inspection_task
    })

    print(f"    ✓ {len(AHU_003_BASELINES)} baselines")
    print("    ✓ 1 schedule")
    print("    ✓ 1 ML prediction (active)")
    print("    ✓ 1 pending inspection task")


async def setup_demo_workflow_data():
    """Create complete demo building with workflow data."""
    print("=" * 70)
    print("SENTINEL Demo Workflow Data Setup")
    print("=" * 70)
    print()

    # Initialize data store
    store = DemoDataStore()

    # 1. Create building
    print("1. Creating demo building...")
    print(f"   Building: {DEMO_BUILDING['name']}")
    print(f"   Address: {DEMO_BUILDING['address']}")
    print()

    # 2. Onboard equipment
    print("2. Onboarding equipment...")
    for eq in DEMO_EQUIPMENT:
        store.add_equipment(eq)
        print(f"   ✓ {eq['equipment_id']}: {eq['name']} ({eq['story']} story)")
    print()

    # 3. Setup equipment lifecycle data
    print("3. Creating equipment lifecycle data...")
    print()

    await setup_chiller_001_lifecycle(store)
    print()

    await setup_generator_002_healthy(store)
    print()

    await setup_ahu_003_issue(store)
    print()

    # 4. Save to JSON files
    print("4. Saving demo data to JSON files...")

    output_dir = Path("/opt/bms-intelligence/backend/app/data/demo_workflow")
    output_dir.mkdir(exist_ok=True)

    # Save building data
    building_file = output_dir / "building.json"
    with open(building_file, 'w') as f:
        json.dump({
            **DEMO_BUILDING,
            "equipment": [eq["equipment_id"] for eq in DEMO_EQUIPMENT]
        }, f, indent=2)
    print(f"   ✓ {building_file}")

    # Save equipment data
    equipment_file = output_dir / "equipment.json"
    with open(equipment_file, 'w') as f:
        json.dump({eq["equipment_id"]: eq for eq in DEMO_EQUIPMENT}, f, indent=2)
    print(f"   ✓ {equipment_file}")

    # Save baselines
    baselines_file = output_dir / "baselines.json"
    with open(baselines_file, 'w') as f:
        json.dump(store.baselines, f, indent=2)
    print(f"   ✓ {baselines_file}")

    # Save inspections
    inspections_file = output_dir / "inspections.json"
    with open(inspections_file, 'w') as f:
        json.dump(store.inspections, f, indent=2)
    print(f"   ✓ {inspections_file}")

    # Save schedules
    schedules_file = output_dir / "schedules.json"
    with open(schedules_file, 'w') as f:
        json.dump(store.inspection_schedules, f, indent=2)
    print(f"   ✓ {schedules_file}")

    # Save deficiencies
    deficiencies_file = output_dir / "deficiencies.json"
    with open(deficiencies_file, 'w') as f:
        json.dump(store.deficiencies, f, indent=2)
    print(f"   ✓ {deficiencies_file}")

    # Save work orders
    work_orders_file = output_dir / "work_orders.json"
    with open(work_orders_file, 'w') as f:
        json.dump(store.work_orders, f, indent=2)
    print(f"   ✓ {work_orders_file}")

    # Save ML predictions
    predictions_file = output_dir / "ml_predictions.json"
    with open(predictions_file, 'w') as f:
        json.dump(store.ml_predictions, f, indent=2)
    print(f"   ✓ {predictions_file}")

    print()
    print("=" * 70)
    print("Demo workflow data setup complete!")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  - Equipment: {len(store.equipment)}")
    print(f"  - Baselines: {sum(len(v) for v in store.baselines.values())}")
    print(f"  - Inspections: {sum(len(v) for v in store.inspections.values())}")
    print(f"  - Schedules: {sum(len(v) for v in store.inspection_schedules.values())}")
    print(f"  - Deficiencies: {sum(len(v) for v in store.deficiencies.values())}")
    print(f"  - Work Orders: {sum(len(v) for v in store.work_orders.values())}")
    print(f"  - ML Predictions: {len(store.ml_predictions)}")
    print()
    print(f"Output directory: {output_dir}")
    print()


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    asyncio.run(setup_demo_workflow_data())
