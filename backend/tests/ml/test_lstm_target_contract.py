import pytest

from ml.lstm.train import resolve_lstm_training_contract


def test_lstm_target_contract_uses_configured_target_when_present(monkeypatch):
    monkeypatch.setattr(
        "ml.lstm.train.get_lstm_features",
        lambda equipment_type, site_id=None: ["chw_return_temp", "chw_supply_temp"],
    )

    features, target = resolve_lstm_training_contract("chiller", site_id="site-002")

    assert features == ["chw_return_temp", "chw_supply_temp"]
    assert target == "chw_supply_temp"


def test_lstm_target_contract_fails_when_site_features_omit_configured_target(monkeypatch):
    monkeypatch.setattr(
        "ml.lstm.train.get_lstm_features",
        lambda equipment_type, site_id=None: ["co2_ppm", "room_temp"],
    )

    with pytest.raises(ValueError) as exc:
        resolve_lstm_training_contract("fcu", site_id="site-002")

    message = str(exc.value)
    assert "expected target 'supply_temp'" in message
    assert "co2_ppm" in message
    assert "room_temp" in message
    assert "site-002" in message


def test_lstm_target_contract_keeps_global_defaults_when_site_features_absent(monkeypatch):
    monkeypatch.setattr("ml.lstm.train.get_lstm_features", lambda equipment_type, site_id=None: [])

    features, target = resolve_lstm_training_contract("vav", site_id="site-002")

    assert target == "zone_temp"
    assert "zone_temp" in features
