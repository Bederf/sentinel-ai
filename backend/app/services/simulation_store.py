"""Simulation Store — JSON-based state for building simulation.

The building simulation is NOT SENTINEL.  It is a standalone building
that produces sensor data, meter readings, energy history, etc.
This store keeps all simulation state in JSON files — the building's
own "BMS database".

When SENTINEL turns on it reads from the building via DeviceManager,
NOT from these files directly.  SENTINEL writes to its own Supabase.

File layout:
    backend/app/data/simulation/{site_id}/
        sensor_readings.jsonl    — append-only hourly readings
        power_meters.json        — current meter state (latest values)
        energy_history.json      — daily energy aggregation {date: {hvac_kwh, lighting_kwh, ...}}
        equipment_state.json     — equipment health/status overrides
        command_writes.jsonl     — command writes issued to the simulated BMS
        task_progress.json       — simulation task progress tracking
        validations.jsonl        — power meter / cost validation audit trail
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).parent.parent / "data" / "simulation"

# JSONL file size caps (bytes).  When a file exceeds its cap the oldest
# half of its lines are discarded (truncate-in-place).
_JSONL_MAX_BYTES: dict[str, int] = {
    "sensor_readings.jsonl": 100 * 1024 * 1024,  # 100 MB
    "zone_history.jsonl": 50 * 1024 * 1024,  # 50 MB
    "solar_hourly_snapshots.jsonl": 20 * 1024 * 1024,  # 20 MB
    "solar_daily_aggregates.jsonl": 10 * 1024 * 1024,  # 10 MB
    "command_writes.jsonl": 10 * 1024 * 1024,  # 10 MB
    "validations.jsonl": 10 * 1024 * 1024,  # 10 MB
}
_DEFAULT_JSONL_MAX_BYTES = 50 * 1024 * 1024  # 50 MB default


class SimulationStore:
    """JSON-backed store for a single building's simulation state."""

    def __init__(self, site_id: str):
        self.site_id = site_id or "unknown"
        self._dir = _DATA_ROOT / self.site_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # In-memory caches (flushed to disk periodically)
        self._power_meters: dict[str, dict[str, Any]] = {}
        self._energy_history: dict[str, dict[str, float]] = {}  # date -> {hvac_kwh, lighting_kwh, ...}
        self._equipment_state: dict[str, dict[str, Any]] = {}
        self._task_progress: dict[str, Any] = {}

        # Load existing state from disk
        self._load_state()

    def _load_state(self):
        """Load persisted state from JSON files."""
        for attr, filename in [
            ("_power_meters", "power_meters.json"),
            ("_energy_history", "energy_history.json"),
            ("_equipment_state", "equipment_state.json"),
            ("_task_progress", "task_progress.json"),
        ]:
            path = self._dir / filename
            if path.exists():
                try:
                    with open(path) as f:
                        setattr(self, attr, json.load(f))
                except Exception as e:
                    logger.warning(f"[SIM-STORE] Could not load {filename}: {e}")

    def _save_json(self, filename: str, data: Any):
        """Write JSON atomically (write to tmp then rename)."""
        path = self._dir / filename
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2, default=str)
            tmp.rename(path)
        except Exception as e:
            logger.error(f"[SIM-STORE] Failed to save {filename}: {e}")
            if tmp.exists():
                tmp.unlink()

    def _append_jsonl(self, filename: str, record: dict[str, Any]):
        """Append a single JSON record to a JSONL file, rotating if over size cap."""
        path = self._dir / filename
        try:
            with open(path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.error(f"[SIM-STORE] Failed to append to {filename}: {e}")
            return

        # Check size cap and rotate if needed
        try:
            max_bytes = _JSONL_MAX_BYTES.get(filename, _DEFAULT_JSONL_MAX_BYTES)
            if path.stat().st_size > max_bytes:
                self._rotate_jsonl(path, filename)
        except Exception as e:
            logger.warning(f"[SIM-STORE] Rotation check failed for {filename}: {e}")

    def _rotate_jsonl(self, path: Path, filename: str):
        """Truncate a JSONL file by keeping only the newest half of lines."""
        try:
            with open(path) as f:
                lines = f.readlines()
            if len(lines) < 2:
                return
            keep = lines[len(lines) // 2 :]
            tmp = path.with_suffix(".rotate.tmp")
            with open(tmp, "w") as f:
                f.writelines(keep)
            tmp.rename(path)
            logger.info(f"[SIM-STORE] Rotated {filename}: {len(lines)} → {len(keep)} lines")
        except Exception as e:
            logger.error(f"[SIM-STORE] Rotation failed for {filename}: {e}")

    # ------------------------------------------------------------------
    # Sensor Readings (append-only JSONL)
    # ------------------------------------------------------------------

    def write_sensor_readings(self, readings: list[dict[str, Any]]):
        """Append sensor readings (temperature, CO2, etc.) to JSONL file."""
        for r in readings:
            self._append_jsonl("sensor_readings.jsonl", r)

    # ------------------------------------------------------------------
    # Power Meters (latest state)
    # ------------------------------------------------------------------

    def update_power_meter(self, meter_id: str, active_power_kw: float):
        """Update a power meter's current reading."""
        with self._lock:
            self._power_meters[meter_id] = {
                "active_power_kw": round(active_power_kw, 2),
                "last_poll": datetime.utcnow().isoformat() + "Z",
            }
            self._save_json("power_meters.json", self._power_meters)

    def get_power_meter(self, meter_id: str) -> dict[str, Any] | None:
        """Get current state of a power meter."""
        return self._power_meters.get(meter_id)

    def get_all_power_meters(self) -> dict[str, dict[str, Any]]:
        """Get all power meter states."""
        return dict(self._power_meters)

    # ------------------------------------------------------------------
    # Energy History (daily aggregation)
    # ------------------------------------------------------------------

    def update_energy_history(self, date_str: str, field: str, kwh: float):
        """Upsert a daily energy field (hvac_kwh, lighting_kwh, other_kwh)."""
        with self._lock:
            if date_str not in self._energy_history:
                self._energy_history[date_str] = {"site_id": self.site_id, "date": date_str}
            prev = self._energy_history[date_str].get(field, 0.0)
            self._energy_history[date_str][field] = round(prev + kwh, 2)
            self._save_json("energy_history.json", self._energy_history)

    def get_energy_history(self, date_str: str) -> dict[str, float]:
        """Get energy history for a specific date."""
        return self._energy_history.get(date_str, {})

    # ------------------------------------------------------------------
    # Equipment State (health, status overrides)
    # ------------------------------------------------------------------

    def update_equipment_state(self, equipment_code: str, updates: dict[str, Any]):
        """Update equipment state (health_score, status, etc.)."""
        with self._lock:
            if equipment_code not in self._equipment_state:
                self._equipment_state[equipment_code] = {}
            self._equipment_state[equipment_code].update(updates)
            self._save_json("equipment_state.json", self._equipment_state)

    def get_equipment_state(self, equipment_code: str) -> dict[str, Any]:
        """Get equipment state."""
        return self._equipment_state.get(equipment_code, {})

    def get_all_equipment_state(self) -> dict[str, dict[str, Any]]:
        """Get all equipment state for the building."""
        return dict(self._equipment_state)

    def get_equipment_codes(self) -> list[str]:
        """Get the known equipment codes for the building."""
        codes = set(self._equipment_state.keys())
        latest_readings = self.get_latest_sensor_readings()
        codes.update(latest_readings.keys())
        return sorted(codes)

    def get_latest_sensor_readings(self, equipment_code: str | None = None) -> dict[str, dict[str, dict[str, Any]]]:
        """Get latest reading per point from the append-only sensor JSONL file.

        Returns:
            {
                "S002-FCU-201": {
                    "room_temp": {"value": 22.1, "timestamp": "...", "site_id": "site-002"},
                    ...
                },
                ...
            }
        """
        path = self._dir / "sensor_readings.jsonl"
        latest: dict[str, dict[str, dict[str, Any]]] = {}
        if not path.exists():
            return latest

        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    code = record.get("equipment_code")
                    point_name = record.get("point_name")
                    if not code or not point_name:
                        continue
                    if equipment_code and code != equipment_code:
                        continue

                    latest.setdefault(code, {})[point_name] = {
                        "value": record.get("value"),
                        "timestamp": record.get("timestamp"),
                        "site_id": record.get("site_id", self.site_id),
                    }
        except Exception as e:
            logger.warning(f"[SIM-STORE] Failed to load latest sensor readings: {e}")

        return latest

    def write_command(self, record: dict[str, Any]):
        """Append a command write and persist it as the latest desired state."""
        equipment_code = record.get("device_id") or record.get("equipment_code")
        point_name = record.get("point_id") or record.get("point_name")
        if not equipment_code or not point_name:
            raise ValueError("Command record requires device/equipment code and point name")

        self._append_jsonl("command_writes.jsonl", record)

        current_state = self.get_equipment_state(equipment_code)
        command_overrides = dict(current_state.get("command_overrides", {}))
        command_overrides[point_name] = record.get("value")
        self.update_equipment_state(
            equipment_code,
            {
                "command_overrides": command_overrides,
                "last_command": dict(record),
            },
        )

    # ------------------------------------------------------------------
    # Simulation Task Progress
    # ------------------------------------------------------------------

    def update_task_progress(self, task_id: str, updates: dict[str, Any]):
        """Update simulation task progress."""
        with self._lock:
            if task_id not in self._task_progress:
                self._task_progress[task_id] = {}
            updates = dict(updates)
            updates.setdefault("updated_at", datetime.now().isoformat())
            self._task_progress[task_id].update(updates)
            self._save_json("task_progress.json", self._task_progress)

    def get_task_progress(self, task_id: str) -> dict[str, Any]:
        """Get simulation task progress."""
        return self._task_progress.get(task_id, {})

    def get_all_tasks(self) -> dict[str, dict[str, Any]]:
        """Get all task progress entries."""
        return dict(self._task_progress)

    def find_queued_tasks(self, simulation_type: str = "lifecycle") -> list[dict[str, Any]]:
        """Find tasks with status 'queued', oldest first (FIFO).

        Args:
            simulation_type: Filter by simulation type

        Returns:
            List of task dicts with task_id included, sorted by created_at
        """
        queued = []
        for task_id, task_data in self._task_progress.items():
            if task_data.get("status") == "queued" and task_data.get("simulation_type", "lifecycle") == simulation_type:
                entry = dict(task_data)
                entry["task_id"] = task_id
                queued.append(entry)
        # Sort by created_at (oldest first = FIFO)
        queued.sort(key=lambda t: t.get("created_at", ""))
        return queued

    # ------------------------------------------------------------------
    # Solar Snapshots (append-only JSONL)
    # ------------------------------------------------------------------

    def write_solar_snapshot(self, record: dict[str, Any]):
        """Append a solar hourly snapshot."""
        self._append_jsonl("solar_hourly_snapshots.jsonl", record)

    def write_solar_daily(self, record: dict[str, Any]):
        """Append a solar daily aggregate."""
        self._append_jsonl("solar_daily_aggregates.jsonl", record)

    # ------------------------------------------------------------------
    # Zone History (append-only JSONL)
    # ------------------------------------------------------------------

    def write_zone_history(self, records: list[dict[str, Any]]):
        """Append zone history records (temp, humidity, CO2 per zone per hour)."""
        for r in records:
            self._append_jsonl("zone_history.jsonl", r)

    # ------------------------------------------------------------------
    # Validation Audit Trail (append-only JSONL)
    # ------------------------------------------------------------------

    def write_validation(self, validation_type: str, record: dict[str, Any]):
        """Append a validation record (power meter or cost)."""
        record["validation_type"] = validation_type
        self._append_jsonl("validations.jsonl", record)

    # ------------------------------------------------------------------
    # Clean start
    # ------------------------------------------------------------------

    def reset(self):
        """Clear all simulation state for a fresh start."""
        with self._lock:
            self._power_meters = {}
            self._energy_history = {}
            self._equipment_state = {}
            self._task_progress = {}

            for f in self._dir.iterdir():
                if f.suffix in (".json", ".jsonl", ".tmp"):
                    f.unlink()

            logger.info(f"[SIM-STORE] Reset simulation state for {self.site_id}")


# ------------------------------------------------------------------
# Singleton per building
# ------------------------------------------------------------------

_stores: dict[str, SimulationStore] = {}


def get_simulation_store(site_id: str) -> SimulationStore:
    """Get or create simulation store for a building."""
    if site_id not in _stores:
        _stores[site_id] = SimulationStore(site_id)
    return _stores[site_id]
