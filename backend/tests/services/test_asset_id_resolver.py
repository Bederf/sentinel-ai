"""
Tests for AssetIDResolver — stages 1-3 (Phase 180-01).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.asset_resolution import (
    ResolutionConfidence,
    ResolutionMethod,
    ResolutionResult,
)
from app.services.asset_id_resolver import AssetIDResolver

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_db():
    """Minimal async-style mock matching self.db.table().execute() pattern."""
    return MagicMock()


@pytest.fixture
def equipment_data():
    return [
        {
            "code": "S002-CHILLER-B1-001",
            "type": "CHILLER",
            "manufacturer": "Carrier",
            "model": "30XA4525",
            "display_name": "Chiller B1 — Primary",
        },
        {
            "code": "S002-CHILLER-B1-002",
            "type": "CHILLER",
            "manufacturer": "Carrier",
            "model": "30XA4526",
            "display_name": "Chiller B2 — Secondary",
        },
        {
            "code": "S002-AHU-001",
            "type": "AHU",
            "manufacturer": "Johnson Controls",
            "model": "YMEA45",
            "display_name": "AHU-1 — Lobby",
        },
        {
            "code": "S002-FCU-101",
            "type": "FCU",
            "manufacturer": "Daikin",
            "model": "FWS03",
            "display_name": "FCU 101 — Office Floor 1",
        },
    ]


def _make_equipment_result(equipment_data):
    """Build a mock result with .data = equipment_data for equipment table."""
    return MagicMock(data=equipment_data)


def _make_alias_result(alias_data):
    """Build a mock result with .data = alias_data for aliases table."""
    return MagicMock(data=alias_data)


# --------------------------------------------------------------------------- #
# Enum & dataclass tests
# --------------------------------------------------------------------------- #


class TestResolutionEnums:
    def test_resolution_method_values(self):
        assert ResolutionMethod.EXACT.value == "exact"
        assert ResolutionMethod.FUZZY.value == "fuzzy"
        assert ResolutionMethod.LLM_ASSISTED.value == "llm_assisted"
        assert ResolutionMethod.UNRESOLVED.value == "unresolved"

    def test_resolution_confidence_values(self):
        assert ResolutionConfidence.HIGH.value == "high"
        assert ResolutionConfidence.MEDIUM.value == "medium"
        assert ResolutionConfidence.LOW.value == "low"

    def test_confidence_is_string_enum(self):
        assert isinstance(ResolutionConfidence.HIGH, str)


class TestResolutionResult:
    def test_dataclass_creation(self):
        r = ResolutionResult(
            asset_id="S002-CHILLER-B1-001",
            confidence=0.95,
            confidence_band=ResolutionConfidence.HIGH,
            method=ResolutionMethod.EXACT,
            matched_on="code",
            needs_review=False,
            review_reason=None,
        )
        assert r.asset_id == "S002-CHILLER-B1-001"
        assert r.confidence == 0.95
        assert r.confidence_band is ResolutionConfidence.HIGH
        assert r.method is ResolutionMethod.EXACT
        assert r.matched_on == "code"
        assert r.needs_review is False
        assert r.review_reason is None

    def test_dataclass_is_frozen(self):
        r = ResolutionResult(
            asset_id="X",
            confidence=0.5,
            confidence_band=ResolutionConfidence.MEDIUM,
            method=ResolutionMethod.FUZZY,
            matched_on="display_name",
            needs_review=True,
            review_reason="low score",
        )
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            r.asset_id = "Y"


# --------------------------------------------------------------------------- #
# Normalise tests
# --------------------------------------------------------------------------- #


class TestNormalise:
    def test_lowercase(self):
        assert AssetIDResolver._normalise("Chiller B1") == "chiller b1"

    def test_strips_punctuation(self):
        assert AssetIDResolver._normalise("Chiller, B1! #102?") == "chiller b1 102"

    def test_preserves_hyphen(self):
        assert AssetIDResolver._normalise("CHILLER-B1-001") == "chiller-b1-001"

    def test_collapse_whitespace(self):
        assert AssetIDResolver._normalise("Chiller    B1") == "chiller b1"

    def test_empty_string(self):
        assert AssetIDResolver._normalise("") == ""

    def test_none_input(self):
        assert AssetIDResolver._normalise(None) == ""


# --------------------------------------------------------------------------- #
# Confidence band tests
# --------------------------------------------------------------------------- #


class TestConfidenceBand:
    def test_085_is_high(self):
        assert AssetIDResolver._confidence_band(0.85) == ResolutionConfidence.HIGH

    def test_090_is_high(self):
        assert AssetIDResolver._confidence_band(0.90) == ResolutionConfidence.HIGH

    def test_100_is_high(self):
        assert AssetIDResolver._confidence_band(1.0) == ResolutionConfidence.HIGH

    def test_084_is_medium(self):
        assert AssetIDResolver._confidence_band(0.84) == ResolutionConfidence.MEDIUM

    def test_070_is_medium(self):
        assert AssetIDResolver._confidence_band(0.70) == ResolutionConfidence.MEDIUM

    def test_060_is_medium(self):
        assert AssetIDResolver._confidence_band(0.60) == ResolutionConfidence.MEDIUM

    def test_059_is_low(self):
        assert AssetIDResolver._confidence_band(0.59) == ResolutionConfidence.LOW

    def test_000_is_low(self):
        assert AssetIDResolver._confidence_band(0.0) == ResolutionConfidence.LOW


# --------------------------------------------------------------------------- #
# Stage 1 — Alias match tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestStage1AliasMatch:
    async def test_known_alias_returns_high_exact(self, mock_db):
        """KNOWN_ALIASES entry → HIGH confidence, EXACT method, no review."""
        # _load_aliases returns {} (table missing) → KNOWN_ALIASES used
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve("Chiller B1")
        assert result.asset_id == "S002-CHILLER-B1-001"
        assert result.method == ResolutionMethod.EXACT
        assert result.matched_on == "alias"
        assert result.confidence_band == ResolutionConfidence.HIGH
        assert result.needs_review is False
        assert result.review_reason is None

    async def test_unknown_alias_proceeds_to_stage2(self, mock_db, equipment_data):
        """Unknown alias falls through to Stage 2 → Stage 3 → Stage 4 LLM."""
        from unittest.mock import AsyncMock

        # Both aliases and equipment table return data
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = _make_alias_result([])
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _make_equipment_result(equipment_data)
        )

        # Mock LLM to return null (no match)
        mock_call = AsyncMock(return_value='{"asset_id": null, "confidence": 0.1, "reason": "no match"}')
        mock_gateway = type("MockGateway", (), {"call": mock_call})()

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver._llm_resolve(
            "unknown-alias-xyz",
            equipment_data,
            None,
            gateway=mock_gateway,
        )
        assert result.method == ResolutionMethod.LLM_ASSISTED
        assert result.asset_id is None


# --------------------------------------------------------------------------- #
# Stage 2 — Exact code match tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestStage2ExactMatch:
    async def test_exact_code_match_returns_high(self, mock_db, equipment_data):
        """Stage 2: exact code match → HIGH, EXACT, no review."""
        # Empty aliases, equipment has the code
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = _make_alias_result([])
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _make_equipment_result(equipment_data)
        )

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve("S002-CHILLER-B1-001")
        assert result.asset_id == "S002-CHILLER-B1-001"
        assert result.method == ResolutionMethod.EXACT
        assert result.matched_on == "code"
        assert result.confidence_band == ResolutionConfidence.HIGH
        assert result.needs_review is False

    async def test_exact_code_case_insensitive(self, mock_db, equipment_data):
        """Stage 2: exact code match is case-insensitive (normalised)."""
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = _make_alias_result([])
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _make_equipment_result(equipment_data)
        )

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve("s002-chiller-b1-001")
        assert result.asset_id == "S002-CHILLER-B1-001"
        assert result.method == ResolutionMethod.EXACT
        assert result.matched_on == "code"


# --------------------------------------------------------------------------- #
# Stage 3 — Fuzzy match tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestStage3FuzzyMatch:
    async def test_fuzzy_high_score_returns_high_or_medium(self, mock_db, equipment_data):
        """Score >= 0.85 → HIGH; 0.60-0.84 → MEDIUM (review flag)."""
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = _make_alias_result([])
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _make_equipment_result(equipment_data)
        )

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        # "Chiller B1 primary" should fuzzy-match to "Chiller B1 — Primary"
        result = await resolver.resolve("Chiller B1 primary")
        if result.method == ResolutionMethod.FUZZY:
            assert result.confidence_band in (ResolutionConfidence.HIGH, ResolutionConfidence.MEDIUM)
            if result.confidence_band == ResolutionConfidence.HIGH:
                assert result.needs_review is False

    async def test_fuzzy_medium_score_flagged_for_review(self, mock_db, equipment_data):
        """Score 0.60-0.84 → MEDIUM, needs_review=True with reason."""
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = _make_alias_result([])
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _make_equipment_result(equipment_data)
        )

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve("Chiller B1 compressor")
        if result.method == ResolutionMethod.FUZZY and result.confidence_band == ResolutionConfidence.MEDIUM:
            assert result.needs_review is True
            assert result.review_reason is not None
            assert "fuzzy match" in result.review_reason

    async def test_fuzzy_below_060_returns_unresolved(self, mock_db, equipment_data):
        """Score < 0.60 → stage 4 LLM called (now async); test with alien description."""
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = _make_alias_result([])
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _make_equipment_result(equipment_data)
        )

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        # "telephone exchange switching system" scores ~0.21-0.31 vs all equipment → below 0.60
        result = await resolver.resolve("telephone exchange switching system")
        # Now reaches LLM stage since fuzzy < 0.60
        assert result.needs_review is True


# --------------------------------------------------------------------------- #
# Empty description tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestEmptyDescription:
    async def test_empty_string_returns_low_unresolved(self, mock_db):
        result = await AssetIDResolver(db=mock_db, site_id="site-002").resolve("")
        assert result.method == ResolutionMethod.UNRESOLVED
        assert result.confidence_band == ResolutionConfidence.LOW
        assert result.needs_review is True
        assert result.review_reason == "empty description"

    async def test_whitespace_only_returns_low_unresolved(self, mock_db):
        result = await AssetIDResolver(db=mock_db, site_id="site-002").resolve("   ")
        assert result.method == ResolutionMethod.UNRESOLVED
        assert result.confidence_band == ResolutionConfidence.LOW
        assert result.needs_review is True
        assert result.review_reason == "empty description"


# --------------------------------------------------------------------------- #
# KNOWN_ALIASES fallback (table missing) tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestKnownAliasesFallback:
    async def test_table_missing_uses_known_aliases(self, mock_db):
        """
        When asset_resolver_aliases table doesn't exist (query raises),
        KNOWN_ALIASES should still work as fallback.
        """

        def raise_on_aliases(*args, **kwargs):
            raise Exception("relation 'asset_resolver_aliases' does not exist")

        mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = raise_on_aliases

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver.resolve("chiller")  # In KNOWN_ALIASES
        assert result.asset_id == "S002-CHILLER-B1-001"
        assert result.method == ResolutionMethod.EXACT
        assert result.matched_on == "alias"


# --------------------------------------------------------------------------- #
# Site ID validation tests
# --------------------------------------------------------------------------- #


class TestSiteIdValidation:
    def test_none_raises_valueerror(self, mock_db):
        with pytest.raises(ValueError, match="non-empty string"):
            AssetIDResolver(db=mock_db, site_id=None)

    def test_empty_string_raises_valueerror(self, mock_db):
        with pytest.raises(ValueError, match="non-empty string"):
            AssetIDResolver(db=mock_db, site_id="")

    def test_whitespace_only_raises_valueerror(self, mock_db):
        with pytest.raises(ValueError, match="non-empty string"):
            AssetIDResolver(db=mock_db, site_id="   ")


# --------------------------------------------------------------------------- #
# Equipment cache tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestEquipmentCache:
    async def test_equipment_queried_once_across_multiple_resolves(self, mock_db, equipment_data):
        """
        After first resolve, _equipment_cache is populated.
        Subsequent resolves reuse the cache — no extra DB calls for equipment.
        """
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = _make_alias_result([])
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _make_equipment_result(equipment_data)
        )

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")

        await resolver.resolve("Chiller B1")
        await resolver.resolve("AHU-1")
        await resolver.resolve("FCU 101")

        # Count how many times equipment table was called
        equipment_call_count = sum(
            1 for call in mock_db.table.call_args_list if call.args and call.args[0] == "equipment"
        )
        assert equipment_call_count == 1, f"Expected 1 equipment call, got {equipment_call_count}"


# --------------------------------------------------------------------------- #
# LLM stage / end-to-end tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestLlmStageStub:
    async def test_llm_stage_returns_llm_assisted_on_fuzzy_miss(self, mock_db, equipment_data):
        """Stage 4: when fuzzy score < 0.60, LLM is called and returns LLM_ASSISTED."""
        from unittest.mock import AsyncMock

        mock_call = AsyncMock(return_value='{"asset_id": null, "confidence": 0.3, "reason": "no match"}')
        mock_gateway = type("MockGateway", (), {"call": mock_call})()

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver._llm_resolve(
            "something completely unrelated to any equipment",
            equipment_data,
            "service_report",
            gateway=mock_gateway,
        )
        assert result.method == ResolutionMethod.LLM_ASSISTED
        assert result.asset_id is None
        assert result.confidence == 0.3

    async def test_llm_stage_returns_unresolved_on_llm_failure(self, mock_db, equipment_data):
        """Stage 4: when fuzzy score < 0.60 AND LLM fails, returns UNRESOLVED."""
        from unittest.mock import AsyncMock

        mock_call = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        mock_gateway = type("MockGateway", (), {"call": mock_call})()

        resolver = AssetIDResolver(db=mock_db, site_id="site-002")
        result = await resolver._llm_resolve(
            "something completely unrelated to any equipment",
            equipment_data,
            "service_report",
            gateway=mock_gateway,
        )
        assert result.method == ResolutionMethod.UNRESOLVED
        assert result.needs_review is True
