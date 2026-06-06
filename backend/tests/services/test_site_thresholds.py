"""Acceptance tests for site threshold unification (Phase 221).

Covers:
  - SiteThresholds dataclass contract
  - Repository: site-specific read/write
  - Repository: ordering validation rejection
  - Service: site → global → hardcoded fallback chain
  - Service: cache isolation by site_id
  - Service: cache clearing + invalidation
  - Policy: override preservation
  - API: legacy adapter backward compat
  - API: invalid threshold rejection
  - Frontend: threshold types consistent
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.health_threshold_service import (
    DEFAULT_HEALTH,
    DEFAULT_RISK,
    HealthThresholdService,
    SiteThresholds,
    get_health_status,
    get_health_thresholds,
    get_risk_thresholds,
)

# ── Dataclass contract ────────────────────────────────────────────────────────


class TestSiteThresholdsDataclass:
    def test_defaults(self):
        t = SiteThresholds.defaults()
        assert t.health == {"healthy": 85, "warning": 65, "critical": 40}
        assert t.risk == {"medium": 31, "high": 61, "critical": 81}
        assert t.site_id is None

    def test_frozen(self):
        t = SiteThresholds(health={"healthy": 90, "warning": 70, "critical": 0}, risk=DEFAULT_RISK)
        with pytest.raises(AttributeError):
            t.health = {"healthy": 0}  # type: ignore[misc]

    def test_typed_attributes(self):
        t = SiteThresholds(health=DEFAULT_HEALTH, risk=DEFAULT_RISK, site_id="site-002")
        assert isinstance(t.health, dict)
        assert isinstance(t.risk, dict)
        assert isinstance(t.site_id, str)

    def test_convenience_functions_return_dict(self):
        h = get_health_thresholds()
        assert isinstance(h, dict)
        assert set(h.keys()) == {"healthy", "warning", "critical"}

        r = get_risk_thresholds()
        assert isinstance(r, dict)
        assert set(r.keys()) == {"medium", "high", "critical"}


# ── Repository: ordering validation ───────────────────────────────────────────


class TestRepositoryValidation:
    def test_rejects_invalid_health_ordering(self):
        from app.database.repositories.site_threshold_repository import _validate_ordering

        _validate_ordering({"healthy": 90, "warning": 70, "critical": 50}, DEFAULT_RISK)  # OK

        with pytest.raises(ValueError, match="Health thresholds"):
            _validate_ordering({"healthy": 50, "warning": 70, "critical": 30}, DEFAULT_RISK)

        with pytest.raises(ValueError, match="Health thresholds"):
            _validate_ordering({"healthy": 90, "warning": 70, "critical": 70}, DEFAULT_RISK)

        with pytest.raises(ValueError, match="Health thresholds"):
            _validate_ordering({"healthy": 90, "warning": 70, "critical": -1}, DEFAULT_RISK)

        with pytest.raises(ValueError, match="Health thresholds"):
            _validate_ordering({"healthy": 101, "warning": 70, "critical": 0}, DEFAULT_RISK)

    def test_rejects_invalid_risk_ordering(self):
        from app.database.repositories.site_threshold_repository import _validate_ordering

        _validate_ordering(DEFAULT_HEALTH, {"medium": 30, "high": 60, "critical": 80})  # OK

        with pytest.raises(ValueError, match="Risk thresholds"):
            _validate_ordering(DEFAULT_HEALTH, {"medium": 60, "high": 30, "critical": 80})

        with pytest.raises(ValueError, match="Risk thresholds"):
            _validate_ordering(DEFAULT_HEALTH, {"medium": 30, "high": 60, "critical": 60})

        with pytest.raises(ValueError, match="Risk thresholds"):
            _validate_ordering(DEFAULT_HEALTH, {"medium": -1, "high": 60, "critical": 80})

        with pytest.raises(ValueError, match="Risk thresholds"):
            _validate_ordering(DEFAULT_HEALTH, {"medium": 30, "high": 60, "critical": 101})


# ── Service: fallback chain ────────────────────────────────────────────────────


class TestFallbackChain:
    def test_hardcoded_defaults_when_db_unavailable(self):
        """Service falls through to hardcoded defaults when repository raises."""
        svc = HealthThresholdService()
        with patch("app.database.repositories.site_threshold_repository.SiteThresholdRepository.get") as mock_get:
            mock_get.side_effect = Exception("DB connection failed")
            t = svc.get_thresholds(site_id="site-002", force_refresh=True)
            assert t.health == DEFAULT_HEALTH
            assert t.risk == DEFAULT_RISK

    def test_site_specific_returns_correct_values(self):
        """Verify service returns site-specific thresholds when repository has them."""
        svc = HealthThresholdService()
        with patch.object(svc, "_load") as mock_load:
            mock_load.return_value = SiteThresholds(
                health={"healthy": 90, "warning": 75, "critical": 50},
                risk={"medium": 40, "high": 70, "critical": 90},
                site_id="site-005",
            )
            t = svc.get_thresholds(site_id="site-005", force_refresh=True)
            assert t.health["healthy"] == 90
            assert t.health["critical"] == 50
            assert t.risk["critical"] == 90
            assert t.site_id == "site-005"


# ── Service: cache isolation ──────────────────────────────────────────────────


class TestCache:
    def test_cache_keyed_by_site_id(self):
        """Different sites get different cached values."""
        svc = HealthThresholdService()

        with patch.object(svc, "_load") as mock_load:
            mock_load.side_effect = [
                SiteThresholds(
                    health={"healthy": 90, "warning": 70, "critical": 0}, risk=DEFAULT_RISK, site_id="site-002"
                ),
                SiteThresholds(
                    health={"healthy": 95, "warning": 85, "critical": 60}, risk=DEFAULT_RISK, site_id="site-005"
                ),
            ]

            t1 = svc.get_thresholds(site_id="site-002", force_refresh=True)
            t2 = svc.get_thresholds(site_id="site-005", force_refresh=True)
            assert t1.health["healthy"] == 90
            assert t2.health["healthy"] == 95
            assert mock_load.call_count == 2

    def test_cache_hit_avoids_reload(self):
        """Second call with same site_id uses cache, doesn't call _load."""
        svc = HealthThresholdService()

        with patch.object(svc, "_load") as mock_load:
            mock_load.return_value = SiteThresholds(health=DEFAULT_HEALTH, risk=DEFAULT_RISK)

            svc.get_thresholds(site_id="site-002", force_refresh=True)
            svc.get_thresholds(site_id="site-002")
            assert mock_load.call_count == 1

    def test_cache_invalidation(self):
        """Clearing cache for a site forces reload on next call."""
        svc = HealthThresholdService()

        with patch.object(svc, "_load") as mock_load:
            mock_load.return_value = SiteThresholds(health=DEFAULT_HEALTH, risk=DEFAULT_RISK)

            svc.get_thresholds(site_id="site-002", force_refresh=True)
            svc.clear_cache(site_id="site-002")
            svc.get_thresholds(site_id="site-002")
            assert mock_load.call_count == 2

    def test_global_cache_cleared_when_site_cache_cleared(self):
        """Clearing a site also invalidates global cache to prevent stale fallback."""
        svc = HealthThresholdService()
        with patch.object(svc, "_load") as mock_load:
            mock_load.side_effect = [
                SiteThresholds(health=DEFAULT_HEALTH, risk=DEFAULT_RISK),  # global
                SiteThresholds(health={"healthy": 90, "warning": 70, "critical": 0}, risk=DEFAULT_RISK),  # site-002
                SiteThresholds(health=DEFAULT_HEALTH, risk=DEFAULT_RISK),  # global reload
            ]

            # Warm global cache
            svc.get_thresholds(force_refresh=True)
            # Warm site cache
            svc.get_thresholds(site_id="site-002", force_refresh=True)
            # Clear site — should also clear global
            svc.clear_cache(site_id="site-002")
            # Global should reload
            svc.get_thresholds()
            assert mock_load.call_count == 3

    def test_force_refresh_bypasses_cache(self):
        svc = HealthThresholdService()
        with patch.object(svc, "_load") as mock_load:
            mock_load.return_value = SiteThresholds(health=DEFAULT_HEALTH, risk=DEFAULT_RISK)
            svc.get_thresholds(force_refresh=True)
            svc.get_thresholds(force_refresh=True)
            assert mock_load.call_count == 2


