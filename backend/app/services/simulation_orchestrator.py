"""
Simulation Orchestrator Registry

Manages active lifecycle simulations globally, enabling:
- Concurrent simulations (multiple users)
- Task lookup by ID
- Crash recovery (find running tasks on startup)

Pattern: Factory + Registry for instance lifecycle management
"""

import logging

from app.services.health_simulation_service import get_health_simulation_service
from app.services.lifecycle_orchestrator import (
    LifecycleOrchestrator,
    create_lifecycle_orchestrator,
)

logger = logging.getLogger(__name__)

# Global registry of active simulations
_active_simulations: dict[str, LifecycleOrchestrator] = {}


def create_orchestrator(task_id: str, site_id: str | None = None) -> LifecycleOrchestrator:
    """
    Create a new orchestrator instance for a task.

    Args:
        task_id: Unique task identifier from database
        site_id: Target site identifier (resolved from registered buildings if None)

    Returns:
        New LifecycleOrchestrator instance
    """
    return create_lifecycle_orchestrator(task_id=task_id, site_id=site_id)


def register_simulation(task_id: str, orchestrator: LifecycleOrchestrator) -> None:
    """
    Register an active simulation in the global registry.
    Pauses independent health writer to prevent conflicting updates.

    Args:
        task_id: Unique task identifier
        orchestrator: LifecycleOrchestrator instance
    """
    _active_simulations[task_id] = orchestrator

    # Pause independent health writer to prevent conflicting updates
    health_sim = get_health_simulation_service()
    health_sim.defer_to_orchestrator(task_id)

    logger.info(f"Registered simulation task {task_id} (total active: {len(_active_simulations)})")


def get_simulation_by_task_id(task_id: str) -> LifecycleOrchestrator | None:
    """
    Look up a running simulation by task ID.

    Special case: task_id="default" returns the first active simulation
    (used by /status endpoint for backwards compatibility).

    Args:
        task_id: Task identifier or "default" for any active simulation

    Returns:
        LifecycleOrchestrator if found and running, None otherwise
    """
    if task_id == "default" and _active_simulations:
        return next(iter(_active_simulations.values()))
    return _active_simulations.get(task_id)


def unregister_simulation(task_id: str) -> bool:
    """
    Remove a simulation from the active registry.
    Called when simulation completes or fails.
    Resumes independent health writer if no other simulations are active.

    Args:
        task_id: Task identifier

    Returns:
        True if simulation was unregistered, False if not found
    """
    if task_id in _active_simulations:
        del _active_simulations[task_id]

        # Resume independent health writer if no other simulations active
        if not _active_simulations:
            health_sim = get_health_simulation_service()
            health_sim.resume_independent(task_id)

        logger.info(f"Unregistered simulation task {task_id} (remaining: {len(_active_simulations)})")
        return True
    return False


def get_active_simulation_count() -> int:
    """Get count of active simulations."""
    return len(_active_simulations)


def get_all_active_simulations() -> dict[str, LifecycleOrchestrator]:
    """Get copy of all active simulations (for monitoring)."""
    return _active_simulations.copy()
