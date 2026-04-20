"""Tests for BMS-aware query expansion service."""

import pytest

from app.services.query_expansion_service import (
    EQUIPMENT_CODE_RE,
    MAX_VARIANTS,
    QueryExpansionService,
    get_query_expansion_service,
)


@pytest.fixture
def expander():
    """Create a fresh QueryExpansionService instance."""
    return QueryExpansionService()


class TestEquipmentCodeRegex:
    """Test the equipment code extraction regex."""

    def test_extracts_chiller_code(self):
        matches = EQUIPMENT_CODE_RE.findall("S002-CHILLER-B1-001 is faulty")
        assert "CHILLER" in matches

    def test_extracts_vav_code(self):
        matches = EQUIPMENT_CODE_RE.findall("Check S002-VAV-101")
        assert "VAV" in matches

    def test_extracts_multiple_codes(self):
        matches = EQUIPMENT_CODE_RE.findall("S002-AHU-B1-001 and S002-FCU-201")
        assert "AHU" in matches
        assert "FCU" in matches

    def test_no_match_on_plain_text(self):
        matches = EQUIPMENT_CODE_RE.findall("how does health scoring work?")
        assert len(matches) == 0


class TestQueryExpansion:
    """Test the full expansion pipeline."""

    def test_original_always_first(self, expander):
        """Original query is always the first variant."""
        result = expander.expand("how does chiller health scoring work?")
        assert result[0] == "how does chiller health scoring work?"

    def test_max_variants_respected(self, expander):
        """Never returns more than MAX_VARIANTS."""
        result = expander.expand("chiller health score maintenance alarm")
        assert len(result) <= MAX_VARIANTS

    def test_empty_query(self, expander):
        """Empty string returns single-element list."""
        assert expander.expand("") == [""]

    def test_none_like_empty(self, expander):
        """Whitespace-only query still returns the original."""
        result = expander.expand("   ")
        assert result[0] == "   "

    def test_equipment_code_expansion(self, expander):
        """Equipment codes generate a variant with expanded type names."""
        result = expander.expand("S002-CHILLER-B1-001 is not cooling")
        # Should have at least 2 variants (original + code expansion)
        assert len(result) >= 2
        # The code-expanded variant should contain chiller-related terms
        code_variant = result[1]
        assert any(term in code_variant.lower() for term in ["cooling plant", "water chiller", "chilled water"])

    def test_synonym_expansion_chiller(self, expander):
        """'chiller' term gets expanded to synonyms."""
        result = expander.expand("what is the chiller doing?")
        # At least one variant should use a chiller synonym
        has_synonym = any("cooling plant" in v.lower() or "water chiller" in v.lower() for v in result[1:])
        assert has_synonym, f"No synonym variant found in: {result}"

    def test_synonym_expansion_load_shedding(self, expander):
        """'load shedding' gets expanded to synonyms."""
        result = expander.expand("how does load shedding integration work?")
        has_synonym = any(
            "loadshedding" in v.lower() or "eskom" in v.lower() or "power outage" in v.lower() for v in result[1:]
        )
        assert has_synonym, f"No synonym variant found in: {result}"

    def test_no_duplicate_variants(self, expander):
        """No duplicate variants in output."""
        result = expander.expand("how does health scoring work for equipment?")
        assert len(result) == len(set(result))

    def test_documentation_rephrase(self, expander):
        """'how does X work' generates a documentation-style variant."""
        result = expander.expand("how does predictive maintenance work")
        # Should have a variant like "predictive maintenance architecture overview"
        has_doc_style = any("architecture" in v or "overview" in v for v in result[1:])
        assert has_doc_style, f"No documentation-style variant in: {result}"

    def test_plain_text_still_returns_original(self, expander):
        """Query with no BMS terms still returns at least the original."""
        result = expander.expand("hello world")
        assert len(result) >= 1
        assert result[0] == "hello world"

    def test_case_insensitive_synonym_match(self, expander):
        """Synonyms match regardless of case."""
        result_lower = expander.expand("the ahu is making noise")
        result_upper = expander.expand("the AHU is making noise")
        # Both should generate synonym variants
        assert len(result_lower) >= 2
        assert len(result_upper) >= 2

    def test_how_to_rephrase(self, expander):
        """'how to' pattern generates guide/procedure variant."""
        result = expander.expand("how to configure DALI zones")
        has_guide = any("guide" in v or "configuration" in v for v in result[1:])
        assert has_guide, f"No guide variant in: {result}"


class TestSingleton:
    """Test singleton pattern."""

    def test_returns_same_instance(self):
        import app.services.query_expansion_service as mod

        mod._query_expansion_service = None
        s1 = get_query_expansion_service()
        s2 = get_query_expansion_service()
        assert s1 is s2
        mod._query_expansion_service = None  # cleanup
