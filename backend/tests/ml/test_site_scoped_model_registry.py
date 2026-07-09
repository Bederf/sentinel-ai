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


def test_classifier_registration_rejects_missing_input_contract(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    registry = ModelRegistry(registry_path=str(registry_path))

    with pytest.raises(ValueError, match="missing input contract metadata"):
        registry.register_model(
            model_type="classifier",
            equipment_type="chiller",
            model_path="/tmp/model.joblib",
            metrics={"cv_accuracy": 0.75},
            metadata={"feature_names": ["temperature"]},
            auto_activate=False,
        )


def test_registry_recovers_from_backup_when_primary_json_is_corrupt(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    registry = ModelRegistry(registry_path=str(registry_path))

    model_id = registry.register_model(
        model_type="lstm",
        equipment_type="chiller",
        model_path="/tmp/site.h5",
        metrics={"r2_24h": 0.81},
        metadata={"feature_names": ["chw_supply_temp"], **_contract("site-002", "chiller")},
        auto_activate=True,
        site_id="site-002",
    )

    registry_path.write_text("{broken")

    recovered = ModelRegistry(registry_path=str(registry_path))

    assert recovered.get_active_model("lstm", "chiller", site_id="site-002")["model_id"] == model_id


def test_registry_reload_picks_up_cross_worker_activation(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    worker_a = ModelRegistry(registry_path=str(registry_path))
    worker_b = ModelRegistry(registry_path=str(registry_path))

    generation_before = worker_b._generation
    assert worker_b.get_active_model("lstm", "chiller", site_id="site-002") is None

    model_id = worker_a.register_model(
        model_type="lstm",
        equipment_type="chiller",
        model_path="/tmp/site.h5",
        metrics={"r2_24h": 0.9},
        metadata={"feature_names": ["chw_supply_temp"], **_contract("site-002", "chiller")},
        auto_activate=True,
        site_id="site-002",
    )

    active = worker_b.get_active_model("lstm", "chiller", site_id="site-002")
    assert active is not None
    assert active["model_id"] == model_id
    assert worker_b._generation > generation_before


def test_registry_own_write_does_not_trigger_spurious_reload(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    registry = ModelRegistry(registry_path=str(registry_path))

    registry.register_model(
        model_type="lstm",
        equipment_type="chiller",
        model_path="/tmp/site.h5",
        metrics={"r2_24h": 0.9},
        metadata={"feature_names": ["chw_supply_temp"], **_contract("site-002", "chiller")},
        auto_activate=True,
        site_id="site-002",
    )

    generation_after_activate = registry._generation
    registry.get_active_model("lstm", "chiller", site_id="site-002")
    assert registry._generation == generation_after_activate


def test_cross_worker_registration_survives_stale_writer(tmp_path):
    """Worker B activating after worker A registered must not clobber A's entry."""
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": {}, "active": {}}))
    worker_a = ModelRegistry(registry_path=str(registry_path))
    worker_b = ModelRegistry(registry_path=str(registry_path))

    id_a = worker_a.register_model(
        model_type="lstm",
        equipment_type="chiller",
        model_path="/tmp/a.h5",
        metrics={"r2_24h": 0.9},
        metadata=_contract(None, "chiller"),
        auto_activate=True,
    )
    id_b = worker_b.register_model(
        model_type="autoencoder",
        equipment_type="ahu",
        model_path="/tmp/b.h5",
        metrics={"recall": 0.8},
        metadata=_contract(None, "ahu", "autoencoder"),
        auto_activate=True,
    )

    fresh = ModelRegistry(registry_path=str(registry_path))
    assert fresh.get_model(id_a) is not None
    assert fresh.get_model(id_b) is not None
    assert fresh.get_active_model("lstm", "chiller")["model_id"] == id_a
    assert fresh.get_active_model("autoencoder", "ahu")["model_id"] == id_b
