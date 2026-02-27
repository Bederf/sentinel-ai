"""Unit tests for POPIA consent guard behavior."""

import uuid

import pytest

from app.services.consent_service import get_consent_service
from app.services.popia_consent_guard import (
    evaluate_ingress_processing_consent,
    should_allow_cloud_processing,
)


@pytest.mark.unit
def test_ingress_consent_flow_captures_processing_consent():
    """First message requires consent, YES captures and enables pi_processing."""
    subject = f"guard-test-{uuid.uuid4()}"

    first = evaluate_ingress_processing_consent(
        data_subject_id=subject,
        platform="whatsapp",
        message_text="hello",
    )
    assert first.allow_processing is False
    assert first.status == "consent_required"

    consented = evaluate_ingress_processing_consent(
        data_subject_id=subject,
        platform="whatsapp",
        message_text="YES",
    )
    assert consented.allow_processing is False
    assert consented.status == "consent_granted"

    service = get_consent_service()
    assert service.check_consent(subject, "pi_processing") is True


@pytest.mark.unit
def test_cloud_processing_requires_cross_border_consent():
    """Cloud gate must stay closed without cross-border consent."""
    from app.config.settings import settings

    # Ensure the consent requirement is active for this test
    original = settings.popia_require_cross_border_consent
    settings.popia_require_cross_border_consent = True

    try:
        subject = f"guard-cross-border-{uuid.uuid4()}"
        service = get_consent_service()

        assert should_allow_cloud_processing(subject) is False

        service.record_consent(
            data_subject_id=subject,
            platform="web",
            consent_type="cross_border_transfer",
            consent_given=True,
        )
        assert should_allow_cloud_processing(subject) is True
    finally:
        settings.popia_require_cross_border_consent = original
