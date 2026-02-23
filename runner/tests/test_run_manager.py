"""Tests for RunManager — state machine, atomic writes, trace logging."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.run_manager import RunManager


class TestRunIdFormat:
    """Test run ID generation."""

    @pytest.mark.asyncio
    async def test_create_run_id_format(self, run_manager_instance: RunManager) -> None:
        """Run ID matches {case_id}_{YYYYMMDD}_{HHMMSS}_{8-hex}."""
        run_id = await run_manager_instance.create_run(
            case_id="TEST001",
            question="What happened?",
            model="phi3:mini",
        )
        # Pattern: TEST001_YYYYMMDD_HHMMSS_xxxxxxxx
        pattern = r"^TEST001_\d{8}_\d{6}_[0-9a-f]{8}$"
        assert re.match(pattern, run_id), f"Run ID '{run_id}' does not match expected format"

    @pytest.mark.asyncio
    async def test_run_ids_are_unique(self, run_manager_instance: RunManager) -> None:
        """Multiple runs produce unique IDs."""
        ids = set()
        for _ in range(5):
            run_id = await run_manager_instance.create_run(
                case_id="TEST001",
                question="test",
                model="phi3:mini",
            )
            ids.add(run_id)
        assert len(ids) == 5


class TestStateTransitions:
    """Test state machine enforcement."""

    @pytest.mark.asyncio
    async def test_valid_transition_queued_to_running(self, run_manager_instance: RunManager) -> None:
        """queued -> running is valid."""
        run_id = await run_manager_instance.create_run("C1", "q", "phi3:mini")
        run_manager_instance.update_status(run_id, "running")
        result = run_manager_instance.get_result(run_id)
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_valid_transition_running_to_complete(self, run_manager_instance: RunManager) -> None:
        """running -> complete is valid."""
        run_id = await run_manager_instance.create_run("C1", "q", "phi3:mini")
        run_manager_instance.update_status(run_id, "running")
        run_manager_instance.update_status(run_id, "complete", {"summary": "Done"})
        result = run_manager_instance.get_result(run_id)
        assert result["status"] == "complete"
        assert result["summary"] == "Done"

    @pytest.mark.asyncio
    async def test_invalid_transition_queued_to_complete(self, run_manager_instance: RunManager) -> None:
        """queued -> complete is invalid (must go through running)."""
        run_id = await run_manager_instance.create_run("C1", "q", "phi3:mini")
        with pytest.raises(ValueError, match="Invalid transition"):
            run_manager_instance.update_status(run_id, "complete")

    @pytest.mark.asyncio
    async def test_invalid_transition_running_to_queued(self, run_manager_instance: RunManager) -> None:
        """running -> queued is invalid (no going back)."""
        run_id = await run_manager_instance.create_run("C1", "q", "phi3:mini")
        run_manager_instance.update_status(run_id, "running")
        with pytest.raises(ValueError, match="Invalid transition"):
            run_manager_instance.update_status(run_id, "queued")


class TestAtomicWrite:
    """Test atomic result persistence."""

    @pytest.mark.asyncio
    async def test_result_json_exists_after_create(self, run_manager_instance: RunManager) -> None:
        """result.json is created immediately on run creation."""
        run_id = await run_manager_instance.create_run("C1", "q", "phi3:mini")
        result_path = run_manager_instance.output_dir / run_id / "result.json"
        assert result_path.is_file()

    @pytest.mark.asyncio
    async def test_no_tmp_file_left(self, run_manager_instance: RunManager) -> None:
        """Atomic write leaves no .tmp file behind."""
        run_id = await run_manager_instance.create_run("C1", "q", "phi3:mini")
        run_manager_instance.update_status(run_id, "running")
        tmp_path = run_manager_instance.output_dir / run_id / "result.json.tmp"
        assert not tmp_path.exists()


class TestTraceLog:
    """Test trace.jsonl append and read."""

    @pytest.mark.asyncio
    async def test_trace_append_and_read(self, run_manager_instance: RunManager) -> None:
        """Entries accumulate in trace.jsonl."""
        run_id = await run_manager_instance.create_run("C1", "q", "phi3:mini")

        run_manager_instance.append_trace(run_id, {
            "timestamp": "2026-02-23T10:00:00Z",
            "event_type": "start",
            "details": {"msg": "Starting analysis"},
        })
        run_manager_instance.append_trace(run_id, {
            "timestamp": "2026-02-23T10:00:01Z",
            "event_type": "file_read",
            "details": {"file": "events.json"},
        })

        trace = run_manager_instance.get_trace(run_id)
        assert trace is not None
        assert len(trace) == 2
        assert trace[0]["event_type"] == "start"
        assert trace[1]["event_type"] == "file_read"

    @pytest.mark.asyncio
    async def test_trace_returns_none_when_no_trace(self, run_manager_instance: RunManager) -> None:
        """get_trace returns None if trace.jsonl does not exist."""
        run_id = await run_manager_instance.create_run("C1", "q", "phi3:mini")
        trace = run_manager_instance.get_trace(run_id)
        assert trace is None

    @pytest.mark.asyncio
    async def test_get_result_nonexistent(self, run_manager_instance: RunManager) -> None:
        """get_result returns None for a nonexistent run."""
        result = run_manager_instance.get_result("DOES_NOT_EXIST")
        assert result is None
