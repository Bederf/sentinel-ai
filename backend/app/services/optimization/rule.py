"""Optimization rule types for the holistic recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class RuleCondition(Protocol):
    """Evaluates telemetry snapshot and returns True if the rule should fire."""

    def __call__(self, telemetry: dict[str, dict[str, Any]]) -> bool: ...


class RuleAction(Protocol):
    """Builds a recommendation dict from telemetry snapshot when condition is met."""

    def __call__(self, telemetry: dict[str, dict[str, Any]]) -> dict[str, Any] | None: ...


@dataclass
class OptimizationRule:
    """A single optimization rule registered by a module.

    Each rule receives the **full** unified telemetry snapshot for the site
    — not just its own module's data.  This enables cross-module conditions
    (e.g. free cooling that also checks solar generation and occupancy).
    """

    module: str
    name: str
    condition: RuleCondition
    action: RuleAction
    description: str = ""
    profile: str = "balanced"
    priority: int = 5

    def evaluate(self, telemetry: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        """Run the rule against the telemetry snapshot.

        Returns a recommendation dict (compatible with the recommendations table)
        or None if the condition is not met.
        """
        if not self.condition(telemetry):
            return None
        rec = self.action(telemetry)
        if rec is None:
            return None
        rec.setdefault("module", self.module)
        rec.setdefault("rule", self.name)
        rec.setdefault("profile", self.profile)
        rec.setdefault("priority", self.priority)
        return rec