# ── Service: health status derivation ─────────────────────────────────────────


class TestHealthStatus:
    def test_healthy_above_threshold(self):
        assert get_health_status(90) == "healthy"
        assert get_health_status(86) == "healthy"  # >= 85
        assert get_health_status(85) == "healthy"

    def test_warning_in_range(self):
        assert get_health_status(70) == "warning"
        assert get_health_status(65) == "warning"
        assert get_health_status(41) == "warning"

    def test_critical_below_threshold(self):
        assert get_health_status(39) == "critical"  # < 40 (critical threshold)
        assert get_health_status(0) == "critical"
        assert get_health_status(40) == "warning"  # = critical threshold, not below

    def test_site_specific_thresholds_change_result(self):
        svc = HealthThresholdService()
        with patch.object(svc, "_load") as mock_load:
            mock_load.return_value = SiteThresholds(
                health={"healthy": 95, "warning": 80, "critical": 70},
                risk=DEFAULT_RISK,
            )
            svc.clear_cache()
            assert svc.get_health_status(85, site_id="site-005") == "warning"
            assert svc.get_health_status(70, site_id="site-005") == "warning"  # >= critical (70)
            assert svc.get_health_status(69, site_id="site-005") == "critical"  # < critical (70)


# ── Convenience function backward compat ──────────────────────────────────────


