"""Smart Dispatch Service - Intelligent dispatch decisions with task bundling.

Phase 59-03: Remote Operations
Reduces truck rolls by 50%+ through intelligent dispatch decisions.
When dispatch IS needed, maximizes efficiency by bundling tasks in the
same building/zone using a "while you're there" approach.

Integrates with:
  - RemoteMonitoringService for equipment diagnostics
  - DeviceManager for real-time device status
  - WorkOrderService for open work orders
  - Safety data for alarmed/warning devices
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.site_resolver import get_primary_site_code
from app.services.device_abstraction import device_manager
from app.services.remote_monitoring_service import get_remote_monitoring_service
from app.services.work_order_service import work_order_service

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
TECHNICIANS_FILE = DATA_DIR / "technicians.json"  # Deprecated — Supabase is source of truth

# Floor ordering for efficient routing (bottom to top)
FLOOR_ORDER = {"B2": 0, "B1": 1, "G": 2, "L0": 3, "L1": 4, "L2": 5, "L3": 6, "R": 7}

# Specialization mapping from equipment type to required skill
EQUIPMENT_SPECIALIZATION: dict[str, str] = {
    "chiller": "hvac",
    "ahu": "hvac",
    "fcu": "hvac",
    "vav": "hvac",
    "boiler": "hvac",
    "cooling_tower": "hvac",
    "pump": "hvac",
    "generator": "electrical",
    "ups": "electrical",
    "transformer": "electrical",
    "meter": "electrical",
    "dali": "electrical",
    "fire": "fire_safety",
    "acc": "general",
}

# Estimated task durations (minutes) by type
TASK_DURATION_ESTIMATES: dict[str, int] = {
    "safety_violation": 45,
    "anomaly_investigation": 30,
    "work_order": 60,
    "device_warning": 20,
    "device_alarm": 40,
    "overdue_inspection": 45,
    "visual_inspection": 15,
    "sensor_calibration": 20,
}

# Tools commonly needed by task type
TOOLS_BY_TASK_TYPE: dict[str, list[str]] = {
    "safety_violation": ["multimeter", "PPE kit", "lockout/tagout kit"],
    "anomaly_investigation": ["multimeter", "thermal camera", "vibration meter"],
    "work_order": ["basic tool kit", "spare parts (per WO)"],
    "device_warning": ["multimeter", "laptop with BMS software"],
    "device_alarm": ["multimeter", "thermal camera", "PPE kit"],
    "overdue_inspection": ["inspection checklist", "camera", "vibration meter"],
    "visual_inspection": ["camera", "flashlight"],
    "sensor_calibration": ["calibration kit", "reference instruments"],
}


class SmartDispatchService:
    """Singleton service for intelligent dispatch decisions with task bundling.

    Key capabilities:
      - Evaluate whether dispatch is needed or issue can be resolved remotely
      - Bundle nearby tasks at same site ("while you're there")
      - Assign best-fit technician based on specialization and proximity
      - Generate structured site briefings for field technicians
      - Track active dispatches from creation through completion
    """

    _instance: Optional["SmartDispatchService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._technicians: list[dict[str, Any]] = []
        self._active_dispatches: dict[str, dict[str, Any]] = {}
        self._completed_dispatches: list[dict[str, Any]] = []
        self._load_technicians()
        self._initialized = True
        logger.info(f"SmartDispatchService initialized with {len(self._technicians)} technicians")

    def _load_technicians(self) -> None:
        """Load technician data from Supabase (source of truth)."""
        try:
            from app.database.supabase_client import get_supabase_client
            client = get_supabase_client()
            if client:
                result = client.table("technicians").select("*").eq("active", True).execute()
                if result.data:
                    self._technicians = result.data
                    logger.info(f"Loaded {len(self._technicians)} technicians from Supabase")
                    return
            logger.warning("Supabase unavailable, falling back to local file")
            if TECHNICIANS_FILE.exists():
                with open(TECHNICIANS_FILE) as f:
                    self._technicians = json.load(f).get("technicians", [])
                logger.info(f"Loaded {len(self._technicians)} technicians from fallback file")
            else:
                self._technicians = []
        except Exception as e:
            logger.error(f"Failed to load technicians: {e}")
            self._technicians = []

    # ------------------------------------------------------------------
    # Dispatch decision engine
    # ------------------------------------------------------------------

    async def evaluate_dispatch(self, equipment_id: str) -> dict[str, Any]:
        """Evaluate whether a technician dispatch is needed for equipment.

        Steps:
        1. Get equipment diagnostic from RemoteMonitoringService
        2. Check if issue can be resolved remotely (fault reset, setpoint adjust)
        3. If remotely resolvable: return dispatch_required=False with suggestions
        4. If dispatch needed: bundle with nearby open tasks

        Args:
            equipment_id: Equipment ID in v2.0 format (e.g., S002-CHILLER-B1-001).

        Returns:
            Dict with dispatch_required, reason, urgency, remote_actions,
            bundled_tasks, and recommended_specialization.
        """
        monitoring = get_remote_monitoring_service()

        # Get full diagnostic
        report = await monitoring.get_equipment_diagnostic(equipment_id, "full_diagnostic")

        # Determine site from equipment ID prefix
        site_id = self._site_id_from_equipment(equipment_id)

        # Check if remotely resolvable
        remote_actions: list[str] = []
        if not report.requires_dispatch and not report.anomalies:
            remote_actions.append("Remote diagnostic completed - all readings normal")
            return {
                "dispatch_required": False,
                "reason": "Equipment operating normally, no dispatch needed",
                "urgency": "low",
                "equipment_id": equipment_id,
                "site_id": site_id,
                "remote_actions": remote_actions,
                "bundled_tasks": [],
                "recommended_specialization": None,
                "diagnostic_summary": report.status_summary,
                "assessed_at": datetime.now().isoformat(),
            }

        # Check if a simple remote action could fix it
        if report.anomalies and not report.requires_dispatch:
            # Anomalies detected but no safety violations -- suggest remote first
            remote_suggestions = self._suggest_remote_actions(equipment_id, report.anomalies, report.recommendations)
            if remote_suggestions:
                remote_actions.extend(remote_suggestions)
                return {
                    "dispatch_required": False,
                    "reason": "Issue may be resolvable remotely -- try suggested actions first",
                    "urgency": "medium",
                    "equipment_id": equipment_id,
                    "site_id": site_id,
                    "remote_actions": remote_actions,
                    "bundled_tasks": [],
                    "recommended_specialization": None,
                    "diagnostic_summary": report.status_summary,
                    "assessed_at": datetime.now().isoformat(),
                }

        # Dispatch IS needed -- bundle tasks
        equipment_type = self._equipment_type_from_id(equipment_id)
        specialization = EQUIPMENT_SPECIALIZATION.get(equipment_type, "general")

        # Determine urgency
        urgency = "medium"
        if report.safety_status:
            overall = report.safety_status.get("overall_status", "")
            if overall == "critical":
                urgency = "critical"
            elif overall in ("alarm",):
                urgency = "high"
            elif overall == "warning":
                urgency = "medium"

        if report.requires_dispatch and urgency == "medium":
            urgency = "high"

        # Bundle nearby tasks
        bundled = await self.bundle_tasks(site_id, equipment_id)

        dispatch_reason = report.dispatch_reason or (
            f"{len(report.anomalies)} anomaly/anomalies detected requiring onsite investigation"
        )

        return {
            "dispatch_required": True,
            "reason": dispatch_reason,
            "urgency": urgency,
            "equipment_id": equipment_id,
            "site_id": site_id,
            "remote_actions": ["Remote diagnostic completed"],
            "bundled_tasks": bundled,
            "recommended_specialization": specialization,
            "diagnostic_summary": report.status_summary,
            "assessed_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Task bundling ("while you're there")
    # ------------------------------------------------------------------

    async def bundle_tasks(self, site_id: str, primary_equipment_id: str) -> list[dict[str, Any]]:
        """Find additional tasks at the same site to bundle with dispatch.

        Gathers:
        a. Open work orders for the same site
        b. Devices in warning/alarm state at the same site
        c. Overdue inspections at the same site
        Groups by floor/zone for efficient routing.

        Args:
            site_id: Site identifier (e.g., "site-002").
            primary_equipment_id: The primary equipment triggering dispatch.

        Returns:
            List of bundled tasks sorted by floor for efficient routing.
        """
        tasks: list[dict[str, Any]] = []

        # a. Open work orders for same site
        try:
            work_orders = work_order_service.get_work_orders(site_id=site_id)
            for wo in work_orders:
                if wo.status in ("open", "pending"):
                    tasks.append(
                        {
                            "task_id": wo.id,
                            "task_type": "work_order",
                            "description": wo.description,
                            "equipment_id": wo.equipment_id,
                            "priority": wo.priority,
                            "floor": self._floor_from_equipment(wo.equipment_id),
                            "estimated_minutes": TASK_DURATION_ESTIMATES.get("work_order", 60),
                            "source": "work_order",
                        }
                    )
        except Exception as e:
            logger.warning(f"Could not fetch work orders for {site_id}: {e}")

        # b. Devices in warning/alarm state at same site
        try:
            devices = await device_manager.list_devices_by_site(site_id)
            for device in devices:
                if device.id == primary_equipment_id:
                    continue  # Skip primary -- it's the reason we're dispatching

                try:
                    safety_status = await device_manager.get_device_safety_status(device.id)
                    overall = safety_status.get("overall_status", "safe")
                    if overall in ("warning", "alarm", "critical"):
                        task_type = "device_alarm" if overall in ("alarm", "critical") else "device_warning"
                        tasks.append(
                            {
                                "task_id": f"dev-{device.id}",
                                "task_type": task_type,
                                "description": f"{device.name} in {overall} state",
                                "equipment_id": device.id,
                                "priority": "high" if overall != "warning" else "medium",
                                "floor": self._floor_from_equipment(device.id),
                                "estimated_minutes": TASK_DURATION_ESTIMATES.get(task_type, 30),
                                "source": "device_status",
                                "violations": safety_status.get("violations", []),
                            }
                        )
                except Exception:
                    pass  # safety engine may not cover this device
        except Exception as e:
            logger.warning(f"Could not fetch devices for {site_id}: {e}")

        # c. Overdue inspections (from inspection schedule in hvac_zones)
        try:
            hvac_file = DATA_DIR / "hvac_zones.json"
            if hvac_file.exists():
                with open(hvac_file) as f:
                    zones = json.load(f)
                for zone in zones:
                    if zone.get("status") == "fault":
                        fcu_id = zone.get("fcu_id", "")
                        if fcu_id and fcu_id != primary_equipment_id:
                            tasks.append(
                                {
                                    "task_id": f"insp-{zone['zone_id']}",
                                    "task_type": "overdue_inspection",
                                    "description": f"Inspect {zone['zone_name']} - FCU in fault state",
                                    "equipment_id": fcu_id,
                                    "priority": "medium",
                                    "floor": zone.get("floor", "unknown"),
                                    "estimated_minutes": TASK_DURATION_ESTIMATES.get("overdue_inspection", 45),
                                    "source": "inspection_schedule",
                                }
                            )
        except Exception as e:
            logger.warning(f"Could not check inspection schedule: {e}")

        # Deduplicate by equipment_id
        seen_equipment: set = set()
        unique_tasks: list[dict[str, Any]] = []
        for task in tasks:
            eq_id = task.get("equipment_id")
            if eq_id and eq_id not in seen_equipment:
                seen_equipment.add(eq_id)
                unique_tasks.append(task)
            elif not eq_id:
                unique_tasks.append(task)

        # Sort by floor for efficient routing
        unique_tasks.sort(key=lambda t: FLOOR_ORDER.get(t.get("floor", ""), 99))

        return unique_tasks

    # ------------------------------------------------------------------
    # Technician assignment
    # ------------------------------------------------------------------

    def find_best_technician(self, site_id: str, required_specialization: str = "general") -> dict[str, Any]:
        """Find the best technician for a dispatch.

        Priority:
        1. Technician already onsite at same building with matching specialization
        2. Available technician with matching specialization
        3. Available technician with general skills
        4. Any available technician

        Args:
            site_id: Site where dispatch is needed.
            required_specialization: Required skill (hvac, electrical, etc.).

        Returns:
            Dict with technician info and assignment_reason.
        """
        if not self._technicians:
            return {
                "technician": None,
                "assignment_reason": "No technicians configured",
            }

        # 1. Onsite at same site with matching specialization
        for tech in self._technicians:
            if (
                tech["status"] == "onsite"
                and tech.get("current_site") == site_id
                and required_specialization in tech.get("specializations", [])
            ):
                return {
                    "technician": tech,
                    "assignment_reason": (f"Already onsite at {site_id} with {required_specialization} specialization"),
                }

        # 2. Available with matching specialization
        for tech in self._technicians:
            if tech["status"] == "available" and required_specialization in tech.get("specializations", []):
                return {
                    "technician": tech,
                    "assignment_reason": (f"Available with {required_specialization} specialization"),
                }

        # 3. Available with general skills
        for tech in self._technicians:
            if tech["status"] == "available" and "general" in tech.get("specializations", []):
                return {
                    "technician": tech,
                    "assignment_reason": "Available with general skills",
                }

        # 4. Any available
        for tech in self._technicians:
            if tech["status"] == "available":
                return {
                    "technician": tech,
                    "assignment_reason": "Available (no specialization match)",
                }

        return {
            "technician": None,
            "assignment_reason": "No available technicians",
        }

    # ------------------------------------------------------------------
    # Site briefing generation
    # ------------------------------------------------------------------

    async def generate_site_briefing(
        self,
        site_id: str,
        technician_id: str,
        bundled_tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a structured site briefing for a technician.

        Includes building info, current status, task list with floor routing,
        equipment details, tools/parts needed, and estimated time.

        Args:
            site_id: Site identifier.
            technician_id: Assigned technician ID.
            bundled_tasks: List of tasks to complete.

        Returns:
            Structured dict suitable for WhatsApp/PDF formatting.
        """
        monitoring = get_remote_monitoring_service()

        # Building info
        site_info = self._get_site_info(site_id)

        # Current building status
        site_status = await monitoring.get_site_status(site_id)

        # Floor-by-floor task routing
        floor_routing = self._build_floor_routing(bundled_tasks)

        # Equipment details for each task
        equipment_details = await self._get_equipment_details(bundled_tasks)

        # Tools and parts needed
        tools_needed = self._infer_tools_needed(bundled_tasks)

        # Estimated total onsite time
        total_minutes = sum(t.get("estimated_minutes", 30) for t in bundled_tasks)
        # Add 15 min for travel between floors if multiple floors
        floors_involved = {t.get("floor") for t in bundled_tasks if t.get("floor")}
        if len(floors_involved) > 1:
            total_minutes += (len(floors_involved) - 1) * 15

        # Technician info
        tech = next((t for t in self._technicians if t["id"] == technician_id), None)

        return {
            "briefing_id": str(uuid.uuid4()),
            "generated_at": datetime.now().isoformat(),
            "site_id": site_id,
            "building": site_info,
            "technician": {
                "id": technician_id,
                "name": tech["name"] if tech else technician_id,
                "phone": tech.get("phone") if tech else None,
            },
            "site_status": {
                "devices_total": site_status.get("device_count", 0),
                "devices_online": site_status.get("devices_online", 0),
                "devices_in_alarm": site_status.get("devices_in_alarm", 0),
                "devices_in_warning": site_status.get("devices_in_warning", 0),
                "overall_health": site_status.get("overall_health_score", 0),
                "active_alarms": site_status.get("active_alarms", []),
            },
            "task_count": len(bundled_tasks),
            "tasks": bundled_tasks,
            "floor_routing": floor_routing,
            "equipment_details": equipment_details,
            "tools_needed": tools_needed,
            "estimated_onsite_minutes": total_minutes,
            "estimated_onsite_time": (
                f"{total_minutes // 60}h {total_minutes % 60}m" if total_minutes >= 60 else f"{total_minutes}m"
            ),
            "safety_notes": [
                "Sign in at reception and collect building access card",
                "Check active alarms before entering plant rooms",
                "Wear PPE in plant room areas",
                "Lock out/tag out before working on electrical equipment",
            ],
            "access_instructions": site_info.get("access_instructions", ""),
        }

    # ------------------------------------------------------------------
    # Dispatch tracking
    # ------------------------------------------------------------------

    async def create_dispatch(
        self,
        site_id: str,
        equipment_id: str,
        technician_id: str | None = None,
        additional_tasks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new dispatch with bundled tasks and site briefing.

        Args:
            site_id: Target site.
            equipment_id: Primary equipment triggering dispatch.
            technician_id: Optionally pre-assign technician.
            additional_tasks: Extra tasks to include.

        Returns:
            Dict with dispatch_id, technician, briefing, tasks, estimated_time.
        """
        dispatch_id = f"DSP-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Determine specialization
        equipment_type = self._equipment_type_from_id(equipment_id)
        specialization = EQUIPMENT_SPECIALIZATION.get(equipment_type, "general")

        # Assign technician
        if technician_id:
            tech = next((t for t in self._technicians if t["id"] == technician_id), None)
            assignment_reason = "Manually assigned"
        else:
            result = self.find_best_technician(site_id, specialization)
            tech = result["technician"]
            assignment_reason = result["assignment_reason"]

        if not tech:
            return {
                "success": False,
                "error": "No suitable technician available for dispatch",
                "dispatch_id": None,
            }

        # Bundle tasks
        bundled = await self.bundle_tasks(site_id, equipment_id)

        # Add primary task at the front
        primary_task = {
            "task_id": f"primary-{equipment_id}",
            "task_type": "safety_violation" if True else "anomaly_investigation",
            "description": f"Primary: Investigate {equipment_id}",
            "equipment_id": equipment_id,
            "priority": "high",
            "floor": self._floor_from_equipment(equipment_id),
            "estimated_minutes": TASK_DURATION_ESTIMATES.get("anomaly_investigation", 30),
            "source": "dispatch_trigger",
        }
        all_tasks = [primary_task, *bundled]

        # Add any explicitly requested additional tasks
        if additional_tasks:
            for task in additional_tasks:
                all_tasks.append(
                    {
                        "task_id": task.get("task_id", f"extra-{uuid.uuid4().hex[:8]}"),
                        "task_type": task.get("task_type", "work_order"),
                        "description": task.get("description", "Additional task"),
                        "equipment_id": task.get("equipment_id"),
                        "priority": task.get("priority", "medium"),
                        "floor": self._floor_from_equipment(task.get("equipment_id")),
                        "estimated_minutes": task.get("estimated_minutes", 30),
                        "source": "manual",
                    }
                )

        # Generate briefing
        briefing = await self.generate_site_briefing(site_id, tech["id"], all_tasks)

        # Record active dispatch
        self._active_dispatches[dispatch_id] = {
            "dispatch_id": dispatch_id,
            "technician_id": tech["id"],
            "technician_name": tech["name"],
            "site_id": site_id,
            "primary_equipment_id": equipment_id,
            "tasks": all_tasks,
            "status": "assigned",
            "assignment_reason": assignment_reason,
            "created_at": datetime.now().isoformat(),
            "checked_in_at": None,
            "completed_at": None,
            "tasks_completed": [],
        }

        # Update technician status
        for t in self._technicians:
            if t["id"] == tech["id"]:
                t["status"] = "onsite"
                t["current_site"] = site_id

        total_minutes = briefing.get("estimated_onsite_minutes", 0)

        return {
            "success": True,
            "dispatch_id": dispatch_id,
            "technician": {
                "id": tech["id"],
                "name": tech["name"],
                "phone": tech.get("phone"),
                "assignment_reason": assignment_reason,
            },
            "site_id": site_id,
            "task_count": len(all_tasks),
            "bundled_tasks": all_tasks,
            "estimated_onsite_minutes": total_minutes,
            "estimated_onsite_time": briefing.get("estimated_onsite_time", ""),
            "site_briefing": briefing,
        }

    def check_in(self, dispatch_id: str, technician_id: str) -> dict[str, Any]:
        """Record technician arrival at site.

        Args:
            dispatch_id: The dispatch to check in to.
            technician_id: The technician checking in.

        Returns:
            Dict with success and updated dispatch status.
        """
        dispatch = self._active_dispatches.get(dispatch_id)
        if not dispatch:
            return {"success": False, "error": f"Dispatch {dispatch_id} not found"}

        if dispatch["technician_id"] != technician_id:
            return {
                "success": False,
                "error": "Only the assigned technician can check in",
            }

        dispatch["status"] = "in_progress"
        dispatch["checked_in_at"] = datetime.now().isoformat()

        return {
            "success": True,
            "dispatch_id": dispatch_id,
            "status": "in_progress",
            "checked_in_at": dispatch["checked_in_at"],
            "task_count": len(dispatch["tasks"]),
            "message": f"Checked in at {dispatch['site_id']}. {len(dispatch['tasks'])} tasks to complete.",
        }

    def complete_task(self, dispatch_id: str, task_id: str, result: dict[str, Any]) -> dict[str, Any]:
        """Mark a single task within a dispatch as completed.

        Args:
            dispatch_id: The active dispatch.
            task_id: The task to mark complete.
            result: Completion details (notes, findings, etc.).

        Returns:
            Dict with success and remaining task count.
        """
        dispatch = self._active_dispatches.get(dispatch_id)
        if not dispatch:
            return {"success": False, "error": f"Dispatch {dispatch_id} not found"}

        # Find the task
        task = next((t for t in dispatch["tasks"] if t["task_id"] == task_id), None)
        if not task:
            return {"success": False, "error": f"Task {task_id} not found in dispatch"}

        dispatch["tasks_completed"].append(
            {
                "task_id": task_id,
                "completed_at": datetime.now().isoformat(),
                "result": result,
            }
        )

        remaining = len(dispatch["tasks"]) - len(dispatch["tasks_completed"])
        return {
            "success": True,
            "dispatch_id": dispatch_id,
            "task_id": task_id,
            "tasks_remaining": remaining,
            "tasks_completed": len(dispatch["tasks_completed"]),
            "tasks_total": len(dispatch["tasks"]),
        }

    def complete_dispatch(
        self,
        dispatch_id: str,
        overall_notes: str = "",
    ) -> dict[str, Any]:
        """Close a dispatch and record completion metrics.

        Args:
            dispatch_id: The dispatch to complete.
            overall_notes: Technician's overall notes.

        Returns:
            Dict with dispatch summary and efficiency metrics.
        """
        dispatch = self._active_dispatches.get(dispatch_id)
        if not dispatch:
            return {"success": False, "error": f"Dispatch {dispatch_id} not found"}

        dispatch["status"] = "completed"
        dispatch["completed_at"] = datetime.now().isoformat()
        dispatch["overall_notes"] = overall_notes

        # Calculate metrics
        created = datetime.fromisoformat(dispatch["created_at"])
        completed = datetime.fromisoformat(dispatch["completed_at"])
        total_duration = (completed - created).total_seconds() / 60

        onsite_duration = 0
        if dispatch.get("checked_in_at"):
            checked_in = datetime.fromisoformat(dispatch["checked_in_at"])
            onsite_duration = (completed - checked_in).total_seconds() / 60

        tasks_completed = len(dispatch["tasks_completed"])
        tasks_total = len(dispatch["tasks"])

        # Update technician status back to available
        for tech in self._technicians:
            if tech["id"] == dispatch["technician_id"]:
                tech["status"] = "available"
                tech["current_site"] = None

        # Move to completed
        self._completed_dispatches.append(dispatch)
        del self._active_dispatches[dispatch_id]

        return {
            "success": True,
            "dispatch_id": dispatch_id,
            "status": "completed",
            "metrics": {
                "total_duration_minutes": round(total_duration, 1),
                "onsite_duration_minutes": round(onsite_duration, 1),
                "tasks_completed": tasks_completed,
                "tasks_total": tasks_total,
                "completion_rate_pct": (round(tasks_completed / tasks_total * 100, 1) if tasks_total else 0),
                "bundled_tasks_completed": max(0, tasks_completed - 1),
            },
            "overall_notes": overall_notes,
            "technician": {
                "id": dispatch["technician_id"],
                "name": dispatch["technician_name"],
            },
            "site_id": dispatch["site_id"],
        }

    def get_active_dispatches(self) -> list[dict[str, Any]]:
        """Get all active dispatches with their current status.

        Returns:
            List of active dispatch summaries.
        """
        return [
            {
                "dispatch_id": d["dispatch_id"],
                "technician_id": d["technician_id"],
                "technician_name": d["technician_name"],
                "site_id": d["site_id"],
                "primary_equipment_id": d["primary_equipment_id"],
                "status": d["status"],
                "task_count": len(d["tasks"]),
                "tasks_completed": len(d["tasks_completed"]),
                "created_at": d["created_at"],
                "checked_in_at": d.get("checked_in_at"),
            }
            for d in self._active_dispatches.values()
        ]

    def get_technicians(self) -> list[dict[str, Any]]:
        """Get all technicians with current status.

        Returns:
            List of technician dicts with availability info.
        """
        return [
            {
                "id": t["id"],
                "name": t["name"],
                "role": t["role"],
                "specializations": t["specializations"],
                "status": t["status"],
                "current_site": t.get("current_site"),
                "assigned_work_orders": len(t.get("assigned_work_orders", [])),
            }
            for t in self._technicians
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _suggest_remote_actions(
        self,
        equipment_id: str,
        anomalies: list[str],
        recommendations: list[str],
    ) -> list[str]:
        """Suggest remote actions that might resolve the issue.

        Checks for common remotely-resolvable patterns:
        - Setpoint drift -> remote setpoint adjust
        - Communication lost -> remote restart
        - Schedule conflict -> schedule override
        """
        suggestions: list[str] = []
        anomaly_text = " ".join(anomalies).lower()

        if "setpoint" in anomaly_text or "temperature" in anomaly_text:
            suggestions.append(f"Try remote setpoint adjustment on {equipment_id}")
        if "communication" in anomaly_text or "offline" in anomaly_text:
            suggestions.append(f"Attempt remote fault reset on {equipment_id}")
        if "schedule" in anomaly_text:
            suggestions.append(f"Apply schedule override on {equipment_id}")
        if not suggestions and recommendations:
            # Pass through recommendations as remote action options
            for rec in recommendations[:2]:
                if "monitor" in rec.lower() or "preventive" in rec.lower():
                    suggestions.append(rec)

        return suggestions

    def _get_site_info(self, site_id: str) -> dict[str, Any]:
        """Get building information for a site.

        Loads from buildings data or returns local defaults.
        """
        # Default for the primary registered site
        if site_id == get_primary_site_code():
            return {
                "name": "Sandton City Office Tower",
                "address": "83 Rivonia Road, Sandton, 2196",
                "floors": ["B1", "G", "L0", "L1", "L2"],
                "total_area_sqm": 4500,
                "equipment_count": 156,
                "bms_system": "Siemens Desigo CC V5.0",
                "access_instructions": (
                    "Enter via main lobby on Rivonia Road. Report to security desk "
                    "for building access card. Plant rooms require separate key from "
                    "facilities office on L1."
                ),
                "emergency_contact": "Building Manager: +27 11 555 0001",
                "parking": "Basement B1, visitor bays 12-15",
            }

        return {
            "name": f"Building {site_id}",
            "address": "Address not configured",
            "floors": ["G", "L1", "L2"],
            "total_area_sqm": 0,
            "equipment_count": 0,
            "bms_system": "Unknown",
            "access_instructions": "Contact building manager for access",
            "emergency_contact": "Not configured",
            "parking": "Not configured",
        }

    def _build_floor_routing(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group tasks by floor for efficient routing.

        Returns floor-by-floor route from lowest to highest.
        """
        floors: dict[str, list[dict[str, Any]]] = {}
        for task in tasks:
            floor = task.get("floor", "unknown")
            if floor not in floors:
                floors[floor] = []
            floors[floor].append(
                {
                    "task_id": task["task_id"],
                    "description": task["description"],
                    "equipment_id": task.get("equipment_id"),
                    "estimated_minutes": task.get("estimated_minutes", 30),
                }
            )

        # Sort by floor order
        routing = []
        for floor in sorted(floors.keys(), key=lambda f: FLOOR_ORDER.get(f, 99)):
            routing.append(
                {
                    "floor": floor,
                    "task_count": len(floors[floor]),
                    "tasks": floors[floor],
                    "estimated_minutes": sum(t.get("estimated_minutes", 30) for t in floors[floor]),
                }
            )

        return routing

    async def _get_equipment_details(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Get detailed equipment info for each task.

        Reads current device status, location, and relevant readings.
        """
        details = []
        for task in tasks:
            eq_id = task.get("equipment_id")
            if not eq_id:
                continue

            detail: dict[str, Any] = {
                "equipment_id": eq_id,
                "task_id": task["task_id"],
            }

            try:
                device = await device_manager.get_device(eq_id)
                if device:
                    detail["device_name"] = device.name
                    detail["device_type"] = (
                        device.device_type.value if hasattr(device.device_type, "value") else str(device.device_type)
                    )
                    detail["status"] = device.status.value if hasattr(device.status, "value") else str(device.status)
                    loc = getattr(device, "device_location", None)
                    if loc:
                        detail["location"] = {
                            "building": getattr(loc, "building", None),
                            "floor": getattr(loc, "floor", None),
                            "zone": getattr(loc, "zone", None),
                            "room": getattr(loc, "room", None),
                            "description": getattr(loc, "description", None),
                        }
                else:
                    detail["device_name"] = eq_id
                    detail["status"] = "unknown"
            except Exception:
                detail["device_name"] = eq_id
                detail["status"] = "unknown"

            details.append(detail)

        return details

    def _infer_tools_needed(self, tasks: list[dict[str, Any]]) -> list[str]:
        """Infer tools and parts needed from task types.

        Deduplicates across all tasks.
        """
        tools: set = set()
        for task in tasks:
            task_type = task.get("task_type", "general")
            task_tools = TOOLS_BY_TASK_TYPE.get(task_type, ["basic tool kit"])
            tools.update(task_tools)

        return sorted(tools)

    @staticmethod
    def _site_id_from_equipment(equipment_id: str) -> str:
        """Extract site_id from equipment ID.

        Equipment ID format: S002-TYPE-FLOOR-ZONE
        Maps S002 -> site-002.
        """
        if not equipment_id:
            return get_primary_site_code() or "unknown"
        parts = equipment_id.split("-")
        if parts and parts[0].startswith("S"):
            try:
                site_num = int(parts[0][1:])
                return f"site-{site_num:03d}"
            except ValueError:
                pass
        return get_primary_site_code() or "unknown"

    @staticmethod
    def _equipment_type_from_id(equipment_id: str) -> str:
        """Extract equipment type from equipment ID.

        Equipment ID format: S002-TYPE-FLOOR-ZONE
        Returns lowercase type string (e.g., "chiller", "ahu").
        """
        if not equipment_id:
            return "general"
        parts = equipment_id.split("-")
        if len(parts) >= 2:
            return parts[1].lower()
        return "general"

    @staticmethod
    def _floor_from_equipment(equipment_id: str | None) -> str:
        """Extract floor from equipment ID.

        Equipment ID format: S002-TYPE-FLOOR-ZONE
        Returns floor string (e.g., "B1", "L1", "L2").
        """
        if not equipment_id:
            return "unknown"
        parts = equipment_id.split("-")
        if len(parts) >= 3:
            return parts[2]
        return "unknown"


def get_smart_dispatch_service() -> SmartDispatchService:
    """Factory function returning the singleton SmartDispatchService."""
    return SmartDispatchService()
