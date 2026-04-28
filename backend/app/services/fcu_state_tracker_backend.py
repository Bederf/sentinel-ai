"""FCU State Tracker — swappable backend interface.

Phase 1a/1b: InMemoryBackend.
Phase 3: SupabaseBackend (drop-in replacement, same interface).

The backend abstraction allows the tracker to work in-memory for real-time
detection, then persist to Supabase for historical queries and cross-session state.
"""

from app.services.fcu_state_tracker import _ZoneState


class FCUStateTrackerBackend:
    """Abstract backend for FCU state storage.

    Implement this to add persistence (Supabase in Phase 3).
    """

    def get_state(self, zone_id: str) -> _ZoneState | None:
        raise NotImplementedError

    def set_state(self, zone_id: str, state: _ZoneState) -> None:
        raise NotImplementedError

    def iter_zones(self):
        raise NotImplementedError
