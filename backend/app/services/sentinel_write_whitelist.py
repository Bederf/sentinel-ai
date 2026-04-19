"""SENTINEL Write Whitelist — Point-level gate for autonomous device writes.

Phase 185 Wave 2: Blocks writes to equipment/points that are not explicitly
approved for autonomous control. Every write route (Tier 2 human-approved,
Tier 3 auto-execute) passes through this whitelist before reaching the device.

Whitelist is stored in app/data/policies/sentinel_write_whitelist.json
and can optionally be overridden per-site in Supabase.

BACnet priority is determined by the SentinelTool classification passed to
execute_command() — not stored in the whitelist. The whitelist only gates
whether a write is allowed at all.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_WHITELIST_FILE = DATA_DIR / "policies" / "sentinel_write_whitelist.json"


@dataclass
class WhitelistResult:
    allowed: bool
    equipment_type: str
    point_name: str
    reason: str
    whitelist_version: str = ""


def _extract_equipment_type(equipment_id: str) -> str:
    """Extract equipment type from SENTINEL equipment ID.

    SENTINEL naming convention: {site}-{type}-{zone?}-{seq?}
    Examples:
        S002-CHILLER-B1-001  → CHILLER
        S002-AHU-MX-001      → AHU
        S002-VAV-L1-001      → VAV
        S002-FCU-101         → FCU
        S002-DALI-L1-001     → DALI
        S002-BESS-001        → BESS
        S002-GEN-001         → GEN
    """
    parts = equipment_id.split("-")
    if len(parts) >= 2:
        eq_type = parts[1].upper()
        # Strip any numeric suffix for multi-character types
        eq_type = re.sub(r"\d+$", "", eq_type)
        return eq_type
    return equipment_id.upper()


class SentinelWriteWhitelist:
    """Point-level whitelist for SENTINEL autonomous writes.

    Loads from JSON file (app/data/policies/sentinel_write_whitelist.json).
    Can be extended to Supabase-backed per-site rules in future.

    Usage:
        whitelist = SentinelWriteWhitelist()
        result = whitelist.can_write("S002-CHILLER-B1-001", "supply_water_temperature_setpoint")
        if not result.allowed:
            raise PermissionError(f"Write to {result.equipment_type}.{result.point_name} not whitelisted")
    """

    def __init__(self, whitelist_file: Path | None = None):
        self._whitelist_file = whitelist_file or DEFAULT_WHITELIST_FILE
        self._rules: dict[str, dict[str, Any]] = {}  # equipment_type -> {points: set, wildcard_points: set}
        self._catch_all_points: frozenset[str] = frozenset()
        self._version: str = "unknown"
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load whitelist from JSON file."""
        if self._loaded:
            return

        if not self._whitelist_file.exists():
            logger.warning(
                f"SENTINEL write whitelist not found at {self._whitelist_file}. "
                "All writes will be BLOCKED. Create the file to enable autonomous control."
            )
            self._loaded = True
            return

        import json

        try:
            with open(self._whitelist_file) as f:
                data = json.load(f)
            self._version = data.get("version", "1")
            rules = data.get("rules", [])

            for rule in rules:
                eq_type = rule.get("equipment_type", "").upper()
                if not eq_type:
                    continue
                points = rule.get("points", [])
                self._rules[eq_type] = {
                    "points": frozenset(p.lower() for p in points),
                }

            self._catch_all_points = frozenset(p.lower() for p in data.get("catch_all_points", []))

            logger.info(f"SENTINEL write whitelist loaded: {len(self._rules)} equipment types, version={self._version}")
        except Exception as e:
            logger.error(f"Failed to load write whitelist: {e}. All writes will be BLOCKED.")
            self._rules = {}

        self._loaded = True

    def reload(self) -> None:
        """Force reload from file."""
        self._loaded = False
        self._rules = {}
        self.load()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def can_write(self, equipment_id: str, point_name: str) -> WhitelistResult:
        """Check if a write to equipment_id.point_name is whitelisted.

        Equipment type is extracted from equipment_id using SENTINEL naming.
        Point name is matched literally (case-insensitive).

        Returns WhitelistResult with:
            allowed: True if write is permitted
            equipment_type: extracted type
            point_name: the requested point
            reason: human-readable reason for denial or 'ok'
            whitelist_version: version string from whitelist file
        """
        self.load()

        eq_type = _extract_equipment_type(equipment_id)
        point_lower = point_name.lower()

        # If no rules loaded, block everything
        if not self._rules:
            return WhitelistResult(
                allowed=False,
                equipment_type=eq_type,
                point_name=point_name,
                reason="Write whitelist not loaded or not found — all writes blocked",
                whitelist_version=self._version,
            )

        rule = self._rules.get(eq_type)
        if rule is None:
            return WhitelistResult(
                allowed=False,
                equipment_type=eq_type,
                point_name=point_name,
                reason=f"Equipment type '{eq_type}' is not in the write whitelist",
                whitelist_version=self._version,
            )

        if point_lower not in rule["points"] and point_lower not in self._catch_all_points:
            return WhitelistResult(
                allowed=False,
                equipment_type=eq_type,
                point_name=point_name,
                reason=f"Point '{point_name}' is not whitelisted for {eq_type} writes",
                whitelist_version=self._version,
            )

        return WhitelistResult(
            allowed=True,
            equipment_type=eq_type,
            point_name=point_name,
            reason="ok",
            whitelist_version=self._version,
        )

    @property
    def version(self) -> str:
        self.load()
        return self._version


# Module-level singleton
_whitelist: SentinelWriteWhitelist | None = None


def get_sentinel_write_whitelist() -> SentinelWriteWhitelist:
    global _whitelist
    if _whitelist is None:
        _whitelist = SentinelWriteWhitelist()
    return _whitelist
