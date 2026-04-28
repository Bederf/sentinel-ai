"""Shared occupancy profile helpers for simulator and API consumers."""

from __future__ import annotations

import random
from typing import Protocol


class _UniformRng(Protocol):
    def uniform(self, a: float, b: float) -> float: ...


def calculate_zone_occupancy(
    hour: int,
    day_of_week: int,
    is_weekend: bool,
    zone_type: str,
    is_holiday: bool = False,
    rng: _UniformRng | None = None,
) -> float:
    """Return occupancy percentage for a zone at a given time.

    The profile is shared by the lifecycle simulator and occupancy-facing APIs.
    `day_of_week` is kept in the signature for compatibility with existing
    callers and future profile tuning, even though the current heuristics only
    branch on weekday vs weekend.
    """
    random_source = rng or random

    if is_holiday:
        return 5.0 if zone_type != "utility" else 2.0

    if is_weekend:
        return 5.0 if zone_type != "utility" else 2.0

    if zone_type == "entry":
        if 7 <= hour < 9:
            return 60.0 + (hour - 7) * 15
        if 9 <= hour < 17:
            return 30.0
        if 17 <= hour < 19:
            return 50.0 + (hour - 17) * 15
        return 5.0

    if zone_type == "office":
        if 7 <= hour < 9:
            return 30.0 + (hour - 7) * 27.5
        if 9 <= hour < 12:
            return 85.0 + random_source.uniform(-5, 5)
        if 12 <= hour < 14:
            return 65.0 + random_source.uniform(-10, 10)
        if 14 <= hour < 17:
            return 75.0 + random_source.uniform(-5, 10)
        if 17 <= hour < 19:
            return max(5.0, 75.0 - (hour - 17) * 25)
        return 5.0

    # open_plan office floor zones — same schedule as 'office'
    if zone_type == "open_office":
        if 7 <= hour < 9:
            return 30.0 + (hour - 7) * 27.5
        if 9 <= hour < 12:
            return 85.0 + random_source.uniform(-5, 5)
        if 12 <= hour < 14:
            return 65.0 + random_source.uniform(-10, 10)
        if 14 <= hour < 17:
            return 75.0 + random_source.uniform(-5, 10)
        if 17 <= hour < 19:
            return max(5.0, 75.0 - (hour - 17) * 25)
        return 5.0

    if zone_type == "meeting":
        if 9 <= hour < 17:
            return 50.0 + random_source.uniform(-20, 30)
        return 0.0

    if zone_type == "common":
        if 12 <= hour < 14:
            return 80.0
        if 9 <= hour < 17:
            return 30.0
        return 5.0

    if zone_type == "utility":
        return 10.0 if 9 <= hour < 17 else 2.0

    return 20.0 if 9 <= hour < 17 else 5.0


def calculate_building_occupancy_percent(
    hour: int,
    day_of_week: int,
    is_weekend: bool,
    is_holiday: bool = False,
    rng: _UniformRng | None = None,
    seeded_variation: bool = False,
) -> float:
    """Return whole-building occupancy percent for control/status paths."""
    random_source = rng or random

    if is_holiday:
        if 8 <= hour < 18:
            base = 5.0
        elif 6 <= hour < 20:
            base = 2.0
        else:
            base = 0.0
    else:
        if hour < 6 or hour >= 22:
            base = 0.0
        elif hour < 8:
            base = 10.0
        elif hour < 11:
            base = 70.0
        elif hour < 12:
            base = 90.0
        elif hour < 13:
            base = 95.0
        elif hour < 17:
            base = 80.0
        elif hour < 18:
            base = 60.0
        elif hour < 20:
            base = 30.0
        else:
            base = 5.0

        day_factors = {5: 0.3, 6: 0.2} if is_weekend else {0: 1.0, 1: 0.95, 2: 0.9, 3: 0.88, 4: 0.8}
        base *= day_factors.get(day_of_week, 1.0)

    if seeded_variation:
        base *= random_source.uniform(0.85, 1.15)

    return max(0.0, min(100.0, base))
