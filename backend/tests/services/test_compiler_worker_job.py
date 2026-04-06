"""
Tests for CompilerWorker APScheduler job registration.

Verifies:
- Job is registered with correct id
- Interval is 5 minutes
- max_instances=1
- _run_compiler_worker_sync calls worker.poll_and_process()
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
class TestCompilerWorkerJob:
    """Tests for CompilerWorker job registration."""

    def test_add_compiler_worker_job_registers_job(self):
        """add_compiler_worker_job registers a job with id 'compiler_worker'."""
        from app.services.background_scheduler import scheduler_service

        # Remove any existing job first
        existing = scheduler_service.scheduler.get_job("compiler_worker")
        if existing:
            scheduler_service.scheduler.remove_job("compiler_worker")

        scheduler_service.add_compiler_worker_job(interval_minutes=5)

        job = scheduler_service.scheduler.get_job("compiler_worker")
        assert job is not None, "compiler_worker job was not registered"
        assert job.id == "compiler_worker"

    def test_compiler_worker_job_has_correct_interval(self):
        """Job runs at 5-minute interval by default."""
        from app.services.background_scheduler import scheduler_service

        existing = scheduler_service.scheduler.get_job("compiler_worker")
        if existing:
            scheduler_service.scheduler.remove_job("compiler_worker")

        scheduler_service.add_compiler_worker_job(interval_minutes=5)

        job = scheduler_service.scheduler.get_job("compiler_worker")
        assert job is not None
        trigger = job.trigger
        assert trigger.interval.total_seconds() == pytest.approx(5 * 60)  # 5 minutes in seconds

    def test_compiler_worker_job_has_max_instances_one(self):
        """Job has max_instances=1 to prevent overlapping runs."""
        from app.services.background_scheduler import scheduler_service

        existing = scheduler_service.scheduler.get_job("compiler_worker")
        if existing:
            scheduler_service.scheduler.remove_job("compiler_worker")

        scheduler_service.add_compiler_worker_job(interval_minutes=5)

        job = scheduler_service.scheduler.get_job("compiler_worker")
        assert job is not None
        assert job.max_instances == 1

    def test_run_compiler_worker_sync_calls_poll_and_process(self):
        """_run_compiler_worker_sync calls worker.poll_and_process() once."""
        from app.services.background_scheduler import _run_compiler_worker_sync

        mock_worker = AsyncMock()
        mock_worker.poll_and_process.return_value = 0

        with patch(
            "app.services.compiler_worker.CompilerWorker",
            return_value=mock_worker,
        ):
            _run_compiler_worker_sync()

        mock_worker.poll_and_process.assert_called_once()
