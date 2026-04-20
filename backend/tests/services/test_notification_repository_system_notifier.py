"""Tests for FK-safe system notifier technician resolution."""

from uuid import UUID

from app.database.repositories.notification_repository import (
    SYSTEM_NOTIFIER_TECHNICIAN_CODE,
    SYSTEM_NOTIFIER_TECHNICIAN_ID,
    NotificationRepository,
)


class _Response:
    def __init__(self, data=None):
        self.data = data or []


class _TableQuery:
    def __init__(self, table_name: str, store: dict):
        self.table_name = table_name
        self.store = store
        self._eq_field = None
        self._eq_value = None
        self._insert_data = None

    def select(self, _fields):
        return self

    def eq(self, field, value):
        self._eq_field = field
        self._eq_value = value
        return self

    def limit(self, _n):
        return self

    def insert(self, data):
        self._insert_data = data
        return self

    def execute(self):
        if self._insert_data is not None and self.table_name == "technicians":
            self.store["technicians"][self._insert_data["code"]] = self._insert_data
            return _Response(data=[self._insert_data])

        if self.table_name == "technicians" and self._eq_field == "code":
            row = self.store["technicians"].get(self._eq_value)
            return _Response(data=[{"id": row["id"]}] if row else [])

        return _Response(data=[])


class _FakeSupabaseClient:
    def __init__(self):
        self.store = {"technicians": {}}

    def table(self, table_name):
        return _TableQuery(table_name, self.store)


def _repo_with_fake_client() -> NotificationRepository:
    repo = NotificationRepository()
    repo.use_json = False
    repo.client = _FakeSupabaseClient()
    return repo


def test_resolve_non_system_technician_id_passthrough():
    repo = _repo_with_fake_client()
    actual = UUID("11111111-1111-1111-1111-111111111111")
    resolved = repo._resolve_delivery_log_technician_id(actual)
    assert resolved == actual


def test_resolve_system_notifier_uses_existing_row():
    repo = _repo_with_fake_client()
    existing_id = "22222222-2222-2222-2222-222222222222"
    repo.client.store["technicians"][SYSTEM_NOTIFIER_TECHNICIAN_CODE] = {"id": existing_id}

    resolved = repo._resolve_delivery_log_technician_id(UUID(int=0))
    assert resolved == UUID(existing_id)


def test_resolve_system_notifier_inserts_when_missing():
    repo = _repo_with_fake_client()

    resolved = repo._resolve_delivery_log_technician_id(UUID(int=0))
    assert resolved == SYSTEM_NOTIFIER_TECHNICIAN_ID
    inserted = repo.client.store["technicians"][SYSTEM_NOTIFIER_TECHNICIAN_CODE]
    assert inserted["id"] == str(SYSTEM_NOTIFIER_TECHNICIAN_ID)
    assert inserted["name"] == "System Notifier"
