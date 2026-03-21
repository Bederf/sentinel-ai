"""Template completeness scoring for equipment point sets.

Phase 162: Semantic Control Foundation — Plan 03.
Scores how completely a classified equipment matches expected critical/important/optional points.
"""

from __future__ import annotations

from typing import List


class TemplateCompletenessCalculator:
    """Calculates how completely an equipment matches expected template."""

    def calculate_completeness(
        self,
        equipment_type: str,
        classified_points: List[dict],
        expected_template: dict,
    ) -> float:
        """Calculate completeness score (0.0 to 1.0).

        Critical = Required for safe operation          (weight 0.7)
        Important = Required for efficiency optimisation (weight 0.3)
        Optional  = Nice to have for diagnostics         (not scored)

        Formula:
            (critical_weight * critical_fraction) + (important_weight * important_fraction)
        """
        present_tags = {point.get("semantic_tag") for point in classified_points}

        expected_critical = expected_template.get("critical_points", [])
        expected_important = expected_template.get("important_points", [])

        critical_present = sum(1 for tag in expected_critical if tag in present_tags)
        important_present = sum(1 for tag in expected_important if tag in present_tags)

        critical_weight = 0.7
        important_weight = 0.3

        critical_score = (critical_present / len(expected_critical)) * critical_weight if expected_critical else 0.0
        important_score = (
            (important_present / len(expected_important)) * important_weight if expected_important else 0.0
        )

        return min(1.0, critical_score + important_score)

    def generate_completeness_report(
        self,
        equipment_type: str,
        completeness_score: float,
        present_tags: List[str],
        expected_template: dict,
    ) -> dict:
        """Generate human-readable completeness report."""
        report: dict = {
            "equipment_type": equipment_type,
            "completeness_score": completeness_score,
            "grade": self._get_grade(completeness_score),
            "critical_points_present": [],
            "critical_points_missing": [],
            "important_points_present": [],
            "important_points_missing": [],
            "recommendations": [],
        }

        for tag in expected_template.get("critical_points", []):
            if tag in present_tags:
                report["critical_points_present"].append(tag)
            else:
                report["critical_points_missing"].append(tag)

        for tag in expected_template.get("important_points", []):
            if tag in present_tags:
                report["important_points_present"].append(tag)
            else:
                report["important_points_missing"].append(tag)

        if report["critical_points_missing"]:
            missing_count = len(report["critical_points_missing"])
            report["recommendations"].append(f"Missing {missing_count} critical points required for safe operation")

        if completeness_score < 0.5:
            report["recommendations"].append(
                "Equipment template is incomplete. Review point mappings or BMS discovery."
            )
        elif completeness_score >= 0.9:
            report["recommendations"].append(
                "Template is nearly complete. Add optional points for enhanced diagnostics."
            )

        return report

    def _get_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score >= 0.9:
            return "A"
        if score >= 0.8:
            return "B"
        if score >= 0.7:
            return "C"
        if score >= 0.6:
            return "D"
        return "F"
