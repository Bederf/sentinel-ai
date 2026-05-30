from __future__ import annotations

import json

import pytest

from app.api.residential_onboarding import _encrypt_site_config
from app.services.encryption_service import get_encryption_service

_TEST_CONFIG = {"email": "user@example.com", "password": "hunter2", "site_id": "site-test"}


# ── Round-trip ────────────────────────────────────────────────────────────────

def test_encrypt_decrypt_round_trip():
    ciphertext = _encrypt_site_config(_TEST_CONFIG)
    svc = get_encryption_service()
    recovered = json.loads(svc.decrypt(ciphertext))
    assert recovered == _TEST_CONFIG


def test_ciphertext_differs_from_plaintext():
    ciphertext = _encrypt_site_config(_TEST_CONFIG)
    assert ciphertext != json.dumps(_TEST_CONFIG)


def test_different_encryptions_differ():
    # Fernet uses random IVs — same input gives different ciphertext each time
    svc = get_encryption_service()
    if not svc.enabled:
        pytest.skip("Encryption disabled (no ENCRYPTION_KEY set)")
    c1 = _encrypt_site_config(_TEST_CONFIG)
    c2 = _encrypt_site_config(_TEST_CONFIG)
    assert c1 != c2


# ── Credential safety ─────────────────────────────────────────────────────────

def test_password_not_in_ciphertext():
    svc = get_encryption_service()
    if not svc.enabled:
        pytest.skip("Encryption disabled (no ENCRYPTION_KEY set)")
    ciphertext = _encrypt_site_config(_TEST_CONFIG)
    assert "hunter2" not in ciphertext
    assert "user@example.com" not in ciphertext


def test_site_config_not_logged_during_onboard(caplog):
    """Ensure plaintext credentials do not appear in any log record."""
    import logging
    with caplog.at_level(logging.DEBUG):
        _encrypt_site_config(_TEST_CONFIG)
    for record in caplog.records:
        assert "hunter2" not in record.message
