"""Tests for ConsentService with mocked Supabase client."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.consent_service import ConsentService, get_consent_service


def _make_mock_result(data=None, count=0):
    return MagicMock(data=data or [], count=count)


class MockQueryBuilder:
    """Simulates Supabase query builder chain."""

    def __init__(self, result_data=None):
        self._result = _make_mock_result(result_data or [])
        self._side_effects = None
        self._call_count = 0

    def select(self, *args, **kwargs):
        return self

    def insert(self, data, **kwargs):
        record = data
        rid = record.get("record_id") if isinstance(record, dict) else str(uuid.uuid4())
        result_data = [
            {
                "record_id": rid,
                "data_subject_id": record.get("data_subject_id", ""),
                "platform": record.get("platform", ""),
                "consent_type": record.get("consent_type", ""),
                "consent_given": record.get("consent_given", False),
                "consent_text": record.get("consent_text", ""),
                "given_at": record.get("given_at", ""),
                "expires_at": record.get("expires_at"),
                "withdrawn_at": record.get("withdrawn_at"),
                "ip_address": record.get("ip_address"),
                "metadata": record.get("metadata", {}),
            }
        ]
        self._result = _make_mock_result(result_data)
        return self

    def update(self, data, **kwargs):
        return self

    def delete(self, **kwargs):
        return self

    def eq(self, col, val):
        return self

    def neq(self, col, val):
        return self

    def order(self, col, **kwargs):
        return self

    def limit(self, n):
        return self

    def gte(self, col, val):
        return self

    def lte(self, col, val):
        return self

    def execute(self):
        return self._result

    def rpc(self, name, args):
        return self


@pytest.fixture(autouse=True)
def reset_singleton():
    ConsentService._instance = None
    ConsentService._initialized = False
    yield
    ConsentService._instance = None
    ConsentService._initialized = False


@pytest.fixture
def mock_repo():
    with patch("app.database.repositories.consent_repository.get_supabase_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value = MockQueryBuilder()
        mock_get.return_value = mock_client
        yield mock_client


@pytest.mark.unit
def test_record_and_check_consent(mock_repo):
    subject = f"test-{uuid.uuid4()}"
    service = get_consent_service()

    record = service.record_consent(
        data_subject_id=subject,
        platform="web",
        consent_type="pi_processing",
        consent_given=True,
    )
    assert record.consent_given is True

    result = service.check_consent(subject, "pi_processing")
    assert result is True


@pytest.mark.unit
def test_consent_not_given_if_none_recorded(mock_repo):
    service = get_consent_service()
    result = service.check_consent("nonexistent", "pi_processing")
    assert result is False


@pytest.mark.unit
def test_consent_withdrawal(mock_repo):
    subject = f"test-withdraw-{uuid.uuid4()}"
    service = get_consent_service()

    # Record consent first
    service.record_consent(
        data_subject_id=subject,
        platform="web",
        consent_type="pi_processing",
        consent_given=True,
    )

    result = service.withdraw_consent(subject, "pi_processing")
    assert result.consent_given is False
    assert result.platform == "withdrawal"


@pytest.mark.unit
def test_get_consent_history(mock_repo):
    subject = f"test-history-{uuid.uuid4()}"
    service = get_consent_service()

    service.record_consent(subject, "web", "pi_processing", True)
    history = service.get_consent_history(subject)
    assert len(history) >= 1


@pytest.mark.unit
def test_consent_stats(mock_repo):
    service = get_consent_service()
    stats = service.get_consent_stats()
    assert "total_records" in stats
    assert "active_consents" in stats
    assert "withdrawals" in stats
    assert "by_platform" in stats
    assert "by_consent_type" in stats


@pytest.mark.unit
def test_export_consent_records(mock_repo):
    service = get_consent_service()
    records = service.export_consent_records()
    assert isinstance(records, list)
