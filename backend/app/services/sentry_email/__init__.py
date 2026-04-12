"""SENTINEL Sentry Email Intake Service"""

from .classifier import get_email_classifier, EmailClassification

__all__ = ["get_email_classifier", "EmailClassification"]
