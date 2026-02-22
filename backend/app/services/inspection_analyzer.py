"""Inspection Analysis Service

Analyzes technician inspection findings to recommend next actions:
- RESOLVED: Issue fixed during inspection
- RECOMMEND_REPAIR: Issue found, recommend repair/maintenance work order
- MONITOR: Minor issue, schedule follow-up

Powered by contextual analysis of findings, health score changes, and keyword detection.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class InspectionDecision(str, Enum):
    """Decision after analyzing inspection findings."""

    RESOLVED = "resolved"
    RECOMMEND_REPAIR = "recommend_repair"
    MONITOR = "monitor"


@dataclass
class InspectionAnalysisResult:
    """Result of inspection analysis with recommendation."""

    decision: InspectionDecision
    severity: Optional[str] = None  # high, medium, low
    reason: Optional[str] = None  # Human-readable explanation
    parts_needed: Optional[list] = None  # Recommended parts
    confidence: float = 0.8  # Confidence in recommendation (0-1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API response."""
        return {
            "decision": self.decision.value,
            "severity": self.severity,
            "reason": self.reason,
            "parts_needed": self.parts_needed or [],
            "confidence": self.confidence,
        }


class InspectionAnalyzer:
    """Analyzes inspection findings to recommend repair actions."""

    # Keywords that indicate resolved issues
    RESOLVED_KEYWORDS = [
        "fixed",
        "resolved",
        "working",
        "normal",
        "functioning",
        "operational",
        "back to normal",
        "cleaned",
        "cleared",
        "reset",
    ]

    # Keywords that indicate critical/high severity issues
    CRITICAL_KEYWORDS = [
        "failed",
        "broken",
        "replace",
        "major",
        "leak",
        "damage",
        "crack",
        "severe",
        "critical",
        "emergency",
        "catastrophic",
    ]

    # Keywords that indicate repair is needed
    REPAIR_KEYWORDS = [
        "needs",
        "repair",
        "calibrate",
        "adjustment",
        "recalibrate",
        "maintenance",
        "overdue",
        "service",
        "replacement",
        "component",
    ]

    # Keywords that indicate monitoring is sufficient
    MONITOR_KEYWORDS = [
        "monitor",
        "watch",
        "track",
        "observe",
        "check",
        "follow up",
        "minor",
        "cosmetic",
        "aesthetic",
        "clean",
    ]

    def analyze_inspection_completion(
        self,
        findings: str,
        equipment_code: str,
        health_before: int = None,
        health_after: int = None,
        parts_needed: list = None,
        technician_notes: str = None,
    ) -> InspectionAnalysisResult:
        """
        Analyze inspection findings to recommend next action.

        Args:
            findings: Technician's inspection findings text
            equipment_code: Equipment identifier
            health_before: Equipment health before inspection (optional)
            health_after: Equipment health after inspection (optional)
            parts_needed: List of parts identified as needed
            technician_notes: Additional notes from technician

        Returns:
            InspectionAnalysisResult with decision and reasoning
        """
        findings_lower = findings.lower() if findings else ""

        # Check for resolved issues
        if self._check_resolved(findings_lower, health_before, health_after):
            return InspectionAnalysisResult(
                decision=InspectionDecision.RESOLVED, reason=self._extract_resolution_summary(findings), confidence=0.9
            )

        # Check for critical issues requiring repair
        if self._check_critical_issue(findings_lower, parts_needed):
            return InspectionAnalysisResult(
                decision=InspectionDecision.RECOMMEND_REPAIR,
                severity="high",
                reason=self._extract_issue_summary(findings),
                parts_needed=parts_needed,
                confidence=0.95,
            )

        # Check for repair needed
        if self._check_repair_needed(findings_lower, health_before, health_after):
            return InspectionAnalysisResult(
                decision=InspectionDecision.RECOMMEND_REPAIR,
                severity="medium",
                reason=self._extract_issue_summary(findings),
                parts_needed=parts_needed,
                confidence=0.85,
            )

        # Default: Monitor if unclear
        return InspectionAnalysisResult(
            decision=InspectionDecision.MONITOR,
            reason="Issue appears minor or unclear. Continue monitoring.",
            confidence=0.7,
        )

    def _check_resolved(self, findings_lower: str, health_before: int = None, health_after: int = None) -> bool:
        """Check if findings indicate the issue was resolved."""
        # Keyword match for resolved status
        if any(keyword in findings_lower for keyword in self.RESOLVED_KEYWORDS):
            # If health improved significantly, more confident
            if health_before and health_after and health_after >= 80:
                return True

        # If health jumped from warning to normal, likely resolved
        if health_before and health_after:
            if health_before < 65 and health_after >= 80:
                return True

        return False

    def _check_critical_issue(self, findings_lower: str, parts_needed: list = None) -> bool:
        """Check if findings indicate a critical issue requiring repair."""
        # Critical keywords found
        if any(keyword in findings_lower for keyword in self.CRITICAL_KEYWORDS):
            return True

        # Parts explicitly needed indicates repair required
        if parts_needed and len(parts_needed) > 0:
            # Major parts (not just consumables)
            major_parts = [p for p in parts_needed if not self._is_consumable(p)]
            if major_parts:
                return True

        return False

    def _check_repair_needed(self, findings_lower: str, health_before: int = None, health_after: int = None) -> bool:
        """Check if findings indicate repair is needed."""
        # Repair keywords found
        if any(keyword in findings_lower for keyword in self.REPAIR_KEYWORDS):
            # Only recommend repair if health didn't improve much
            if health_before and health_after:
                health_improvement = health_after - health_before
                if health_improvement < 10:  # Minimal improvement despite inspection
                    return True
            return True

        return False

    def _is_consumable(self, part: str) -> bool:
        """Check if a part is a consumable (vs major component)."""
        consumables = [
            "filter",
            "oil",
            "fluid",
            "coolant",
            "lubricant",
            "seal",
            "gasket",
            "wipe",
            "cloth",
            "battery",
            "fuse",
        ]
        part_lower = part.lower()
        return any(c in part_lower for c in consumables)

    def _extract_resolution_summary(self, findings: str) -> str:
        """Extract a summary of how the issue was resolved."""
        if not findings:
            return "Issue resolved during inspection"

        # Look for resolution keywords and extract context
        resolution_context = ""
        for keyword in self.RESOLVED_KEYWORDS:
            if keyword in findings.lower():
                # Find sentence containing keyword
                sentences = findings.split(".")
                for sentence in sentences:
                    if keyword in sentence.lower():
                        resolution_context = sentence.strip()
                        break
                if resolution_context:
                    break

        return resolution_context or "Issue resolved during inspection"

    def _extract_issue_summary(self, findings: str) -> str:
        """Extract a summary of the identified issue."""
        if not findings:
            return "Issue identified requiring repair"

        # Take first 100 chars or first sentence
        if len(findings) > 100:
            period_index = findings.find(".")
            if period_index > 0 and period_index < 150:
                return findings[: period_index + 1]
            return findings[:100] + "..."

        return findings

    @staticmethod
    def get_analyzer() -> "InspectionAnalyzer":
        """Get singleton instance of analyzer."""
        if not hasattr(InspectionAnalyzer, "_instance"):
            InspectionAnalyzer._instance = InspectionAnalyzer()
        return InspectionAnalyzer._instance


# Singleton accessor
def get_inspection_analyzer() -> InspectionAnalyzer:
    """Get or create the singleton InspectionAnalyzer instance.

    Returns:
        InspectionAnalyzer: The singleton analyzer
    """
    return InspectionAnalyzer.get_analyzer()
