"""Priority classification dataclass for semantic priority correction."""

from dataclasses import dataclass


@dataclass
class PriorityClassification:
    """Result of semantic priority classification.

    Attaches to recommendation creation to correct misclassified
    consumables (e.g. soap dispensers flagged as CRITICAL).

    Fields:
        is_consumable: True if the issue is a consumable replace, not a fault
        original_priority: Priority that was assigned by keyword classifier
        corrected_priority: Corrected priority (may be same as original)
        reason: Human-readable explanation of the correction
        confidence: Classification confidence (0.0-1.0)
        classification_method: How classification was done:
            - "keyword" = matched consumables taxonomy directly
            - "embedding" = matched via embedding similarity
    """

    is_consumable: bool
    original_priority: str
    corrected_priority: str
    reason: str
    confidence: float  # 0.0-1.0
    classification_method: str  # "keyword" | "embedding"
