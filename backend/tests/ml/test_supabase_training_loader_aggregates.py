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


def _patched_loader(monkeypatch, rows, features):
    monkeypatch.setattr(
        "ml.data.supabase_loader.get_lstm_features",
        lambda equipment_type, site_id=None: list(features),
    )
    monkeypatch.setattr(
        "ml.data.supabase_loader._resolve_config",
        lambda equipment_type, site_id=None: {"site_id": site_id, "equipment_type": equipment_type},
    )
    loader = SupabaseTrainingDataLoader(site_id="site-002")
    monkeypatch.setattr(loader, "_query_hourly_aggregates", lambda **_kwargs: rows)
    # Hermetic: no DB lookup for operating hours — heuristic fallback unless a test overrides
    monkeypatch.setattr(loader, "_load_site_operating_hours", lambda: None)
    return loader


def _rows_for(feature_values: dict[str, list[float | None]], base: datetime | None = None):
    base = base or datetime(2026, 7, 1, 0, tzinfo=UTC)
    rows = []
    for feature, values in feature_values.items():
        for hour, value in enumerate(values):
            if value is None:
                continue
            rows.append(
                {
                    "equipment_id": "S002-AHU-001",
                    "sensor_type": feature,
                    "value": value,
                    "recorded_at": base + timedelta(hours=hour),
                }
            )
    return rows


def test_variance_gate_blocks_pinned_feature(monkeypatch):
    rows = _rows_for(
        {
            "supply_air_temp": [18.0, 19.5, 21.0, 20.0, 18.5, 19.0],
            "valve_position": [48.0] * 6,
        }
    )
    loader = _patched_loader(monkeypatch, rows, ["supply_air_temp", "valve_position"])

    df = loader.load_equipment_type_dataframe(
        "ahu", min_hours=2, required_features=["supply_air_temp", "valve_position"]
    )

    assert df is None
    gate = loader.last_load_metadata["variance_gate"]
    assert gate["passed"] is False
    assert gate["degenerate_features"] == ["valve_position"]
    assert loader.last_load_metadata["feature_stats"]["valve_position"]["degenerate"] is True
    assert loader.last_load_metadata["feature_stats"]["supply_air_temp"]["degenerate"] is False


def test_variance_gate_blocks_near_constant_feature(monkeypatch):
    # Distinct values but std/|mean| far below the CV floor (a "1100±0.0001" pin)
    rows = _rows_for(
        {
            "supply_air_temp": [18.0, 19.5, 21.0, 20.0, 18.5, 19.0],
            "co2_ppm": [1100.0, 1100.0001, 1100.0, 1100.0002, 1100.0001, 1100.0],
        }
    )
    loader = _patched_loader(monkeypatch, rows, ["supply_air_temp", "co2_ppm"])

    df = loader.load_equipment_type_dataframe("ahu", min_hours=2, required_features=["supply_air_temp", "co2_ppm"])

    assert df is None
    assert loader.last_load_metadata["variance_gate"]["degenerate_features"] == ["co2_ppm"]


def test_provenance_records_forward_fill_and_stats(monkeypatch):
    # return_air_temp missing at hour 2 -> one forward-filled cell
    rows = _rows_for(
        {
            "supply_air_temp": [18.0, 19.5, 21.0, 20.0, 18.5, 19.0],
            "return_air_temp": [23.0, 24.0, None, 25.0, 23.5, 24.5],
        }
    )
    loader = _patched_loader(monkeypatch, rows, ["supply_air_temp", "return_air_temp"])

    df = loader.load_equipment_type_dataframe(
        "ahu", min_hours=2, required_features=["supply_air_temp", "return_air_temp"]
    )

    assert df is not None
    assert len(df) == 6
    # The filled value must actually be present in the returned frame
    assert not df[["supply_air_temp", "return_air_temp"]].isna().any().any()
    assert df["return_air_temp"].iloc[2] == 24.0

    meta = loader.last_load_metadata
    assert meta["variance_gate"]["passed"] is True
    assert meta["forward_fill_limit_hours"] == 3
    assert meta["forward_filled_cells"] == {"supply_air_temp": 0, "return_air_temp": 1}
    assert meta["forward_filled_cells_total"] == 1
    stats = meta["feature_stats"]["supply_air_temp"]
    assert stats["distinct_values"] == 6
    assert stats["std"] > 0


