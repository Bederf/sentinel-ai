"""Tests for semantic dictionary loader service.

Phase 162: Semantic Control Foundation — Plan 01.
"""

from __future__ import annotations

import pytest

from app.models.semantic_tag import SafetyClass, SemanticDictionary, SemanticTag
from app.services.simbiot.semantic_dictionary import SemanticDictionaryService


@pytest.fixture()
def service() -> SemanticDictionaryService:
    svc = SemanticDictionaryService()
    svc.load()
    return svc


def test_dictionary_loads_valid_json(service: SemanticDictionaryService) -> None:
    """Dictionary loads without validation errors."""
    dictionary = service.get_dictionary()
    assert dictionary is not None
    assert isinstance(dictionary, SemanticDictionary)
    assert dictionary.version == "1.0"


def test_dictionary_has_minimum_tag_count(service: SemanticDictionaryService) -> None:
    """At least 40 semantic tags must be defined."""
    tags = service.list_tags()
    assert len(tags) >= 40, f"Expected >= 40 tags, got {len(tags)}"


def test_all_tags_have_valid_safety_classes(service: SemanticDictionaryService) -> None:
    """Every tag must have a LOW, MEDIUM, or HIGH safety class."""
    valid_classes = {SafetyClass.LOW, SafetyClass.MEDIUM, SafetyClass.HIGH}
    for tag_name in service.list_tags():
        tag = service.get_tag(tag_name)
        assert tag is not None
        assert tag.safety_class in valid_classes, f"Tag '{tag_name}' has invalid safety class: {tag.safety_class}"


def test_supply_air_temp_tag_has_correct_rules(service: SemanticDictionaryService) -> None:
    """Supply air temp tag must have multiple classification rules."""
    tag = service.get_tag("supply_air_temperature_sensor")
    assert tag is not None, "supply_air_temperature_sensor tag not found"
    assert len(tag.classification_rules) >= 2
    sources = {rule.source for rule in tag.classification_rules}
    assert "haystack_id" in sources or "point_name" in sources


def test_get_tag_returns_expected_structure(service: SemanticDictionaryService) -> None:
    """get_tag() returns a fully populated SemanticTag."""
    tag = service.get_tag("compressor_occupancy_command")
    assert tag is not None
    assert isinstance(tag, SemanticTag)
    assert tag.description
    assert len(tag.applies_to) > 0
    assert len(tag.classification_rules) > 0
    assert tag.safety_class == SafetyClass.MEDIUM


def test_find_by_equipment_type_filters_correctly(service: SemanticDictionaryService) -> None:
    """find_by_equipment_type() returns tags applicable to equipment."""
    ahu_tags = service.find_by_equipment_type("AHU")
    assert len(ahu_tags) >= 3, "Expected multiple AHU tags"

    for tag in ahu_tags:
        applies_lower = [e.lower() for e in tag.applies_to]
        assert "ahu" in applies_lower, f"Tag {tag.tag} returned for AHU but not in applies_to"


def test_high_safety_tags_have_strict_envelopes(service: SemanticDictionaryService) -> None:
    """HIGH safety tags must have monitor_only=True or requires_approval_above."""
    for tag_name in service.list_tags():
        tag = service.get_tag(tag_name)
        assert tag is not None
        if tag.safety_class == SafetyClass.HIGH:
            envelope = tag.control_envelope
            assert envelope is not None, f"HIGH safety tag '{tag_name}' must have a control_envelope"
            is_restricted = (
                envelope.monitor_only or envelope.requires_approval_above is not None or not envelope.writable
            )
            assert is_restricted, (
                f"HIGH safety tag '{tag_name}' must have monitor_only, requires_approval_above, or writable=False"
            )


def test_control_envelopes_have_reasonable_limits(service: SemanticDictionaryService) -> None:
    """Control envelopes with bounds must have physically reasonable limits."""
    for tag_name in service.list_tags():
        tag = service.get_tag(tag_name)
        assert tag is not None
        if tag.control_envelope and tag.control_envelope.bounds:
            bounds = tag.control_envelope.bounds
            assert bounds.min < bounds.max, f"Tag '{tag_name}' has bounds.min >= bounds.max"


def test_get_safety_class_returns_string(service: SemanticDictionaryService) -> None:
    """get_safety_class() returns a plain string value."""
    sc = service.get_safety_class("emergency_stop_status")
    assert sc == "HIGH"


def test_get_tag_returns_none_for_unknown(service: SemanticDictionaryService) -> None:
    """get_tag() returns None for an unknown tag name."""
    tag = service.get_tag("nonexistent_tag_xyz")
    assert tag is None


def test_tag_name_injected_correctly(service: SemanticDictionaryService) -> None:
    """Each SemanticTag.tag field matches its dictionary key."""
    for tag_name in service.list_tags():
        tag = service.get_tag(tag_name)
        assert tag is not None
        assert tag.tag == tag_name, f"Tag key '{tag_name}' != tag.tag '{tag.tag}'"
