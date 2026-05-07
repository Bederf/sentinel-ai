#!/usr/bin/env python3
"""Tests for ThesaurusService — 14 core tests."""

import pytest
from ..thesaurus_service import (
    ThesaurusService,
    get_thesaurus,
    classify_complaint,
    is_facilities,
    MATCH_THRESHOLD,
)
from ..complaint_thesaurus import (
    ComplaintCategory,
    get_all_entries,
)


class TestThesaurusService:
    def test_singleton(self):
        t1 = get_thesaurus()
        t2 = get_thesaurus()
        assert t1 is t2

    def test_stats_keys(self):
        ts = ThesaurusService()
        stats = ts.get_stats()
        assert "total_entries" in stats
        assert stats["match_threshold"] == MATCH_THRESHOLD
        assert stats["categories"] == 5

    def test_is_facilities_positive(self):
        ts = ThesaurusService()
        assert ts.is_facilities_complaint("too cold at desk 203")
        assert ts.is_facilities_complaint("hot in here")
        assert ts.is_facilities_complaint("stuffy air near window")
        assert ts.is_facilities_complaint("lights flickering")

    def test_is_facilities_negative(self):
        ts = ThesaurusService()
        assert not ts.is_facilities_complaint("hello")
        assert not ts.is_facilities_complaint("what time is it")
        assert not ts.is_facilities_complaint("meeting at 3pm")

    def test_classify_returns_result_for_valid_input(self):
        ts = ThesaurusService()
        r = ts.classify("freezing at desk 208")
        assert r is not None
        assert r.category == ComplaintCategory.TOO_COLD
        assert r.priority == "high"
        assert r.specialty == "hvac"

    def test_classify_returns_none_for_garbage(self):
        ts = ThesaurusService()
        assert ts.classify("lunch menu options") is None
        assert ts.classify("") is None

    def test_keyword_index_built(self):
        ts = ThesaurusService()
        assert len(ts._keyword_index) > 100

    def test_all_categories_have_classifications(self):
        """Every category can be reached via known phrases."""
        ts = ThesaurusService()
        for cat in ComplaintCategory:
            found = False
            for phrase, expected_cat in [
                ("hot in here", ComplaintCategory.TOO_HOT),
                ("freezing", ComplaintCategory.TOO_COLD),
                ("stuffy air", ComplaintCategory.STUFFY_AIR),
                ("light not working", ComplaintCategory.LIGHTING),
                ("water leak", ComplaintCategory.OTHER),
            ]:
                r = ts.classify(phrase)
                if r and r.category == expected_cat:
                    found = True
            assert found, f"No classification found for {cat}"


class TestClassifyComplaint:
    def test_classify_complaint_returns_dict(self):
        result = classify_complaint("hot in here")
        assert result is not None
        assert isinstance(result, dict)
        assert "discipline" in result
        assert "sub_category" in result
        assert result["discipline"] == "HVAC"

    def test_is_facilities_bool(self):
        assert is_facilities("too cold") is True
        assert is_facilities("hello world") is False


class TestComplaintCategories:
    def test_hvac_discipline(self):
        ts = ThesaurusService()
        for text in ["hot in here", "freezing", "stuffy air"]:
            r = ts.classify(text)
            assert r is not None
            assert r.discipline == "HVAC"

    def test_lighting_discipline(self):
        ts = ThesaurusService()
        r = ts.classify("light not working")
        assert r is not None
        assert r.discipline == "Lighting"
        assert r.category == ComplaintCategory.LIGHTING

    def test_priority_values(self):
        ts = ThesaurusService()
        r = ts.classify("too cold")
        assert r is not None
        assert r.priority in ("high", "medium", "low")


class TestGetAllEntries:
    def test_returns_list(self):
        entries = get_all_entries()
        assert isinstance(entries, list)
        assert len(entries) > 40

    def test_entries_have_required_fields(self):
        for entry in get_all_entries():
            assert hasattr(entry, "canonical")
            assert hasattr(entry, "category")
            assert hasattr(entry, "keywords")
            assert isinstance(entry.keywords, tuple)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
