"""ML Explanations module for generating natural language explanations."""

from ml.explanations.templates import (
    PREDICTION_EXPLANATION_TEMPLATE,
    MAINTENANCE_RECOMMENDATION_TEMPLATE,
    get_equipment_specific_template,
)
from ml.explanations.parser import ExplanationParser

__all__ = [
    "PREDICTION_EXPLANATION_TEMPLATE",
    "MAINTENANCE_RECOMMENDATION_TEMPLATE",
    "get_equipment_specific_template",
    "ExplanationParser",
]
