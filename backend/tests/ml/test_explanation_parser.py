"""Tests for the Explanation Parser."""

from ml.explanations.parser import (
    ActionPriority,
    ExplanationParser,
    ParsedExplanation,
    ParsedRecommendation,
    PartNeeded,
    RecommendedAction,
    parse_llm_explanation,
    parse_llm_recommendation,
)


class TestExplanationParser:
    """Test cases for ExplanationParser."""

    def test_parse_explanation_with_sections(self):
        """Test parsing explanation with valid section markers."""
        explanation = """
### SUMMARY
The chiller is showing signs of refrigerant leak

### KEY_FACTORS
- High discharge pressure
- Low suction pressure
- Unusual noise from compressor

### RECOMMENDED_ACTIONS
- [HIGH] Inspect refrigerant lines and connections
- [MEDIUM] Schedule professional leak repair service
- Check compressor oil level

### PARTS_NEEDED
- Refrigerant leak detector
- Sealant kit (1)

### LABOR_ESTIMATE
2.5 hours for inspection, 4 hours for repair

### ADDITIONAL_NOTES
Monitor pressure levels after repair
"""

        result = ExplanationParser.parse_explanation(explanation)

        assert isinstance(result, ParsedExplanation)
        assert result.parse_success is True
        assert "refrigerant leak" in result.summary
        assert len(result.key_factors) == 3
        assert len(result.recommended_actions) >= 2
        assert result.recommended_actions[0].priority == ActionPriority.HIGH
        assert len(result.parts_needed) >= 1
        assert "2.5 hours" in result.labor_estimate

    def test_parse_explanation_without_sections(self):
        """Test parsing explanation without explicit section markers."""
        explanation = """
The HVAC system is operating normally within expected parameters.
Temperature readings are consistent with seasonal patterns.
No immediate action required.
"""

        result = ExplanationParser.parse_explanation(explanation)

        assert isinstance(result, ParsedExplanation)
        # Without matching sections, parse_success should be False
        assert result.parse_success is False
        assert len(result.recommended_actions) == 0

    def test_parse_empty_explanation(self):
        """Test handling of empty explanation."""
        result = ExplanationParser.parse_explanation("")

        assert isinstance(result, ParsedExplanation)
        assert result.parse_success is False
        assert len(result.recommended_actions) == 0

    def test_parse_actions_with_priorities(self):
        """Test parsing actions with explicit priority markers."""
        actions_text = """
- [HIGH] Inspect compressor immediately
- [LOW] Schedule routine check
- [MEDIUM] Order replacement parts
- Review maintenance log
"""

        actions = ExplanationParser._parse_actions(actions_text)

        assert len(actions) == 4
        assert actions[0].priority == ActionPriority.HIGH
        assert actions[0].action == "Inspect compressor immediately"
        assert actions[1].priority == ActionPriority.LOW
        assert actions[2].priority == ActionPriority.MEDIUM
        # Action without priority defaults to MEDIUM
        assert actions[3].priority == ActionPriority.MEDIUM

    def test_parse_parts_needed(self):
        """Test extraction of required parts."""
        parts_text = """
- Mechanical seal kit (2)
- Gasket set
- Lubricant
"""

        parts = ExplanationParser._parse_parts(parts_text)

        assert len(parts) == 3
        assert parts[0].name == "Mechanical seal kit"
        assert parts[0].quantity == "2"
        assert parts[1].name == "Gasket set"
        assert parts[1].quantity is None

    def test_parse_parts_filters_none(self):
        """Test that 'none' and 'n/a' parts are filtered out."""
        parts_text = """
- None
- n/a
- Actual part needed
- None anticipated
"""

        parts = ExplanationParser._parse_parts(parts_text)

        assert len(parts) == 1
        assert parts[0].name == "Actual part needed"

    def test_parse_list_items(self):
        """Test parsing bulleted list items."""
        text = """
- Item one
- Item two
* Item three
1. Item four
"""

        items = ExplanationParser._parse_list_items(text)

        assert len(items) == 4
        assert items[0] == "Item one"

    def test_parse_list_items_empty(self):
        """Test parsing empty list returns empty."""
        assert ExplanationParser._parse_list_items("") == []
        assert ExplanationParser._parse_list_items("   ") == []

    def test_clean_text(self):
        """Test text cleaning removes markdown artifacts."""
        assert ExplanationParser._clean_text("**bold** text") == "bold text"
        assert ExplanationParser._clean_text("[link text]") == "link text"
        assert ExplanationParser._clean_text("  spaced   out  ") == "spaced out"
        assert ExplanationParser._clean_text("") == ""

    def test_parse_recommendation(self):
        """Test parsing of maintenance recommendations."""
        recommendation = """
### IMMEDIATE_ACTIONS
- Shut down affected unit
- Isolate circuit

### SCHEDULED_MAINTENANCE
- [Next 7 days] Full compressor service
- [Monthly] Filter replacement

### PREVENTIVE_MEASURES
- Regular vibration monitoring
- Oil analysis quarterly

### SPARE_PARTS
- Compressor bearing | CB-2301 | 1
- Oil filter | OF-100 | 2

### TECHNICIAN_SKILLS
- HVAC certification
- Refrigeration specialist

### ESTIMATED_DOWNTIME
4-6 hours for repair
"""

        result = ExplanationParser.parse_recommendation(recommendation)

        assert isinstance(result, ParsedRecommendation)
        assert result.parse_success is True
        assert len(result.immediate_actions) == 2
        assert len(result.scheduled_maintenance) >= 1
        assert len(result.preventive_measures) == 2
        assert len(result.spare_parts) >= 1
        assert len(result.technician_skills) == 2
        assert "4-6 hours" in result.estimated_downtime

    def test_parse_scheduled_items(self):
        """Test parsing scheduled items with timelines."""
        text = """
- [Weekly] Check belt tension
- [Monthly] Replace filters
- General inspection
"""

        items = ExplanationParser._parse_scheduled_items(text)

        assert len(items) == 3
        assert items[0]["timeline"] == "Weekly"
        assert "belt tension" in items[0]["action"]
        assert items[2]["timeline"] == "As scheduled"

    def test_parse_detailed_parts(self):
        """Test parsing parts with pipe-separated details."""
        text = """
- Bearing assembly | BA-1234 | 2
- Seal kit | SK-5678
- Lubricant
"""

        parts = ExplanationParser._parse_detailed_parts(text)

        assert len(parts) == 3
        assert parts[0].name == "Bearing assembly"
        assert parts[0].part_number == "BA-1234"
        assert parts[0].quantity == "2"
        assert parts[1].part_number == "SK-5678"
        assert parts[1].quantity is None

    def test_parsed_explanation_to_dict(self):
        """Test conversion of ParsedExplanation to dict."""
        result = ParsedExplanation(
            summary="Test summary",
            key_factors=["factor1"],
            recommended_actions=[RecommendedAction(action="Do thing", priority=ActionPriority.HIGH)],
            parts_needed=[PartNeeded(name="Part1", quantity="1")],
            labor_estimate="2 hours",
        )

        d = result.to_dict()

        assert d["summary"] == "Test summary"
        assert len(d["recommended_actions"]) == 1
        assert d["recommended_actions"][0]["priority"] == "HIGH"
        assert d["parse_success"] is True

    def test_parsed_recommendation_to_dict(self):
        """Test conversion of ParsedRecommendation to dict."""
        result = ParsedRecommendation(
            immediate_actions=["action1"],
            technician_skills=["HVAC"],
            estimated_downtime="4 hours",
        )

        d = result.to_dict()

        assert d["immediate_actions"] == ["action1"]
        assert d["estimated_downtime"] == "4 hours"
        assert d["parse_success"] is True

    def test_convenience_functions(self):
        """Test the module-level convenience functions."""
        explanation = """
### SUMMARY
Test explanation

### RECOMMENDED_ACTIONS
- [HIGH] Take action
"""
        result = parse_llm_explanation(explanation)
        assert isinstance(result, dict)
        assert "summary" in result
        assert "recommended_actions" in result

        recommendation = """
### IMMEDIATE_ACTIONS
- Do something now
"""
        result = parse_llm_recommendation(recommendation)
        assert isinstance(result, dict)
        assert "immediate_actions" in result

    def test_recommended_action_to_dict(self):
        """Test RecommendedAction serialization."""
        action = RecommendedAction(action="Inspect valve", priority=ActionPriority.HIGH)
        d = action.to_dict()
        assert d == {"action": "Inspect valve", "priority": "HIGH"}

    def test_part_needed_to_dict(self):
        """Test PartNeeded serialization."""
        part = PartNeeded(name="Seal kit", quantity="2", part_number="SK-100")
        d = part.to_dict()
        assert d == {"name": "Seal kit", "quantity": "2", "part_number": "SK-100"}

    def test_extract_sections_multiple_formats(self):
        """Test section extraction with different markdown formats."""
        # Bold format
        text = """
**SUMMARY**
Bold format summary

**KEY_FACTORS**
- Factor one
"""
        sections = ExplanationParser._extract_sections(text, ["SUMMARY", "KEY_FACTORS"])
        assert "SUMMARY" in sections
        assert "Bold format" in sections["SUMMARY"]
