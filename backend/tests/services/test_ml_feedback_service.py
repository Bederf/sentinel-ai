"""Unit tests for ML feedback module gating behavior."""

from app.services.ml_feedback_service import MLFeedbackService


class _DummyModuleRegistry:
    """Simple in-memory module registry stub for eligibility checks."""

    def __init__(self, active_modules_by_site: dict[str, set[str]] | None = None):
        self._active_modules_by_site = active_modules_by_site or {}

    def get_site_config(self, site_id: str):
        if site_id in self._active_modules_by_site:
            return {"site_id": site_id}
        return None

    def is_module_active(self, site_id, module_type):
        return module_type.value in self._active_modules_by_site.get(site_id, set())


def test_base_module_feedback_always_eligible(monkeypatch):
    """Base-pack modules should remain eligible for shared ML learning."""
    monkeypatch.setattr(MLFeedbackService, "_load_state", lambda self: None)
    service = MLFeedbackService()
    assert service._is_module_eligible_for_feedback("site-002", "hvac") is True


def test_addon_feedback_ineligible_when_module_inactive(monkeypatch):
    """Add-on module feedback must fail closed when module is not active."""
    monkeypatch.setattr(MLFeedbackService, "_load_state", lambda self: None)
    service = MLFeedbackService()

    from app.services import module_registry_service as registry_module

    monkeypatch.setattr(registry_module, "module_registry", _DummyModuleRegistry({}))
    assert service._is_module_eligible_for_feedback("site-002", "control") is False


def test_addon_feedback_eligible_with_site_id_normalization(monkeypatch):
    """Eligibility should work across S002/site-002 variants."""
    monkeypatch.setattr(MLFeedbackService, "_load_state", lambda self: None)
    service = MLFeedbackService()

    from app.services import module_registry_service as registry_module

    dummy_registry = _DummyModuleRegistry({"site-002": {"control"}})
    monkeypatch.setattr(registry_module, "module_registry", dummy_registry)

    assert service._is_module_eligible_for_feedback("S002", "control") is True
