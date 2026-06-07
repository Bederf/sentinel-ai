"""Tests for 173-03: Module-level phase overrides in effective_phase().

Verifies:
  - effective_phase() returns module override when site_modules has phase_override set
  - effective_phase() falls back to site-level phase when no module override
  - effective_phase() defaults to 'shadow' on Supabase error
  - phase_allows() works correctly for boundary cases
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# effective_phase — resolution order
# ---------------------------------------------------------------------------


class TestEffectivePhaseModuleOverride:
    """173-03: effective_phase() uses module-level phase_override when set."""

    @pytest.mark.asyncio
    async def test_effective_phase_uses_module_override(self, monkeypatch):
        """effective_phase returns module override when site_modules has one."""

        class FakeQuery:
            def __init__(self, data):
                self._data = data

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def execute(self):
                result = MagicMock()
                result.data = self._data
                return result

        class FakeSupabase:
            def table(self, name: str):
                if name == "site_modules":
                    return FakeQuery([{"phase_override": "supervised"}])
                return FakeQuery([{"onboarding_phase": "shadow"}])

        monkeypatch.setattr(
            "app.database.supabase_client.get_supabase_client",
            lambda: FakeSupabase(),
        )

        from app.models.onboarding_phase import effective_phase

        result = await effective_phase("S001", "block_booking")
        assert result == "supervised"

    @pytest.mark.asyncio
    async def test_effective_phase_falls_back_to_site(self, monkeypatch):
        """effective_phase uses site-level phase when module override is None."""

        class FakeQuery:
            def __init__(self, data):
                self._data = data

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def execute(self):
                result = MagicMock()
                result.data = self._data
                return result

        class FakeSupabase:
            def table(self, name: str):
                if name == "site_modules":
                    # phase_override is None → fall through
                    return FakeQuery([{"phase_override": None}])
                return FakeQuery([{"onboarding_phase": "advisory"}])

        monkeypatch.setattr(
            "app.database.supabase_client.get_supabase_client",
            lambda: FakeSupabase(),
        )

        from app.models.onboarding_phase import effective_phase

        result = await effective_phase("S001", "block_booking")
        assert result == "advisory"

    @pytest.mark.asyncio
    async def test_effective_phase_falls_back_to_site_no_module_type(self, monkeypatch):
        """effective_phase uses site-level phase when no module_type provided."""

        class FakeQuery:
            def __init__(self, data):
                self._data = data

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def execute(self):
                result = MagicMock()
                result.data = self._data
                return result

        class FakeSupabase:
            def table(self, name: str):
                return FakeQuery([{"onboarding_phase": "supervised"}])

        monkeypatch.setattr(
            "app.database.supabase_client.get_supabase_client",
            lambda: FakeSupabase(),
        )

        from app.models.onboarding_phase import effective_phase

        result = await effective_phase("S001")
        assert result == "supervised"

    @pytest.mark.asyncio
    async def test_effective_phase_defaults_to_shadow_on_exception(self, monkeypatch):
        """effective_phase returns 'shadow' when Supabase raises an exception."""

        def raise_error():
            raise ConnectionError("Supabase unreachable")

        monkeypatch.setattr(
            "app.database.supabase_client.get_supabase_client",
            raise_error,
        )

        from app.models.onboarding_phase import effective_phase

        result = await effective_phase("S001")
        assert result == "shadow"

    @pytest.mark.asyncio
    async def test_effective_phase_defaults_to_shadow_on_empty_site(self, monkeypatch):
        """effective_phase returns 'shadow' when site row is missing."""

        class FakeQuery:
            def __init__(self):
                pass

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def execute(self):
                result = MagicMock()
                result.data = []  # No site found
                return result

        class FakeSupabase:
            def table(self, _name: str):
                return FakeQuery()

        monkeypatch.setattr(
            "app.database.supabase_client.get_supabase_client",
            lambda: FakeSupabase(),
        )

        from app.models.onboarding_phase import effective_phase

        result = await effective_phase("S999")
        assert result == "shadow"

    @pytest.mark.asyncio
    async def test_effective_phase_module_override_empty_returns_site_phase(self, monkeypatch):
        """phase_override='' (empty string) falls through to site-level phase."""

        class FakeQuery:
            def __init__(self, data):
                self._data = data

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def execute(self):
                result = MagicMock()
                result.data = self._data
                return result

        class FakeSupabase:
            def table(self, name: str):
                if name == "site_modules":
                    # Empty string is falsy → fall through
                    return FakeQuery([{"phase_override": ""}])
                return FakeQuery([{"onboarding_phase": "auto"}])

        monkeypatch.setattr(
            "app.database.supabase_client.get_supabase_client",
            lambda: FakeSupabase(),
        )

        from app.models.onboarding_phase import effective_phase

        result = await effective_phase("S001", "occupancy_control")
        assert result == "automatic"  # effective_phase normalises legacy "auto" → "automatic"


# ---------------------------------------------------------------------------
# phase_allows — boundary tests
# ---------------------------------------------------------------------------


class TestPhaseAllowsBoundary:
    """phase_allows() gate logic for all four phases."""

    def test_shadow_blocks_emit_signal(self):
        from app.models.onboarding_phase import phase_allows

        assert phase_allows("shadow", "emit_signal") is False

    def test_advisory_allows_emit_signal(self):
        from app.models.onboarding_phase import phase_allows

        assert phase_allows("advisory", "emit_signal") is True

    def test_advisory_blocks_auto_apply(self):
        from app.models.onboarding_phase import phase_allows

        assert phase_allows("advisory", "auto_apply") is False

    def test_supervised_allows_approve_reject(self):
        from app.models.onboarding_phase import phase_allows

        assert phase_allows("supervised", "approve_reject") is True

    def test_auto_allows_all(self):
        from app.models.onboarding_phase import _FEATURE_GATES, phase_allows

        for feature in _FEATURE_GATES:
            assert phase_allows("auto", feature) is True, f"auto should allow {feature}"

    def test_none_phase_treated_as_shadow(self):
        from app.models.onboarding_phase import phase_allows

        assert phase_allows(None, "emit_signal") is False

    def test_unknown_feature_denied(self):
        from app.models.onboarding_phase import phase_allows

        assert phase_allows("auto", "nonexistent_feature") is False

    def test_unknown_phase_value_denied(self):
        from app.models.onboarding_phase import phase_allows

        assert phase_allows("production", "emit_signal") is False


# ---------------------------------------------------------------------------
# get_site_phase — delegates to effective_phase
# ---------------------------------------------------------------------------


class TestGetSitePhase:
    """get_site_phase() is a thin wrapper around effective_phase()."""

    @pytest.mark.asyncio
    async def test_get_site_phase_delegates_to_effective_phase(self, monkeypatch):
        monkeypatch.setattr(
            "app.models.onboarding_phase.effective_phase",
            AsyncMock(return_value="advisory"),
        )

        from app.models.onboarding_phase import get_site_phase

        result = await get_site_phase("S001")
        assert result == "advisory"

    @pytest.mark.asyncio
    async def test_get_site_phase_passes_module_type(self, monkeypatch):
        captured: list[tuple] = []

        async def fake_effective_phase(site_id: str, module_type=None):
            captured.append((site_id, module_type))
            return "supervised"

        monkeypatch.setattr(
            "app.models.onboarding_phase.effective_phase",
            fake_effective_phase,
        )

        from app.models.onboarding_phase import get_site_phase

        result = await get_site_phase("S001", "block_booking")
        assert result == "supervised"
        assert captured == [("S001", "block_booking")]