def test_variance_gate_blocks_temporally_pinned_feature(monkeypatch):
    # damper_position passes the GLOBAL variance floor (one full day of real
    # movement) but is flat for 3 of 4 days -> temporally pinned -> blocked.
    varying_day = [50.0 + h * 4 for h in range(24)]
    supply = [15.0 + (h % 24) * 0.5 for h in range(96)]
    damper = [100.0] * 72 + varying_day
    rows = _rows_for({"supply_air_temp": supply, "damper_position": damper})
    loader = _patched_loader(monkeypatch, rows, ["supply_air_temp", "damper_position"])

    df = loader.load_equipment_type_dataframe(
        "ahu", min_hours=2, required_features=["supply_air_temp", "damper_position"]
    )

    assert df is None
    gate = loader.last_load_metadata["variance_gate"]
    assert gate["degenerate_features"] == ["damper_position"]
    stats = loader.last_load_metadata["feature_stats"]["damper_position"]
    assert stats["degenerate_reason"] == "temporally_pinned"
    assert stats["degenerate_window_fraction"] == 0.75
    assert stats["longest_flat_run_hours"] == 72
    # Global floor alone would have passed it
    assert stats["distinct_values"] > 1
    assert stats["std"] > 0


def test_variance_gate_allows_legitimate_weekend_flatness(monkeypatch):
    # Plant off 2 of 7 days (weekend) is real building behaviour, not a dead
    # channel: 2/7 degenerate windows is under the majority threshold, and the
    # flat days land on Sat/Sun so they never enter the occupied-hours check.
    varying_week = [50.0 + (h % 24) * 4 for h in range(120)]
    damper = varying_week + [0.0] * 48
    supply = [15.0 + (h % 24) * 0.5 for h in range(168)]
    base = datetime(2026, 6, 29, 0, tzinfo=UTC)  # Monday
    rows = _rows_for({"supply_air_temp": supply, "damper_position": damper}, base=base)
    loader = _patched_loader(monkeypatch, rows, ["supply_air_temp", "damper_position"])

    df = loader.load_equipment_type_dataframe(
        "ahu", min_hours=2, required_features=["supply_air_temp", "damper_position"]
    )

    assert df is not None
    assert loader.last_load_metadata["variance_gate"]["passed"] is True
    stats = loader.last_load_metadata["feature_stats"]["damper_position"]
    assert stats["degenerate"] is False
    assert stats["degenerate_reason"] is None
    assert stats["degenerate_window_fraction"] == round(2 / 7, 3)
    assert stats["longest_flat_run_hours"] == 48


def test_variance_gate_blocks_occupied_hours_pinned_feature(monkeypatch):
    # CO2 flat through business hours but moving at night (recirc effects):
    # every full-day window passes on night-time variance, so only the
    # occupied-hours check can catch it. 5 weekdays from Mon 2026-06-29.
    # Occupied = weekday 06:00-22:00 SAST = 04:00-20:00 UTC.
    co2 = []
    room = []
    for day in range(5):
        for h in range(24):
            co2.append(1100.0 if 4 <= h < 20 else 600.0 + day * 17 + h * 10)
            room.append(18.0 + h * 0.3 + day * 0.1)
    base = datetime(2026, 6, 29, 0, tzinfo=UTC)
    rows = []
    for feature, values in {"co2_ppm": co2, "room_temp": room}.items():
        for hour, value in enumerate(values):
            rows.append(
                {
                    "equipment_id": "S002-FCU-001",
                    "sensor_type": feature,
                    "value": value,
                    "recorded_at": base + timedelta(hours=hour),
                }
            )
    loader = _patched_loader(monkeypatch, rows, ["co2_ppm", "room_temp"])

    df = loader.load_equipment_type_dataframe("fcu", min_hours=2, required_features=["co2_ppm", "room_temp"])

    assert df is None
    gate = loader.last_load_metadata["variance_gate"]
    assert gate["degenerate_features"] == ["co2_ppm"]
    stats = loader.last_load_metadata["feature_stats"]["co2_ppm"]
    assert stats["degenerate_reason"] == "occupied_hours_pinned"
    assert stats["degenerate_occupied_window_fraction"] == 1.0
    assert stats["longest_occupied_flat_run_hours"] == 80  # 5 days x 16 occupied hours
    # Both coarser checks would have passed it
    assert stats["distinct_values"] > 1
    assert stats["degenerate_window_fraction"] == 0.0


