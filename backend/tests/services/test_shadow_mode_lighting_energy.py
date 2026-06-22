from datetime import UTC, datetime

from app.services.shadow_mode_polling import (
    _is_dali_lighting_mapping,
    _lighting_energy_payload_from_state,
)


def test_dali_lighting_mapping_accepts_measured_lighting_points():
    assert _is_dali_lighting_mapping(
        {
            "extracted_asset_id": "S002-DALI-101",
            "parameter_name": "power_watts",
        }
    )
    assert _is_dali_lighting_mapping(
        {
            "extracted_asset_id": "S002-DALI-101",
            "parameter_name": "brightness",
        }
    )


def test_dali_lighting_mapping_rejects_config_points():
    assert not _is_dali_lighting_mapping(
        {
            "extracted_asset_id": "S002-DALI-101",
            "parameter_name": "firmware_version",
        }
    )


def test_lighting_energy_payload_uses_canonical_site_and_zone():
    observed_at = datetime(2026, 6, 21, 21, 30, tzinfo=UTC)

    payload = _lighting_energy_payload_from_state(
        site_id="site-002",
        equipment_id="S002-DALI-101",
        zone_id="Zone-101",
        readings={"power_watts": 42.5, "brightness": 65},
        observed_at=observed_at,
    )

    assert payload == {
        "time": observed_at.isoformat(),
        "controller_id": "S002-DALI-101",
        "zone_id": "Zone-101",
        "total_watts": 42.5,
        "active_luminaires": None,
        "avg_dim_level": 65.0,
        "site_id": "site-002",
    }


def test_lighting_energy_payload_rejects_unmapped_zone():
    payload = _lighting_energy_payload_from_state(
        site_id="site-002",
        equipment_id="S002-DALI-L1-CTR",
        zone_id="",
        readings={"power_watts": 42.5, "brightness": 65},
        observed_at=datetime(2026, 6, 21, 21, 30, tzinfo=UTC),
    )

    assert payload is None
