"""POPIA consent guard helpers for ingress and cross-border control."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config.settings import settings
from app.services.consent_service import CONSENT_TEMPLATES, get_consent_service

logger = logging.getLogger(__name__)

_AFFIRMATIVE_TOKENS = {"yes", "y", "agree", "i agree", "accept", "ok", "okay"}
_DECLINE_TOKENS = {"no", "n", "decline", "disagree", "reject"}
_WITHDRAW_TOKENS = {"stop", "opt out", "unsubscribe", "withdraw"}


@dataclass
class IngressConsentDecision:
    """Result of ingress consent evaluation."""

    allow_processing: bool
    status: str
    response_message: str | None = None


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _is_affirmative(message_text: str) -> bool:
    normalized = _normalize_text(message_text)
    return normalized in _AFFIRMATIVE_TOKENS


def _is_decline(message_text: str) -> bool:
    normalized = _normalize_text(message_text)
    return normalized in _DECLINE_TOKENS


def _is_withdraw(message_text: str) -> bool:
    normalized = _normalize_text(message_text)
    if normalized in _WITHDRAW_TOKENS:
        return True
    return normalized.startswith("stop ")


def has_cross_border_consent(data_subject_id: str | None) -> bool:
    """Return true when cross-border transfer consent is active for subject."""
    if not data_subject_id:
        return False
    service = get_consent_service()
    return service.check_consent(data_subject_id, "cross_border_transfer")


def should_allow_cloud_processing(data_subject_id: str | None) -> bool:
    """Cloud processing policy gate based on POPIA consent."""
    if not settings.popia_require_cross_border_consent:
        return True
    return has_cross_border_consent(data_subject_id)


def evaluate_ingress_processing_consent(
    *,
    data_subject_id: str,
    platform: str,
    message_text: str | None,
    ip_address: str | None = None,
) -> IngressConsentDecision:
    """Evaluate and optionally capture PI-processing consent for inbound channels."""
    service = get_consent_service()
    normalized = _normalize_text(message_text)

    has_processing = service.check_consent(data_subject_id, "pi_processing")

    if _is_withdraw(normalized):
        for consent_type in ("pi_processing", "data_retention", "cross_border_transfer"):
            if service.check_consent(data_subject_id, consent_type):
                service.withdraw_consent(
                    data_subject_id=data_subject_id,
                    consent_type=consent_type,
                    metadata={"source": platform, "reason": "withdraw_token"},
                )
        return IngressConsentDecision(
            allow_processing=False,
            status="withdrawn",
            response_message=(
                "You have withdrawn consent for personal information processing. "
                "Reply YES if you want to re-activate service."
            ),
        )

    if has_processing:
        return IngressConsentDecision(allow_processing=True, status="active")

    if _is_affirmative(normalized):
        # Core service consents required by platform policy.
        service.record_consent(
            data_subject_id=data_subject_id,
            platform=platform,
            consent_type="pi_processing",
            consent_given=True,
            ip_address=ip_address,
            metadata={"source": "ingress", "message": normalized},
        )
        service.record_consent(
            data_subject_id=data_subject_id,
            platform=platform,
            consent_type="data_retention",
            consent_given=True,
            ip_address=ip_address,
            metadata={"source": "ingress", "message": normalized},
        )
        return IngressConsentDecision(
            allow_processing=False,
            status="consent_granted",
            response_message=("Consent captured. Thank you. Please resend your request so I can process it."),
        )

    if _is_decline(normalized):
        service.record_consent(
            data_subject_id=data_subject_id,
            platform=platform,
            consent_type="pi_processing",
            consent_given=False,
            ip_address=ip_address,
            metadata={"source": "ingress", "message": normalized},
        )
        return IngressConsentDecision(
            allow_processing=False,
            status="consent_declined",
            response_message=(
                "No problem. We will not process your personal information. Reply YES if you want to opt in later."
            ),
        )

    prompt = CONSENT_TEMPLATES.get("first_contact", {}).get(platform) or (
        "We need your consent to process personal information for this channel."
    )
    return IngressConsentDecision(
        allow_processing=False,
        status="consent_required",
        response_message=f"{prompt}\n\nReply YES to consent or NO to decline.",
    )


def enforce_active_processing_consent(*, data_subject_id: str) -> bool:
    """Simple gate for non-conversational ingress operations."""
    service = get_consent_service()
    return service.check_consent(data_subject_id, "pi_processing")
