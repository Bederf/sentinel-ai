"""Tests for the Explanation Parser."""

import pytest
from ml.explanations.parser import (
    ExplanationParser,
    ParsedAction,
    ParsedRecommendation,
    ParsingError
)


class TestExplanationParser:
    """Test cases for ExplanationParser."""

    def test_parse_with_valid_actions(self):
        """Test parsing explanation with valid action sections."""
        explanation = """
**Root Cause:** The chiller is showing signs of refrigerant leak

**Actions:**
- **Action #1:** Inspect refrigerant lines and connections
  - **Urgency:** High
  - **Estimated Time:** 2.5 hours
  - **Estimated Cost:** R 3,500
  - **Parts Required:** Refrigerant leak detector, sealant

- **Action #2:** Schedule professional leak repair service
  - **Urgency:** Medium
  - **Estimated Time:** 4 hours
  - **Estimated Cost:** R 12,000

**Next Steps:** Monitor pressure levels
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        assert len(result.actions) == 2
        assert result.actions[0].description == "Inspect refrigerant lines and connections"
        assert result.actions[0].urgency == "High"
        assert result.actions[0].estimated_time_hours == 2.5
        assert result.actions[0].estimated_cost == 3500.0
        assert "Refrigerant leak detector" in result.actions[0].parts_required

    def test_parse_with_alternative_format(self):
        """Test parsing with alternative action format."""
        explanation = """
Problem: Generator battery showing low voltage

Recommended Actions:
1. Check battery terminals for corrosion (URGENCY: HIGH)
   - Time: 0.5 hours
   - Cost: R 200
   - Parts: Terminal cleaner

2. Test battery voltage (URGENCY: Medium)
   - Time: 0.25 hours

3. Replace battery if needed (URGENCY: LOW)
   - Time: 1.5 hours
   - Cost: R 2,500
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        assert len(result.actions) == 3
        assert "battery terminals" in result.actions[0].description
        assert result.actions[0].urgency == "HIGH"

    def test_parse_without_actions(self):
        """Test parsing explanation without explicit actions."""
        explanation = """
The HVAC system is operating normally within expected parameters.
Temperature readings are consistent with seasonal patterns.
No immediate action required.
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        assert len(result.actions) == 0
        assert result.keywords == ["normal", "expected", "No action"]

    def test_parse_cost_variations(self):
        """Test parsing various cost formats."""
        explanation = """
Action 1: Replace filter
- Cost: R 500
- Cost: R1,200
- Cost: $100
- Cost: €50
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        # Should extract numeric values
        assert any("R" in str(action.estimated_cost) for action in result.actions)

    def test_explanation_classification(self):
        """Test automatic explanation classification."""
        test_cases = [
            ("Critical fault detected", "anomaly"),
            ("Normal operation", "normal_operation"),
            ("Pred maintenance warning", "predictive"),
            ("Urgent action required", "anomaly"),
            ("System OK", "normal_operation")
        ]

        for text, expected_class in test_cases:
            classification = ExplanationParser._classify_explanation(text)
            assert classification == expected_class

    def test_empty_explanation(self):
        """Test handling of empty explanation."""
        parser = ExplanationParser()
        result = parser.parse_explanation("")

        assert result.explanation_type == "unknown"
        assert len(result.actions) == 0
        assert len(result.keywords) == 0

    def test_malformed_explanation(self):
        """Test parsing malformed explanation."""
        explanation = """
**Action:** Incomplete action
- **Urgency:** High
Missing time and cost

**Action:** Another incomplete
- **Estimated Time:** 2 hours
Missing urgency
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        # Should still extract valid information
        assert len(result.actions) == 2
        # Actions with missing required fields should still be included

    def test_parts_extraction(self):
        """Test extraction of required parts."""
        explanation = """
