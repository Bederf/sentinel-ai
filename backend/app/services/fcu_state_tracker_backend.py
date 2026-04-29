"""FCU State Tracker — swappable backend interface.

Phase 1a/1b: InMemoryBackend.
Phase 3: SupabaseBackend (drop-in replacement, same interface).

The backend abstraction allows the tracker to work in-memory for real-time
detection, then persist to Supabase for historical queries and cross-session state.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.services.fcu_state_tracker import _ZoneState

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


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


class SupabaseBackend(FCUStateTrackerBackend):
    """Supabase-backed zone state store.

    Reads existing state on init so the tracker has cross-session continuity.
    Writes every state change via upsert so patterns survive restarts.
    """

    def __init__(self, site_id: str = "S002", supabase_client: "Client | None" = None) -> None:
        self._site_id = site_id
        self._client = supabase_client
        self._cache: dict[str, _ZoneState] = {}
        self._loaded = False

    def _ensure_client(self):
        if self._client is None:
            from app.database.supabase_client import get_supabase_client

            self._client = get_supabase_client()

    def _load_all(self) -> None:
        """Load all zone states from Supabase into local cache."""
        if self._loaded:
            return
        self._ensure_client()
        try:
            result = self._client.table("fcu_zone_state").select("*").eq("site_id", self._site_id).execute()
            for row in result.data:
                zone_id = row["zone_id"]
                self._cache[zone_id] = self._row_to_state(row)
            self._loaded = True
            logger.debug(f"[FCU-SUPABASE-BACKEND] Loaded {len(self._cache)} zones from Supabase")
        except Exception as e:
            logger.warning(f"[FCU-SUPABASE-BACKEND] Failed to load state from Supabase: {e}")
            self._cache = {}
            self._loaded = True

    @staticmethod
    def _row_to_state(row: dict) -> _ZoneState:
        """Convert a DB row to a _ZoneState dataclass."""
        return _ZoneState(
            occupancy_pct=float(row["occupancy_pct"]),
            room_temp_c=float(row["room_temp_c"]) if row.get("room_temp_c") is not None else None,
            setpoint_c=float(row["setpoint_c"]) if row.get("setpoint_c") is not None else None,
            timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
            occupancy_end_time=(
                datetime.fromisoformat(row["occupancy_end_time"].replace("Z", "+00:00"))
                if row.get("occupancy_end_time") is not None
                else None
            ),
            prev_room_temp=(float(row["prev_room_temp_c"]) if row.get("prev_room_temp_c") is not None else None),
            prev_timestamp=(
                datetime.fromisoformat(row["prev_timestamp"].replace("Z", "+00:00"))
                if row.get("prev_timestamp") is not None
                else None
            ),
            fcu_inferred_running=bool(row.get("fcu_inferred_running", False)),
            occupancy_source=str(row.get("occupancy_source", "bridge")),
        )

    def get_state(self, zone_id: str) -> _ZoneState | None:
        self._load_all()
        return self._cache.get(zone_id)

    def set_state(self, zone_id: str, state: _ZoneState) -> None:
        self._cache[zone_id] = state
        self._persist(zone_id, state)

    def _persist(self, zone_id: str, state: _ZoneState) -> None:
        """Upsert a single zone state to Supabase."""
        self._ensure_client()
        try:
            payload = {
                "site_id": self._site_id,
                "zone_id": zone_id,
                "occupancy_pct": state.occupancy_pct,
                "room_temp_c": state.room_temp_c,
                "setpoint_c": state.setpoint_c,
                "timestamp": state.timestamp.isoformat(),
                "occupancy_end_time": state.occupancy_end_time.isoformat() if state.occupancy_end_time else None,
                "prev_room_temp_c": state.prev_room_temp,
                "prev_timestamp": state.prev_timestamp.isoformat() if state.prev_timestamp else None,
                "fcu_inferred_running": state.fcu_inferred_running,
                "occupancy_source": state.occupancy_source,
                "updated_at": datetime.now(tz=UTC).isoformat(),
            }
            self._client.table("fcu_zone_state").upsert(payload, on_conflict="site_id,zone_id").execute()
        except Exception as e:
            logger.warning(f"[FCU-SUPABASE-BACKEND] Failed to persist state for {zone_id}: {e}")

    def iter_zones(self):
        self._load_all()
        return self._cache.items()
