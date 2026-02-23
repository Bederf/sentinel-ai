"""Tests for POPIA consent API registration and core flows."""

import uuid


def test_consent_templates_endpoint_is_registered(test_client):
    """Consent templates endpoint should be available under /api/consent."""
    response = test_client.get("/api/consent/templates")
    assert response.status_code == 200

    data = response.json()
    assert "first_contact" in data
    assert "consent_types" in data
    assert "web" in data["first_contact"]
    assert "whatsapp" in data["first_contact"]
    assert "telegram" in data["first_contact"]


def test_consent_record_and_check_flow(test_client):
    """Recording consent should make check endpoint return true."""
    subject_id = f"test-consent-{uuid.uuid4()}"
    payload = {
        "data_subject_id": subject_id,
        "platform": "web",
        "consent_type": "pi_processing",
        "consent_given": True,
    }

    record_response = test_client.post("/api/consent/record", json=payload)
    assert record_response.status_code == 200

    check_response = test_client.get(f"/api/consent/check/{subject_id}/pi_processing")
    assert check_response.status_code == 200
    assert check_response.json()["has_consent"] is True


def test_consent_withdraw_flow(test_client):
    """Withdrawing consent should make check endpoint return false."""
    subject_id = f"test-consent-withdraw-{uuid.uuid4()}"

    record_payload = {
        "data_subject_id": subject_id,
        "platform": "web",
        "consent_type": "data_retention",
        "consent_given": True,
    }
    withdraw_payload = {
        "data_subject_id": subject_id,
        "consent_type": "data_retention",
    }

    record_response = test_client.post("/api/consent/record", json=record_payload)
    assert record_response.status_code == 200

    withdraw_response = test_client.post("/api/consent/withdraw", json=withdraw_payload)
    assert withdraw_response.status_code == 200

    check_response = test_client.get(f"/api/consent/check/{subject_id}/data_retention")
    assert check_response.status_code == 200
    assert check_response.json()["has_consent"] is False
