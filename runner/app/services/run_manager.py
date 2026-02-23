"""RunManager — run state machine, result persistence, trace logging."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid state transitions
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running"},
    "running": {"complete", "error", "timeout"},
}


class RunManager:
    """Manages run lifecycle: creation, state transitions, result persistence."""

    def __init__(self, output_dir: str | None = None) -> None:
        self.output_dir = Path(output_dir or settings.output_dir).resolve()
        # In-memory registry of active runs (run_id -> asyncio.Task for cancellation)
        self._active_runs: dict[str, object] = {}

    async def create_run(self, case_id: str, question: str, model: str) -> str:
        """Create a new run.

        Generates run_id, creates output directory, writes initial result.json.
        Returns the run_id.
        """
        run_id = self._generate_run_id(case_id)
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Initial result with status=queued
        initial_result = {
            "status": "queued",
            "summary": "",
            "findings": [],
            "anomalies": [],
            "timeline": [],
            "recommended_actions": [],
            "confidence": 0.0,
            "needs_deeper_run": False,
            "trajectory": {
                "steps": 0,
                "files_read": 0,
                "bytes_read": 0,
                "elapsed_s": 0.0,
            },
            "case_id": case_id,
            "question": question,
            "model": model,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._write_result_atomic(run_dir, initial_result)
        logger.info("Created run %s for case %s", run_id, case_id)

        return run_id

    def update_status(self, run_id: str, status: str, result_data: dict | None = None) -> None:
        """Update run status with state machine validation.

        Raises ValueError on invalid transition.
        Raises FileNotFoundError if run does not exist.
        """
        run_dir = self.output_dir / run_id
        result_path = run_dir / "result.json"

        if not result_path.is_file():
            raise FileNotFoundError(f"Run '{run_id}' not found")

        with open(result_path) as f:
            current = json.load(f)

        current_status = current["status"]
        allowed = VALID_TRANSITIONS.get(current_status, set())

        if status not in allowed:
            raise ValueError(
                f"Invalid transition: '{current_status}' -> '{status}'. "
                f"Allowed from '{current_status}': {allowed}"
            )

        current["status"] = status
        if result_data:
            current.update(result_data)

        self._write_result_atomic(run_dir, current)
        logger.info("Run %s: %s -> %s", run_id, current_status, status)

    def get_result(self, run_id: str) -> dict | None:
        """Read result.json for a run. Returns None if not found."""
        result_path = self.output_dir / run_id / "result.json"
        if not result_path.is_file():
            return None

        with open(result_path) as f:
            return json.load(f)

    def get_trace(self, run_id: str) -> list[dict] | None:
        """Read trace.jsonl for a run. Returns list of entries or None."""
        trace_path = self.output_dir / run_id / "trace.jsonl"
        if not trace_path.is_file():
            return None

        entries: list[dict] = []
        with open(trace_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        return entries

    def append_trace(self, run_id: str, entry: dict) -> None:
        """Append a single trace entry to trace.jsonl."""
        run_dir = self.output_dir / run_id
        trace_path = run_dir / "trace.jsonl"

        if not run_dir.is_dir():
            raise FileNotFoundError(f"Run directory '{run_id}' not found")

        with open(trace_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def register_task(self, run_id: str, task: object) -> None:
        """Register an asyncio.Task for a run (for cancellation)."""
        self._active_runs[run_id] = task

    def unregister_task(self, run_id: str) -> None:
        """Remove a run from the active registry."""
        self._active_runs.pop(run_id, None)

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _generate_run_id(case_id: str) -> str:
        """Generate run_id: {case_id}_{YYYYMMDD}_{HHMMSS}_{8-char-hex}."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M%S")
        hex_suffix = uuid.uuid4().hex[:8]
        return f"{case_id}_{date_str}_{time_str}_{hex_suffix}"

    @staticmethod
    def _write_result_atomic(run_dir: Path, data: dict) -> None:
        """Write result.json atomically (write to .tmp then rename)."""
        result_path = run_dir / "result.json"
        tmp_path = run_dir / "result.json.tmp"

        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)

        os.replace(str(tmp_path), str(result_path))


# Module-level singleton
run_manager = RunManager()
