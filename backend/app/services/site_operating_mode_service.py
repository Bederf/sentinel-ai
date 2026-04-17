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


def _normalize_site_id(site_id: str) -> str:
    """Normalize site_id to site code (e.g. site-002 → S002)."""
    normalized = site_id.strip()
    m = re.fullmatch(r"site-(\d+)", normalized, re.IGNORECASE)
    if m:
        return f"S{m.group(1).zfill(3)}"
    return normalized


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
    """Resolve cockpit operating mode from per-site building configuration.

    Supabase `sites.optimization_settings` is the primary authority (Phase 183).
    Local JSON is only a backward-compatibility fallback.
    """
    site_code = _normalize_site_id(site_id)

    # 1) Try Supabase first (primary authority since Phase 183)
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        result = client.table("sites").select("optimization_settings").eq("code", site_code).single().execute()
        if result.data:
            opt = result.data.get("optimization_settings") or {}
            explicit_mode = str(opt.get("sentinel_operating_mode") or "").strip().lower()
            if explicit_mode in {"comfort", "cost_saving", "asset_preservation"}:
                return explicit_mode  # type: ignore[return-value]
            profile = str(opt.get("active_profile") or "").strip().lower()
            if profile in _PROFILE_TO_MODE:
                return _PROFILE_TO_MODE[profile]  # type: ignore[return-value]
    except Exception:
        pass  # Fall through to local JSON fallback

    # 2) Fall back to local JSON (backward compatibility)
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
