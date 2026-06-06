"""
Centralized Health Threshold Service — Site-Aware

Provides a single source of truth for health and risk thresholds used across
the entire application. Reads from site_thresholds table with:
  site-specific → global fallback (__global__) → hardcoded defaults

Phase: Threshold Unification (Phase 221)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes

# Hardcoded defaults (ultimate fallback)
DEFAULT_HEALTH = {"healthy": 85, "warning": 65, "critical": 40}
DEFAULT_RISK = {"medium": 31, "high": 61, "critical": 81}


@dataclass(frozen=True)
class SiteThresholds:
    health: dict[str, int]
    risk: dict[str, int]
    site_id: str | None = None

    @staticmethod
    def defaults() -> SiteThresholds:
        return SiteThresholds(health=dict(DEFAULT_HEALTH), risk=dict(DEFAULT_RISK))


class HealthThresholdService:
    """Centralized service for health and risk thresholds — site-aware."""

    def __init__(self):
        self._cache: dict[str, tuple[SiteThresholds, datetime]] = {}

    # ── public API ──────────────────────────────────────────────────────

    def get_thresholds(
        self,
        *,
        site_id: str | None = None,
        force_refresh: bool = False,
    ) -> SiteThresholds:
        cache_key = site_id or "__global__"

        if not force_refresh and cache_key in self._cache:
            thresholds, expires = self._cache[cache_key]
            if datetime.now() < expires:
                return thresholds

        thresholds = self._load(site_id)

        self._cache[cache_key] = (thresholds, datetime.now() + timedelta(seconds=CACHE_TTL))
        return thresholds

    def get_health_status(self, health_score: float, *, site_id: str | None = None) -> str:
        thresholds = self.get_thresholds(site_id=site_id)
        h = thresholds.health
        if health_score >= h["healthy"]:
            return "healthy"
        elif health_score < h["critical"]:
            return "critical"
        else:
            return "warning"

    def get_health_color(self, health_score: float, *, site_id: str | None = None) -> str:
        status = self.get_health_status(health_score, site_id=site_id)
        return {"healthy": "green", "warning": "amber", "critical": "red"}[status]

    def get_risk_level(self, risk_score: float, *, site_id: str | None = None) -> str:
        thresholds = self.get_thresholds(site_id=site_id)
        r = thresholds.risk
        if risk_score >= r["critical"]:
            return "critical"
        elif risk_score >= r["high"]:
            return "high"
        elif risk_score >= r["medium"]:
            return "medium"
        else:
            return "low"

    def clear_cache(self, site_id: str | None = None) -> None:
        if site_id:
            self._cache.pop(site_id, None)
            self._cache.pop("__global__", None)
        else:
            self._cache.clear()
        logger.debug("Health threshold cache cleared (site_id=%s)", site_id)

    # ── internal ────────────────────────────────────────────────────────

    def _load(self, site_id: str | None) -> SiteThresholds:
        from app.database.repositories.site_threshold_repository import SiteThresholdRepository

        repo = SiteThresholdRepository()

        candidate_sites = []
        if site_id:
            candidate_sites.append(site_id)
        candidate_sites.append("__global__")

        for sid in candidate_sites:
            try:
                row = repo.get(sid)
                if row:
                    return SiteThresholds(health=row["health"], risk=row["risk"], site_id=sid)
            except Exception as e:
                logger.debug("Could not load thresholds for %s: %s", sid, e)

        return SiteThresholds.defaults()


# ── singleton ───────────────────────────────────────────────────────────────

_service_instance: HealthThresholdService | None = None


def get_health_threshold_service() -> HealthThresholdService:
    global _service_instance
    if _service_instance is None:
        _service_instance = HealthThresholdService()
    return _service_instance


# ── convenience functions ────────────────────────────────────────────────────


def get_health_thresholds(*, site_id: str | None = None, force_refresh: bool = False) -> dict[str, int]:
    return get_health_threshold_service().get_thresholds(site_id=site_id, force_refresh=force_refresh).health


def get_risk_thresholds(*, site_id: str | None = None, force_refresh: bool = False) -> dict[str, int]:
    return get_health_threshold_service().get_thresholds(site_id=site_id, force_refresh=force_refresh).risk


def get_health_status(health_score: float, *, site_id: str | None = None) -> str:
    return get_health_threshold_service().get_health_status(health_score, site_id=site_id)


def get_health_color(health_score: float, *, site_id: str | None = None) -> str:
    return get_health_threshold_service().get_health_color(health_score, site_id=site_id)


def clear_health_threshold_cache(site_id: str | None = None):
    get_health_threshold_service().clear_cache(site_id=site_id)
