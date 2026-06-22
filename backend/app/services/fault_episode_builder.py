"""Build fault episodes from equipment fault-event transitions.

This module is intentionally read-only and side-effect free. It turns raw
equipment_fault_events rows into episode candidates by using explicit recovery
transitions, not only a polling quiet-gap. It must not create work orders;
operators create work orders manually after reviewing the emitted signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any


NORMAL_TO_STATES = {"NORMAL", "INACTIVE", "CLEARED", "CLEAR", "OFFNORMAL_CLEARED", "RETURNED"}


@dataclass(frozen=True)
class FaultEpisode:
    equipment_code: str
    fault_family: str
    episode_number: int
    started_at: datetime
    ended_at: datetime | None
    event_count: int
    status: str
    opening_state: str | None = None
    closing_state: str | None = None
    sample_message: str | None = None


@dataclass(frozen=True)
class CyclingSignal:
    equipment_code: str
    fault_family: str
    cycle_count: int
    first_seen: datetime
    last_seen: datetime
    median_period_minutes: float
    min_period_minutes: float
    max_period_minutes: float
    has_open_episode: bool
    classification: str = "equipment_hunting_or_short_cycling"


def _event_time(event: dict[str, Any]) -> datetime:
    value = event.get("recorded_at") or event.get("created_at") or event.get("timestamp")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("fault event is missing a parseable recorded_at timestamp")


def _event_state(event: dict[str, Any], key: str) -> str | None:
    raw_payload = event.get("raw_payload") if isinstance(event.get("raw_payload"), dict) else {}
    value = event.get(key) or raw_payload.get(key)
    if value is None:
        return None
    return str(value).upper()


def _fault_family(event: dict[str, Any]) -> str:
    return str(event.get("fault_family") or event.get("alarm_code") or event.get("event_type") or "unknown")


def _is_recovery_event(event: dict[str, Any]) -> bool:
    to_state = _event_state(event, "to_state")
    if to_state in NORMAL_TO_STATES:
        return True

    event_state = _event_state(event, "event_state")
    if event_state in NORMAL_TO_STATES:
        return True

    message = str(event.get("message_text") or event.get("description") or "").lower()
    return "returned normal" in message or "returned to normal" in message


def build_fault_episodes(events: list[dict[str, Any]]) -> list[FaultEpisode]:
    """Build episodes from ordered fault/recovery transitions.

    A non-recovery event opens an episode for its equipment/fault family when no
    episode is currently open. A recovery event with ``to_state=NORMAL`` closes
    the current open episode. A rapid re-fault after a recovery opens a new
    episode, even if it happens seconds later.
    """

    sorted_events = sorted(events, key=lambda event: (_event_time(event), str(event.get("id") or "")))
    open_episodes: dict[tuple[str, str], dict[str, Any]] = {}
    episode_counts: dict[tuple[str, str], int] = {}
    completed: list[FaultEpisode] = []

    for event in sorted_events:
        equipment_code = str(event.get("equipment_code") or event.get("equipment_id") or "UNKNOWN")
        fault_family = _fault_family(event)
        key = (equipment_code, fault_family)
        recorded_at = _event_time(event)
        to_state = _event_state(event, "to_state")

        if _is_recovery_event(event):
            current = open_episodes.pop(key, None)
            if current is None:
                continue
            completed.append(
                FaultEpisode(
                    equipment_code=equipment_code,
                    fault_family=fault_family,
                    episode_number=current["episode_number"],
                    started_at=current["started_at"],
                    ended_at=recorded_at,
                    event_count=current["event_count"] + 1,
                    status="closed",
                    opening_state=current.get("opening_state"),
                    closing_state=to_state,
                    sample_message=current.get("sample_message"),
                )
            )
            continue

        current = open_episodes.get(key)
        if current is None:
            episode_number = episode_counts.get(key, 0) + 1
            episode_counts[key] = episode_number
            open_episodes[key] = {
                "episode_number": episode_number,
                "started_at": recorded_at,
                "event_count": 1,
                "opening_state": to_state,
                "sample_message": event.get("message_text") or event.get("description"),
            }
        else:
            current["event_count"] += 1

    for (equipment_code, fault_family), current in sorted(
        open_episodes.items(),
        key=lambda item: (item[0][0], item[0][1], item[1]["started_at"]),
    ):
        completed.append(
            FaultEpisode(
                equipment_code=equipment_code,
                fault_family=fault_family,
                episode_number=current["episode_number"],
                started_at=current["started_at"],
                ended_at=None,
                event_count=current["event_count"],
                status="open",
                opening_state=current.get("opening_state"),
                sample_message=current.get("sample_message"),
            )
        )

    return sorted(completed, key=lambda episode: (episode.started_at, episode.equipment_code, episode.episode_number))


def detect_cycling_signals(
    episodes: list[FaultEpisode],
    *,
    min_closed_cycles: int = 3,
    max_median_period_minutes: float = 60.0,
) -> list[CyclingSignal]:
    """Detect repeated close/re-fault patterns as hunting/short-cycling.

    This is distinct from episode closure. Episode closure answers "where does
    one fault episode end?" Cycling detection answers "is this equipment
    repeatedly entering and leaving the same fault state?"
    """

    grouped: dict[tuple[str, str], list[FaultEpisode]] = {}
    for episode in episodes:
        grouped.setdefault((episode.equipment_code, episode.fault_family), []).append(episode)

    signals: list[CyclingSignal] = []
    for (equipment_code, fault_family), group in grouped.items():
        ordered = sorted(group, key=lambda episode: episode.started_at)
        closed = [episode for episode in ordered if episode.status == "closed"]
        if len(closed) < min_closed_cycles:
            continue

        start_periods = [
            (closed[index].started_at - closed[index - 1].started_at).total_seconds() / 60.0
            for index in range(1, len(closed))
        ]
        if not start_periods:
            continue

        median_period = median(start_periods)
        if median_period > max_median_period_minutes:
            continue

        signals.append(
            CyclingSignal(
                equipment_code=equipment_code,
                fault_family=fault_family,
                cycle_count=len(closed),
                first_seen=closed[0].started_at,
                last_seen=closed[-1].ended_at or closed[-1].started_at,
                median_period_minutes=round(float(median_period), 2),
                min_period_minutes=round(float(min(start_periods)), 2),
                max_period_minutes=round(float(max(start_periods)), 2),
                has_open_episode=any(episode.status == "open" for episode in ordered),
            )
        )

    return sorted(signals, key=lambda signal: (-signal.cycle_count, signal.equipment_code))
