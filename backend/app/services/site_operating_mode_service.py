"""Resolve the per-site SENTINEL operating mode from building configuration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

SentinelOperatingMode = Literal["comfort", "cost_saving", "asset_preservation"]

DEFAULT_SENTINEL_OPERATING_MODE: SentinelOperatingMode = "comfort"

_PROFILE_TO_MODE: dict[str, SentinelOperatingMode] = {
    "comfort": "comfort",
    "comfort_first": "comfort",
    "cost": "cost_saving",
    "cost_saving": "cost_saving",
    "sweat_assets": "asset_preservation",
    "asset_preservation": "asset_preservation",
    "asset_sweating": "asset_preservation",
}


def _candidate_site_ids(site_id: str) -> list[str]:
    normalized = site_id.strip()
    candidates = [normalized]

    site_match = re.fullmatch(r"site-(\d+)", normalized, re.IGNORECASE)
    if site_match:
        candidates.append(f"S{site_match.group(1).zfill(3)}")

    sentinel_match = re.fullmatch(r"S(\d+)", normalized, re.IGNORECASE)
    if sentinel_match:
        candidates.append(f"site-{sentinel_match.group(1).zfill(3)}")

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _config_path(site_id: str) -> Path | None:
    base = Path(__file__).resolve().parent.parent / "data" / "buildings"
    for candidate_id in _candidate_site_ids(site_id):
        path = base / candidate_id / "building.json"
        if path.exists():
            return path
    return None


def resolve_site_operating_mode(site_id: str) -> SentinelOperatingMode:
    """Resolve cockpit operating mode from per-site building configuration."""
    path = _config_path(site_id)
    if path is None:
        return DEFAULT_SENTINEL_OPERATING_MODE

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return DEFAULT_SENTINEL_OPERATING_MODE

    optimization = data.get("optimization") or {}
    explicit_mode = str(optimization.get("sentinel_operating_mode") or "").strip().lower()
    if explicit_mode in {"comfort", "cost_saving", "asset_preservation"}:
        return explicit_mode  # type: ignore[return-value]

    profile = str(optimization.get("active_profile") or "").strip().lower()
    return _PROFILE_TO_MODE.get(profile, DEFAULT_SENTINEL_OPERATING_MODE)
