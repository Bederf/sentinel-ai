from datetime import UTC, datetime, timedelta

from ml.data.supabase_loader import SupabaseTrainingDataLoader


def test_loader_pivots_telemetry_hourly_with_site_features(monkeypatch):
    monkeypatch.setattr(
        "ml.data.supabase_loader.get_lstm_features",
        lambda equipment_type, site_id=None: ["supply_air_temp", "return_air_temp"],
    )
    monkeypatch.setattr(
        "ml.data.supabase_loader._resolve_config",
        lambda equipment_type, site_id=None: {"site_id": site_id, "equipment_type": equipment_type},
    )

    base = datetime(2026, 7, 1, 0, tzinfo=UTC)
    rows = []
    for hour in range(3):
        rows.extend(
            [
                {
                    "equipment_id": "S002-AHU-001",
                    "sensor_type": "supply_air_temp",
                    "value": 18 + hour,
                    "recorded_at": base + timedelta(hours=hour),
                },
                {
                    "equipment_id": "S002-AHU-001",
                    "sensor_type": "return_air_temp",
                    "value": 23 + hour,
                    "recorded_at": base + timedelta(hours=hour),
                },
            ]
        )

    loader = SupabaseTrainingDataLoader(site_id="site-002")
    monkeypatch.setattr(loader, "_query_hourly_aggregates", lambda **_kwargs: rows)

    df = loader.load_equipment_type_dataframe(
        "ahu", min_hours=2, required_features=["supply_air_temp", "return_air_temp"]
    )

    assert df is not None
    assert list(df.columns) == ["timestamp", "supply_air_temp", "return_air_temp"]
    assert len(df) == 3
    assert loader.last_load_metadata["data_source"] == "telemetry_hourly"
    assert loader.last_load_metadata["site_id"] == "site-002"
    assert loader.last_load_metadata["real_hours_available"] == 3


def test_loader_reports_not_ready_when_feature_complete_hours_short(monkeypatch):
    monkeypatch.setattr("ml.data.supabase_loader.list_ml_trainable_types", lambda site_id=None: ["ahu"])
    monkeypatch.setattr(
        "ml.data.supabase_loader.get_lstm_features", lambda equipment_type, site_id=None: ["supply_air_temp"]
    )
    monkeypatch.setattr(
        "ml.data.supabase_loader.get_autoencoder_features",
        lambda equipment_type, site_id=None: ["supply_air_temp"],
    )
    loader = SupabaseTrainingDataLoader(site_id="site-002")
    monkeypatch.setattr(loader, "_query_hourly_aggregates", lambda **_kwargs: [])

    summary = loader.get_data_summary()

    assert summary["ahu"]["available_hours"] == 0
    assert summary["ahu"]["data_source"] == "telemetry_hourly"
    assert summary["ahu"]["ready_for_lstm"] is False
    assert summary["ahu"]["ready_for_autoencoder"] is False
