"""ML Explanations module for generating natural language explanations."""

from ml.explanations.parser import ExplanationParser
from ml.explanations.templates import (
    MAINTENANCE_RECOMMENDATION_TEMPLATE,
    PREDICTION_EXPLANATION_TEMPLATE,
    get_equipment_specific_template,
)

__all__ = [
    "MAINTENANCE_RECOMMENDATION_TEMPLATE",
    "PREDICTION_EXPLANATION_TEMPLATE",
    "ExplanationParser",
    "get_equipment_specific_template",
]
