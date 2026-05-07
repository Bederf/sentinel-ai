"""Tests for the authoritative module registry endpoint."""

from app.models.module_registry import MODULE_DEFINITIONS


def test_get_module_registry_endpoint_exposes_full_registry(test_client, auth_headers_operator):
    response = test_client.get("/api/modules/registry", headers=auth_headers_operator)

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {module_type.value for module_type in MODULE_DEFINITIONS}
    assert payload["hvac"]["mandatory"] is True
    assert payload["maintenance"]["mandatory"] is False
    assert payload["block_booking"]["module_type"] == "block_booking"