def test_variance_gate_allows_night_setback_flatness(monkeypatch):
    # Flat overnight (setback) with real movement during occupied hours is
    # normal building behaviour and must pass.
    damper = []
    room = []
    for day in range(5):
        for h in range(24):
            damper.append(30.0 + day * 3 + h * 2 if 4 <= h < 20 else 0.0)
            room.append(18.0 + h * 0.3 + day * 0.1)
    base = datetime(2026, 6, 29, 0, tzinfo=UTC)
    rows = []
    for feature, values in {"damper_position": damper, "room_temp": room}.items():
        for hour, value in enumerate(values):
            rows.append(
                {
                    "equipment_id": "S002-VAV-001",
                    "sensor_type": feature,
                    "value": value,
                    "recorded_at": base + timedelta(hours=hour),
                }
            )
    loader = _patched_loader(monkeypatch, rows, ["damper_position", "room_temp"])

    df = loader.load_equipment_type_dataframe("vav", min_hours=2, required_features=["damper_position", "room_temp"])

    assert df is not None
    assert loader.last_load_metadata["variance_gate"]["passed"] is True
    stats = loader.last_load_metadata["feature_stats"]["damper_position"]
    assert stats["degenerate"] is False
    assert stats["degenerate_occupied_window_fraction"] == 0.0


def test_variance_gate_stricter_for_dead_business_days(monkeypatch):
    # Dead on 2 of 5 business days (0.4): passes the full-day majority rule
    # but exceeds the stricter occupied-hours floor (0.3) — at learning time
    # a channel broken ~40% of business days poisons the baseline.
    damper = []
    supply = []
    for day in range(5):
        for h in range(24):
            damper.append(100.0 if day in (1, 3) else 50.0 + h * 2 + day)
            supply.append(18.0 + h * 0.3 + day * 0.1)
    base = datetime(2026, 6, 29, 0, tzinfo=UTC)  # Monday
    rows = _rows_for({"supply_air_temp": supply, "damper_position": damper}, base=base)
    loader = _patched_loader(monkeypatch, rows, ["supply_air_temp", "damper_position"])

    df = loader.load_equipment_type_dataframe(
        "ahu", min_hours=2, required_features=["supply_air_temp", "damper_position"]
    )

    assert df is None
    stats = loader.last_load_metadata["feature_stats"]["damper_position"]
    assert stats["degenerate_reason"] == "occupied_hours_pinned"
    assert stats["degenerate_window_fraction"] == 0.4  # under the 0.5 full-day rule
    assert stats["degenerate_occupied_window_fraction"] == 0.4  # over the 0.3 occupied rule


def test_variance_gate_uses_site_configured_operating_hours(monkeypatch):
    # Wizard/settings hours (07:00-18:00 SAST = 05:00-16:00 UTC, weekend closed)
    # override the heuristic. Channel pinned exactly during configured business
    # hours, varying outside them: under the wider heuristic window the varying
    # edge hours would dilute the segment below the floor — only the configured
    # hours catch it.
    flow = []
    supply = []
    for day in range(5):
        for h in range(24):
            flow.append(500.0 if 5 <= h < 16 else 300.0 + day * 7 + h * 3)
            supply.append(18.0 + h * 0.3 + day * 0.1)
    base = datetime(2026, 6, 29, 0, tzinfo=UTC)  # Monday
    rows = _rows_for({"supply_air_temp": supply, "flow_lpm": flow}, base=base)
    loader = _patched_loader(monkeypatch, rows, ["supply_air_temp", "flow_lpm"])
    monkeypatch.setattr(loader, "_load_site_operating_hours", lambda: {"weekday": "07:00-18:00", "weekend": "closed"})

    df = loader.load_equipment_type_dataframe("ahu", min_hours=2, required_features=["supply_air_temp", "flow_lpm"])

    assert df is None
    gate = loader.last_load_metadata["variance_gate"]
    assert gate["degenerate_features"] == ["flow_lpm"]
    assert "operating_hours" in gate["occupancy_source"]
    stats = loader.last_load_metadata["feature_stats"]["flow_lpm"]
    assert stats["degenerate_reason"] == "occupied_hours_pinned"
    assert stats["degenerate_occupied_window_fraction"] == 1.0
