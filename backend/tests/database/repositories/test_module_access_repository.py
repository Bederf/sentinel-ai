"""Module access repository tests for registry-driven mandatory modules."""

from app.database.repositories.module_access_repository import ModuleAccessRepository
from app.models.auth import SentinelRole
from app.models.module_registry import ModuleDefinition, ModuleInstance, ModuleStatus, ModuleType


class _RegistryStub:
    def __init__(self) -> None:
        self._registry = {
            ModuleType.HVAC: ModuleDefinition(
                module_type=ModuleType.HVAC,
                name="HVAC",
                version="1.0.0",
                description="HVAC",
                mandatory=True,
            ),
            ModuleType.MAINTENANCE: ModuleDefinition(
                module_type=ModuleType.MAINTENANCE,
                name="Maintenance",
                version="1.0.0",
                description="Maintenance",
                mandatory=False,
            ),
        }

    def get_module_registry(self):
        return self._registry

    def get_active_modules(self, _site_code: str):
        return [
            ModuleInstance(
                instance_id="site-1-maintenance",
                site_id="site-1",
                module_type=ModuleType.MAINTENANCE,
                status=ModuleStatus.ACTIVE,
                activated_at="2026-01-01T00:00:00Z",
            )
        ]


def test_get_active_modules_includes_registry_mandatory(monkeypatch):
    monkeypatch.setattr("app.database.repositories.module_access_repository.get_supabase_client", lambda: None)
    repo = ModuleAccessRepository()
    monkeypatch.setattr("app.database.repositories.module_access_repository.module_registry", _RegistryStub())

    active_modules = repo.get_active_modules(site_code="site-1")

    assert active_modules == ["hvac", "maintenance"]


def test_get_effective_modules_filters_explicit_grants_to_active_registry(monkeypatch):
    monkeypatch.setattr("app.database.repositories.module_access_repository.get_supabase_client", lambda: None)
    repo = ModuleAccessRepository()
    monkeypatch.setattr("app.database.repositories.module_access_repository.module_registry", _RegistryStub())
    monkeypatch.setattr(repo, "get_user_modules", lambda **_kwargs: ["maintenance", "financial"])

    effective_modules = repo.get_effective_modules(
        user_email="user@example.com",
        user_role=SentinelRole.AUDITOR,
        site_code="site-1",
    )

    assert effective_modules == ["hvac", "maintenance"]
