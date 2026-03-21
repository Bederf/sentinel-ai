"""Confidence score calculator for semantic point classification.

Phase 162: Semantic Control Foundation — Plan 02.

Implements the weighted evidence formula:

    confidence = min(1.0, Σ(evidence.weight) / required_evidence_threshold)

Where:
- Each EvidenceRecord contributes its weight (0.0-1.0)
- required_evidence_threshold is the minimum total weight needed for acceptance
- Confidence is capped at 1.0 so it always represents a probability-like score
"""

from __future__ import annotations

from app.models.point_classification import EvidenceRecord


class ConfidenceCalculator:
    """Calculates confidence scores from a list of evidence records.

    All methods are static so the calculator can be used without instantiation.
    """

    @staticmethod
    def calculate_confidence(
        evidence_records: list[EvidenceRecord],
        required_evidence: int,
    ) -> float:
        """Calculate confidence using the weighted evidence formula.

        Formula::

            confidence = min(1.0, Σ(evidence.weight) / required_evidence)

        Args:
            evidence_records: List of matching evidence records.
            required_evidence: Minimum evidence threshold from SemanticTag.
                Must be >= 1; if 0 is passed it is treated as 1 to avoid
                division-by-zero.

        Returns:
            Confidence score in [0.0, 1.0].
        """
        if not evidence_records:
            return 0.0

        # Guard against zero denominator
        denominator = max(required_evidence, 1)
        total_weighted_evidence = sum(record.weight for record in evidence_records)
        confidence = total_weighted_evidence / denominator

        return min(1.0, confidence)

    @staticmethod
    def classify_confidence_level(confidence: float) -> str:
        """Translate a confidence score to a human-readable tier.

        Tiers:
            HIGH   — confidence >= 0.7
            MEDIUM — 0.4 <= confidence < 0.7
            LOW    — confidence < 0.4
        """
        if confidence >= 0.7:
            return "HIGH"
        if confidence >= 0.4:
            return "MEDIUM"
        return "LOW"
