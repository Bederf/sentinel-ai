import json

import pytest

from ml.registry import ModelRegistry, build_input_contract_metadata


def _contract(site_id: str | None, equipment_type: str, model_type: str = "lstm") -> dict:
    return build_input_contract_metadata(
        site_id=site_id,
        equipment_type=equipment_type,
        model_type=model_type,
        required_features=["chw_supply_temp"] if equipment_type == "chiller" else ["filter_dp"],
        target="chw_supply_temp" if model_type == "lstm" else "reconstruction_error",
    )


def test_site_scoped_active_model_does_not_fall_back_to_global(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    registry = ModelRegistry(registry_path=str(registry_path))

    global_id = registry.register_model(
        model_type="lstm",
        equipment_type="chiller",
        model_path="/tmp/global.h5",
        metrics={},
        metadata=_contract(None, "chiller"),
        auto_activate=True,
    )
    site_id = registry.register_model(
        model_type="lstm",
        equipment_type="chiller",
        site_id="site-002",
        model_path="/tmp/site.h5",
        metrics={},
        metadata={"feature_names": ["chw_supply_temp"], **_contract("site-002", "chiller")},
        auto_activate=True,
    )

    assert registry.get_active_model("lstm", "chiller")["model_id"] == global_id
    site_model = registry.get_active_model("lstm", "chiller", site_id="site-002")
    assert site_model["model_id"] == site_id
    assert site_model["site_id"] == "site-002"
    assert site_model["metadata"]["site_id"] == "site-002"
    assert registry.get_active_model("lstm", "chiller", site_id="site-005") is None


def test_list_models_can_filter_by_site_id(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    registry = ModelRegistry(registry_path=str(registry_path))

    registry.register_model(
        "autoencoder",
        "ahu",
        "/tmp/global.h5",
        {},
        metadata=_contract(None, "ahu", "autoencoder"),
        auto_activate=True,
    )
    registry.register_model(
        "autoencoder",
        "ahu",
        "/tmp/site.h5",
        {},
        metadata=_contract("site-002", "ahu", "autoencoder"),
        auto_activate=True,
        site_id="site-002",
    )

    site_models = registry.list_models(model_type="autoencoder", equipment_type="ahu", site_id="site-002")
    assert len(site_models) == 1
    assert site_models[0]["site_id"] == "site-002"


def test_lstm_registration_rejects_missing_input_contract(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    registry = ModelRegistry(registry_path=str(registry_path))

    with pytest.raises(ValueError, match="missing input contract metadata"):
        registry.register_model(
            model_type="lstm",
            equipment_type="chiller",
            model_path="/tmp/model.h5",
            metrics={},
            metadata={"feature_names": ["chw_supply_temp"]},
            auto_activate=False,
        )
