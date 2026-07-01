import json

from ml.registry import ModelRegistry


def test_site_scoped_active_model_does_not_fall_back_to_global(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    registry = ModelRegistry(registry_path=str(registry_path))

    global_id = registry.register_model(
        model_type="lstm",
        equipment_type="chiller",
        model_path="/tmp/global.h5",
        metrics={},
        metadata={},
        auto_activate=True,
    )
    site_id = registry.register_model(
        model_type="lstm",
        equipment_type="chiller",
        site_id="site-002",
        model_path="/tmp/site.h5",
        metrics={},
        metadata={"feature_names": ["chw_supply_temp"]},
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

    registry.register_model("autoencoder", "ahu", "/tmp/global.h5", {}, auto_activate=True)
    registry.register_model(
        "autoencoder",
        "ahu",
        "/tmp/site.h5",
        {},
        metadata={},
        auto_activate=True,
        site_id="site-002",
    )

    site_models = registry.list_models(model_type="autoencoder", equipment_type="ahu", site_id="site-002")
    assert len(site_models) == 1
    assert site_models[0]["site_id"] == "site-002"