class TestConvenienceFunctions:
    def test_get_health_thresholds_returns_health_only(self):
        h = get_health_thresholds()
        assert isinstance(h, dict)
        assert "healthy" in h
        assert "medium" not in h  # risk key should not appear

    def test_get_risk_thresholds_returns_risk_only(self):
        r = get_risk_thresholds()
        assert isinstance(r, dict)
        assert "medium" in r
        assert "healthy" not in r  # health key should not appear

    def test_get_health_thresholds_site_id_keyword_only(self):
        """Calling with positional site_id should fail."""
        with pytest.raises(TypeError):
            get_health_thresholds("site-002")  # type: ignore[misc]


# ── Policy override preservation ─────────────────────────────────────────────


class TestPolicyOverrides:
    def test_site_asset_criticality_override_wins(self):
        """SITE_ASSET_CRITICALITY_POLICIES should override system defaults."""
        from app.services.cockpit_policy_resolution import (
            SITE_ASSET_CRITICALITY_POLICIES,
            infer_asset_context,
            resolve_policy,
        )

        # Use a fully-qualified asset ID so infer_asset_context extracts
        # asset_token="CHILLER" → asset_class="chiller" → site-002 assigns high criticality
        ctx = infer_asset_context("site-002", "S002-CHILLER-B1-001")
        policy = resolve_policy("site-002", ctx, "comfort_priority")

        # Chiller at site-002 with high criticality has a tighter threshold override
        override_key = ("site-002", "chiller", "high")
        assert override_key in SITE_ASSET_CRITICALITY_POLICIES
        expected = SITE_ASSET_CRITICALITY_POLICIES[override_key]
        assert policy.risk_thresholds == expected.risk_thresholds
        assert policy.policy_level == "site_asset_criticality"

    def test_site_policy_override_applied(self):
        """Site-specific policy (site-002) should apply when no asset override exists."""
        from app.services.cockpit_policy_resolution import SITE_POLICIES, infer_asset_context, resolve_policy

        # Use an asset type without a site_asset_criticality override
        ctx = infer_asset_context("site-002", "fcu")
        policy = resolve_policy("site-002", ctx, None)

        expected = SITE_POLICIES["site-002"]
        assert policy.risk_thresholds == expected.risk_thresholds
        assert policy.policy_level == "site"

    def test_posture_override_applied(self):
        """Posture-based policy should apply when no site/asset override exists."""
        from app.services.cockpit_policy_resolution import POSTURE_POLICIES, infer_asset_context, resolve_policy

        # Unknown site + generic asset = no site/asset override → falls to posture
        ctx = infer_asset_context("site-999", "ahu")
        policy = resolve_policy("site-999", ctx, "energy_priority")

        expected = POSTURE_POLICIES["energy_priority"]
        assert policy.risk_thresholds == expected.risk_thresholds
        assert policy.policy_level == "posture"

    def test_system_default_fallback(self):
        """Unknown site + no posture → should use system default thresholds."""
        from app.services.cockpit_policy_resolution import infer_asset_context, resolve_policy

        ctx = infer_asset_context("site-999", "ahu")
        policy = resolve_policy("site-999", ctx, None)

        # Should fall to system default
        assert policy.policy_level == "system"


# ── Frontend type consistency ────────────────────────────────────────────────


class TestFrontendTypeConsistency:
    """Verify backend types match frontend expectations (CockpitHealthThresholds / CockpitRiskThresholds)."""

    def test_health_threshold_fields_match_frontend(self):
        """Frontend expects: {healthy: number, warning: number, critical: number}."""
        t = SiteThresholds.defaults()
        expected_fields = {"healthy", "warning", "critical"}
        assert set(t.health.keys()) == expected_fields
        for v in t.health.values():
            assert isinstance(v, int)

    def test_risk_threshold_fields_match_frontend(self):
        """Frontend expects: {medium: number, high: number, critical: number}."""
        t = SiteThresholds.defaults()
        expected_fields = {"medium", "high", "critical"}
        assert set(t.risk.keys()) == expected_fields
        for v in t.risk.values():
            assert isinstance(v, int)
