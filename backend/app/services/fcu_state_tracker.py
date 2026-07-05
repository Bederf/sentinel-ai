"""FCU State Tracker — tracks per-zone occupancy state transitions and infers FCU running state.

Phase 1a: InMemoryBackend (SupabaseBackend in Phase 3).
Provides waste opportunity detection for the AI optimizer's pre-computation layer.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from app.services.fcu_state_tracker_backend import FCUStateTrackerBackend

logger = __import__("logging").getLogger(__name__)

UTC = UTC


@dataclass
class WasteOpportunity:
    """A detected waste opportunity where equipment appears to be running unnecessarily."""

    equipment_id: str
    zone_id: str
    opportunity_type: str  # 'fcu_post_occupancy' | 'overcapacity' | 'free_cooling'
    minutes_elapsed: float
    confidence: float
    description: str  # human-readable, injected into prompt
    estimated_saving_kwh: float | None = None
    occupancy_source: str = "bridge"  # 'bridge' | 'sensor'


@dataclass
class _ZoneState:
    """Internal zone tracking state."""

    occupancy_pct: float
    room_temp_c: float | None
    setpoint_c: float | None
    timestamp: datetime
    # Occupancy transition tracking
    occupancy_end_time: datetime | None = None  # when zone last became empty
    # Temperature trend
    prev_room_temp: float | None = None
    prev_timestamp: datetime | None = None
    # FCU state (None = inference not possible from available telemetry)
    fcu_inferred_running: bool | None = None
    # Occupancy source
    occupancy_source: str = "bridge"  # 'bridge' | 'sensor'


class InMemoryBackend:
    """In-memory zone state store — used in Phase 1a and 2.

    Phase 3 replaces this with SupabaseBackend (persisted, queryable).
    """

    def __init__(self) -> None:
        self._zones: dict[str, _ZoneState] = {}

    def get_state(self, zone_id: str) -> _ZoneState | None:
        return self._zones.get(zone_id)

    def set_state(self, zone_id: str, state: _ZoneState) -> None:
        self._zones[zone_id] = state

    def iter_zones(self):
        return self._zones.items()


class FCUStateTracker:
    """Track per-zone occupancy transitions and infer FCU running state.

    Design: swappable backends. InMemoryBackend used now, SupabaseBackend in Phase 3.

    Integration point: called from ShadowModePollingService after each zone poll cycle.
    """

    # Profile-aware post-occupancy thresholds (minutes empty before flagging waste)
    POST_OCCUPANCY_THRESHOLDS: ClassVar[dict[str, int]] = {
        "cost_saving": 5,
        "comfort": 15,
        "asset_preservation": 10,
        "balanced": 10,
    }

    # Occupancy <= this % counts as "empty" — noisy live PIR/fused percentages
    # rarely settle at exactly 0.0, so both the transition detector and the
    # waste-candidate gate must share this cutoff.
    EMPTY_THRESHOLD: ClassVar[float] = 5.0

    def __init__(
        self,
        active_profile: str = "balanced",
        backend: "FCUStateTrackerBackend | None" = None,
        zone_type_resolver: "Callable[[str], str] | None" = None,
    ) -> None:
        self._active_profile = active_profile
        self._backend = backend or InMemoryBackend()
        self._zone_type_resolver = zone_type_resolver

    # ── Public API ───────────────────────────────────────────────────────────

    def record_poll(
        self,
        zone_id: str,
        occupancy_pct: float,
        room_temp_c: float | None,
        setpoint_c: float | None,
        timestamp: datetime | None = None,
        fcu_running: bool | None = None,
    ) -> None:
        """Record a zone poll result and update state.

        Called from ShadowModePollingService after each zone poll cycle.

        Tracks:
        - Occupancy state transitions (occupied → empty) → records occupancy_end_time
        - FCU running state — direct measurement (fcu_running, from fan_speed /
          valve_position readings) when the caller has one, else inferred from
          temp delta vs setpoint
        - Temperature trend for FCU inference

        Occupancy is taken from the live poll result only. No schedule/profile
        fallback is applied because that would turn missing data into fake data.
        """
        if timestamp is None:
            timestamp = datetime.now(tz=UTC)

        prev = self._backend.get_state(zone_id)
        prev_temp = prev.room_temp_c if prev else None

        effective_occupancy = occupancy_pct
        occupancy_source = "bridge"

        # Detect transition: occupied → empty
        is_empty = effective_occupancy <= self.EMPTY_THRESHOLD
        occupancy_ended = prev is not None and prev.occupancy_pct > self.EMPTY_THRESHOLD and is_empty

        # occupancy_end_time: carry forward if zone remains empty; clear if re-occupied
        # When first detecting empty state, use PREVIOUS timestamp (the zone emptied
        # between last poll and this one, ~5 minutes ago) — not current timestamp
        if occupancy_ended:
            new_occupancy_end_time = prev.timestamp if prev else timestamp
        elif is_empty:
            # Zone still empty — keep existing end_time
            new_occupancy_end_time = prev.occupancy_end_time if prev else None
        else:
            # Zone re-occupied — clear end_time
            new_occupancy_end_time = None

        new_state = _ZoneState(
            occupancy_pct=effective_occupancy,
            room_temp_c=room_temp_c,
            setpoint_c=setpoint_c,
            timestamp=timestamp,
            occupancy_end_time=new_occupancy_end_time,
            prev_room_temp=prev_temp,
            prev_timestamp=prev.timestamp if prev else None,
            # Direct measurement (fan_speed/valve_position) beats temp inference —
            # the ±2°C inter-poll sensor noise flips the delta heuristic even with
            # a setpoint present (observed on above-setpoint zones, 2026-07-04).
            fcu_inferred_running=(
                fcu_running
                if fcu_running is not None
                else self._infer_fcu_running(zone_id, room_temp_c, setpoint_c, prev)
            ),
            # Track source for prompt description
            occupancy_source=occupancy_source,
        )

        self._backend.set_state(zone_id, new_state)

    def get_waste_candidates(self) -> list[WasteOpportunity]:
        """Return zones where FCU appears to be running unnecessarily.

        Criteria for inclusion:
        - Zone occupancy <= EMPTY_THRESHOLD (same "empty" cutoff record_poll uses
          for the transition — fused/PIR percentages rarely hit exactly 0.0)
        - Zone has been empty > profile threshold (cost_saving=5min, balanced=10min, etc.)
        - FCU running (direct fan/valve measurement, or temp-trend inference)
        """
        threshold_min = self._threshold_for_profile(self._active_profile)
        opportunities: list[WasteOpportunity] = []

        for zone_id, state in self._backend.iter_zones():
            if state.occupancy_pct > self.EMPTY_THRESHOLD:
                continue  # zone still occupied

            if state.occupancy_end_time is None:
                continue  # zone has never emptied this session

            elapsed = (state.timestamp - state.occupancy_end_time).total_seconds() / 60.0

            if elapsed < threshold_min:
                continue  # not yet past threshold

            if not state.fcu_inferred_running:
                continue  # FCU not running — nothing to waste

            equip_id = self._zone_to_equipment_id(zone_id)

            if elapsed >= threshold_min * 2:
                # Far past threshold — higher confidence
                confidence = 0.95
            elif elapsed >= threshold_min * 1.5:
                confidence = 0.80
            else:
                confidence = 0.65

            opportunities.append(
                WasteOpportunity(
                    equipment_id=equip_id,
                    zone_id=zone_id,
                    opportunity_type="fcu_post_occupancy",
                    minutes_elapsed=round(elapsed, 1),
                    confidence=confidence,
                    description=(
                        f"Zone {zone_id} empty since {state.occupancy_end_time.strftime('%H:%M')}, "
                        f"FCU still running {elapsed:.0f} min (threshold: {threshold_min} min, "
                        f"profile: {self._active_profile})"
                    ),
                    occupancy_source=state.occupancy_source,
                )
            )

        return opportunities

    def get_minutes_since_zone_emptied(self, zone_id: str) -> float | None:
        """Return minutes since zone last became empty, or None if zone hasn't emptied this session."""
        state = self._backend.get_state(zone_id)
        if state is None or state.occupancy_end_time is None:
            return None
        elapsed = (state.timestamp - state.occupancy_end_time).total_seconds() / 60.0
        return round(elapsed, 1)

    def update_profile(self, active_profile: str) -> None:
        """Switch active profile — used when operator changes optimization profile."""
        self._active_profile = active_profile
        logger.info(f"[FCUTracker] Profile updated to: {active_profile}")

    def refresh_from_backend(self) -> None:
        """Re-read persisted zone state (SupabaseBackend caches after first load).

        No-op for InMemoryBackend. Read-only consumers (the AI optimizer's
        waste-candidate evaluation) must call this each cycle or they evaluate
        the state frozen at first access.
        """
        refresh = getattr(self._backend, "refresh", None)
        if callable(refresh):
            refresh()

    def get_state(self, zone_id: str) -> _ZoneState | None:
        """Expose zone state for debugging."""
        return self._backend.get_state(zone_id)

    # ── Private helpers ──────────────────────────────────────────────────────

    def _infer_fcu_running(
        self,
        zone_id: str,
        current_temp: float | None,
        setpoint: float | None,
        prev_state: _ZoneState | None,
    ) -> bool | None:
        """Infer if FCU is actively cooling based on temperature trend.

        Running if:
        - room_temp is significantly below setpoint (> 1°C under) — was recently cooling
        - OR room_temp is actively moving toward setpoint (delta < -0.5°C between polls)

        Not running if:
        - room_temp is stable and at/above setpoint
        - room_temp is rising (FCU off, passive heat gain)

        Returns None (unknown) when the available telemetry cannot support the
        inference. Without a setpoint, the only remaining signal is a single
        inter-poll temperature delta, and observed sensor noise (±2°C between
        5-minute polls) dwarfs the ±0.5°C decision threshold — the result is a
        coin flip that made reflex rules churn create/expire cycles all night.
        Consumers must treat None as "state unknown", not "not running".
        """
        if current_temp is None:
            return None

        if prev_state is None:
            return None  # no history yet — can't infer

        prev_temp = prev_state.room_temp_c
        if prev_temp is None:
            return None

        if setpoint is None:
            return None  # single-poll temp delta alone is noise, not signal

        temp_delta = current_temp - prev_temp  # negative = cooling, positive = warming
        below_setpoint = current_temp < setpoint - 1.0
        actively_cooling = temp_delta < -0.5
        return bool(below_setpoint or actively_cooling)

    def _zone_to_equipment_id(self, zone_id: str, site_id: str = "S002") -> str:
        """Map zone ID to FCU equipment code.

        Zone-201 → S002-FCU-201 (naming convention: strip Zone- prefix, pad zone number).
        """
        import re

        m = re.search(r"\d+", zone_id)
        zone_num = m.group() if m else zone_id.lstrip("Zonezone-")
        return f"{site_id.upper()}-FCU-{zone_num}"

    def _threshold_for_profile(self, profile: str) -> int:
        return self.POST_OCCUPANCY_THRESHOLDS.get(profile, 10)
