from datetime import UTC, datetime, timedelta

from app.startup.events import _task_is_recoverable


def test_task_is_recoverable_for_recent_task():
    recent = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    task = {"status": "running", "updated_at": recent}

    assert _task_is_recoverable(task) is True


def test_task_is_not_recoverable_for_stale_task():
    stale = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    task = {"status": "running", "updated_at": stale}

    assert _task_is_recoverable(task) is False
