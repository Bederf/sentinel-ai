"""SENTINEL Sentry Email Intake Service"""

from .classifier import EmailClassification, get_email_classifier

__all__ = ["EmailClassification", "get_email_classifier"]