Action: Replace pump seal
Parts Required:
- Mechanical seal kit
- Gasket set
- Lubricant
Tools: Wrench set, torque wrench
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        assert len(result.actions) == 1
        parts = result.actions[0].parts_required
        assert "Mechanical seal kit" in parts
        assert "Gasket set" in parts
        assert "Lubricant" in parts

    def test_urgency_normalization(self):
        """Test normalization of urgency levels."""
        parser = ExplanationParser()

        assert parser._normalize_urgency("HIGH") == "high"
        assert parser._normalize_urgency("medium") == "medium"
        assert parser._normalize_urgency("Low") == "low"
        assert parser._normalize_urgency("critical") == "critical"
        assert parser._normalize_urgency("URGENT") == "high"  # Mapping

    def test_confidence_extraction(self):
        """Test extraction of confidence scores."""
        explanation = """
Analysis confidence: 87%
Model accuracy: 92.5%
I'm 75% sure about this
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        # Should extract highest confidence value
        assert result.confidence >= 0.75
        assert result.confidence <= 0.925

    def test_risk_assessment_extraction(self):
        """Test extraction of risk assessment."""
        explanation = """
Risk Level: High
Potential Impact: Equipment damage
Probability: 70%
If not addressed: System failure
Probability (if not addressed): 85%
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        assert result.risk_assessment is not None
        assert result.risk_assessment.risk_level == "high"
        assert result.risk_assessment.impact == "Equipment damage"
        assert "70%" in result.risk_assessment.probability_description

    def test_maintenance_recommendation_parsing(self):
        """Test parsing of maintenance recommendations."""
        explanation = """
**Recommendation #1:** Perform preventive maintenance
**Category:** Preventive
**Priority:** High
**Justification:** Based on usage patterns
**Expected Outcome:** 15% efficiency improvement
**Timeline:** Next 7 days
**Cost-Benefit:** High ROI
**Success Metrics:** Efficiency gain, failure reduction
"""

        parser = ExplanationParser()
        result = parser.parse_recommendation(explanation)

        assert result.category == "Preventive"
        assert result.priority == "High"
        assert "15% efficiency" in result.expected_outcome
        assert len(result.success_metrics) == 2

    def test_parse_with_multiple_sections(self):
        """Test parsing complex explanation with multiple sections."""
        explanation = """
## Root Cause Analysis
The compressor is cycling too frequently.

## Fault Code
FC-2301

## Severity
MEDIUM

## Immediate Actions Required
1. Check refrigerant charge (URGENCY: MEDIUM)
   - Time: 1 hour
   - Cost: R 800

2. Inspect compressor contacts (URGENCY: LOW)
   - Time: 0.5 hours

## Long Term Recommendations
Schedule comprehensive maintenance

## Supporting Data
Pressure readings: 210 kPa
"""

        parser = ExplanationParser()
        result = parser.parse_explanation(explanation)

        assert result.explanation_type == "anomaly"  # Due to "fault" and "urgency"
        assert len(result.actions) == 2
        assert result.supporting_data.get("pressure") == "210 kPa"
        assert "FC-2301" in result.fault_code

    def test_score_calculation(self):
        """Test confidence score calculation."""
        parser = ExplanationParser()

        # Test with various confidence indicators
        score = parser._calculate_confidence_score(
            has_actions=True,
            has_time_estimate=True,
            has_cost_estimate=True,
            has_risk_assessment=True,
            completeness_score=0.8,
            explicit_confidence=0.85
        )

        assert score > 0.85  # Should be boosted by additional factors
        assert score <= 1.0

    def test_complex_cost_parsing(self):
        """Test parsing of complex cost formats."""
        test_cases = [
            ("R 1,234.56", 1234.56),
            ("R1234", 1234.0),
            ("R2,500.00", 2500.0),
            ("R 500", 500.0),
            ("Cost: R 1,500-2,000", 1750.0),  # Average
        ]

        parser = ExplanationParser()

        for cost_str, expected in test_cases:
            parsed = parser._parse_cost(cost_str)
            assert parsed == expected

    def test_invalid_input_handling(self):
        """Test graceful handling of invalid input."""
        parser = ExplanationParser()

        # None input
        with pytest.raises(ParsingError):
            parser.parse_explanation(None)

        # Non-string input
        with pytest.raises(ParsingError):
            parser.parse_explanation(123)
