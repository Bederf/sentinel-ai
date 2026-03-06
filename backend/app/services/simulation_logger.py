"""Simulation event logger - persists lifecycle events to JSONL files."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).parent.parent / "data" / "simulation_logs"


class SimulationLogger:
    """Logs simulation events to JSONL files for offline analysis."""

    def __init__(self, log_dir: Path = LOG_DIR):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_id: Optional[str] = None
        self._events_file = None
        self._meta: Optional[Dict[str, Any]] = None
        self._event_count: int = 0

    def start_run(
        self,
        run_id: str,
        scenario: str,
        site_code: str,
        config: Dict[str, Any],
    ) -> None:
        """Initialize logging for a new simulation run."""
        self.run_id = run_id
        self._event_count = 0
        events_filename = f"{run_id}_events.jsonl"

        self._meta = {
            "run_id": run_id,
            "scenario": scenario,
            "site_code": site_code,
            "started_at": datetime.now().isoformat(),
            "ended_at": None,
            "duration_minutes": None,
            "event_count": 0,
            "events_file": events_filename,
            "config": config,
        }

        # Write initial metadata
        meta_path = self.log_dir / f"{run_id}_meta.json"
        meta_path.write_text(json.dumps(self._meta, indent=2))

        # Open events file for appending
        self._events_file = open(self.log_dir / events_filename, "a")

        logger.info(f"Simulation logger started for run {run_id}")

    def on_event(self, event) -> None:
        """Callback for lifecycle orchestrator events. Writes one JSONL line."""
        if self._events_file is None or self._events_file.closed:
            return

        record = {
            "timestamp": event.timestamp.isoformat(),
            "simulated_hour": event.simulated_hour,
            "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            "equipment_id": event.equipment_id,
            "equipment_name": event.equipment_name,
            "description": event.description,
            "details": event.details,
            "success": event.success,
        }
        self._events_file.write(json.dumps(record) + "\n")
        self._events_file.flush()
        self._event_count += 1

    def end_run(self) -> Optional[str]:
        """Finalize the run metadata and close files. Returns run_id."""
        if self._events_file and not self._events_file.closed:
            self._events_file.close()

        if self._meta is None or self.run_id is None:
            return None

        ended_at = datetime.now()
        started_at = datetime.fromisoformat(self._meta["started_at"])
        duration = (ended_at - started_at).total_seconds() / 60.0

        self._meta["ended_at"] = ended_at.isoformat()
        self._meta["duration_minutes"] = round(duration, 2)
        self._meta["event_count"] = self._event_count

        meta_path = self.log_dir / f"{self.run_id}_meta.json"
        meta_path.write_text(json.dumps(self._meta, indent=2))

        logger.info(f"Simulation logger ended run {self.run_id}: {self._event_count} events in {duration:.1f} minutes")

        run_id = self.run_id
        self.run_id = None
        self._meta = None
        self._event_count = 0
        return run_id
