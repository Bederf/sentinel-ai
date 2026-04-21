"""Tests for SentinelMLFeeder — site_aggregate wiring and derived features."""

from datetime import datetime

from app.services.sentinel_ml_feeder import SENSOR_MAPPING, SentinelMLFeeder


class TestSiteAggregateWiring:
    """Fix 1 + 2: site_aggregate type and SENSOR_MAPPING entry."""

    def test_site_aggregate_in_sensor_mapping(self):
        """site_aggregate must be present in SENSOR_MAPPING."""
        assert "site_aggregate" in SENSOR_MAPPING

    def test_site_aggregate_has_lighting_kw(self):
        """lighting_kw must be in the site_aggregate mapping."""
        mapping = SENSOR_MAPPING["site_aggregate"]
        assert "lighting_kw" in mapping

    def test_site_aggregate_has_hvac_kw(self):
        mapping = SENSOR_MAPPING["site_aggregate"]
        assert "hvac_kw" in mapping

    def test_site_aggregate_has_total_kw(self):
        mapping = SENSOR_MAPPING["site_aggregate"]
        assert "total_kw" in mapping

    def test_site_aggregate_has_derived_features(self):
        """hvac_ratio, lighting_ratio, non_hvac_kw must be mapped."""
        mapping = SENSOR_MAPPING["site_aggregate"]
        assert "hvac_ratio" in mapping
        assert "lighting_ratio" in mapping
        assert "non_hvac_kw" in mapping

    def test_chiller_mapping_excludes_lighting_kw(self):
        """lighting_kw must NOT be in the chiller mapping — semantic correctness."""
        chiller = SENSOR_MAPPING.get("chiller", {})
        assert "lighting_kw" not in chiller

    def test_lighting_kw_not_in_any_other_mapping(self):
        """lighting_kw should only exist in site_aggregate, nowhere else."""
        for equip_type, mapping in SENSOR_MAPPING.items():
            if "lighting_kw" in mapping:
                assert equip_type == "site_aggregate", (
                    f"lighting_kw found in {equip_type} mapping — only site_aggregate is correct"
                )


class TestSiteAggregateIngest:
    """Fix 2 + 4: ingest populates buffers and derives ratios."""

    def test_lighting_kw_reaches_ml_buffer_via_site_aggregate(self):
        """lighting_kw from S002-CHILLER-AGG with type=site_aggregate reaches ML buffer."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-CHILLER-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "lighting_kw": 12.5,
                    "hvac_kw": 80.0,
                    "total_kw": 100.0,
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        assert "lighting_kw" in buf, f"buffer keys: {list(buf.keys())}"
        assert buf["lighting_kw"][-1] == 12.5

    def test_site_aggregate_catch_all_stores_all_readings(self):
        """When site_aggregate is in SENSOR_MAPPING, no readings are discarded."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-CHILLER-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "lighting_kw": 10.0,
                    "hvac_kw": 75.0,
                    "total_kw": 90.0,
                    "flow_lpm": 450.0,
                    "pressure_bar": 2.1,
                    "zone_count": 18.0,
                    "equip_online": 17.0,
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        for key in ["lighting_kw", "hvac_kw", "total_kw", "flow_lpm", "pressure_bar", "zone_count", "equip_online"]:
            assert key in buf, f"{key} missing from buffer: {list(buf.keys())}"
            assert len(buf[key]) > 0, f"{key} buffer is empty"

    def test_derived_lighting_ratio_computed_at_ingest(self):
        """lighting_ratio = lighting_kw / total_kw computed at ingest time."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-CHILLER-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "lighting_kw": 15.0,
                    "hvac_kw": 75.0,
                    "total_kw": 100.0,
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        assert "lighting_ratio" in buf, f"buffer keys: {list(buf.keys())}"
        assert buf["lighting_ratio"][-1] == 0.15  # 15/100

    def test_derived_hvac_ratio_computed_at_ingest(self):
        """hvac_ratio = hvac_kw / total_kw computed at ingest time."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-CHILLER-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "lighting_kw": 15.0,
                    "hvac_kw": 75.0,
                    "total_kw": 100.0,
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        assert "hvac_ratio" in buf
        assert buf["hvac_ratio"][-1] == 0.75  # 75/100

    def test_derived_non_hvac_kw_computed_at_ingest(self):
        """non_hvac_kw = total_kw - hvac_kw - lighting_kw computed at ingest."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-CHILLER-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "lighting_kw": 15.0,
                    "hvac_kw": 75.0,
                    "total_kw": 100.0,
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        assert "non_hvac_kw" in buf
        assert buf["non_hvac_kw"][-1] == 10.0  # 100 - 75 - 15

    def test_derived_ratios_zero_when_total_is_zero(self):
        """Must not divide by zero — derive nothing when total_kw is 0."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-CHILLER-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "lighting_kw": 0.0,
                    "hvac_kw": 0.0,
                    "total_kw": 0.0,
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        # Ratios must not be appended when total_kw is 0
        assert "lighting_ratio" not in buf or len(buf["lighting_ratio"]) == 0 or buf["lighting_ratio"][-1] == 0.0
        assert "hvac_ratio" not in buf or len(buf["hvac_ratio"]) == 0 or buf["hvac_ratio"][-1] == 0.0
        # non_hvac_kw should be 0 (not negative)
        assert "non_hvac_kw" not in buf or buf["non_hvac_kw"][-1] >= 0

    def test_ratio_derived_when_only_partial_readings_available(self):
        """If hvac_kw is missing but lighting_kw and total_kw are present, lighting_ratio still computed."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-CHILLER-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "lighting_kw": 20.0,
                    "total_kw": 100.0,
                    # hvac_kw missing
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        # lighting_ratio should still be computed
        assert buf["lighting_ratio"][-1] == 0.2
        # hvac_ratio skipped (hvac_kw is None)
        assert len(buf.get("hvac_ratio", [])) == 0

    def test_multiple_ingest_cycles_accumulate(self):
        """Multiple calls to ingest() should accumulate readings in buffers."""
        feeder = SentinelMLFeeder()
        for i in range(5):
            equipment_states = {
                "S002-CHILLER-AGG": {
                    "type": "site_aggregate",
                    "sensor_readings": {
                        "lighting_kw": float(i * 5),
                        "hvac_kw": float(50 + i * 5),
                        "total_kw": 100.0,
                    },
                }
            }
            feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        assert len(buf["lighting_kw"]) == 5
        assert len(buf["lighting_ratio"]) == 5
        assert buf["lighting_ratio"][-1] == 0.2  # 20/100

    def test_code_to_type_populated_for_site_aggregate(self):
        """_code_to_type maps equipment code to site_aggregate."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-CHILLER-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {"lighting_kw": 10.0},
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        assert feeder._code_to_type["S002-CHILLER-AGG"] == "site_aggregate"


class TestSiteAggregateOccupancy:
    """Fix 3: occupancy wired via security_occupancy_service into site_aggregate."""

    def test_occupancy_readings_reach_ml_buffer(self):
        """total_occupancy, occupied_zones, peak_zone_density reach ML buffer."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-SITE-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "lighting_kw": 10.0,
                    "hvac_kw": 75.0,
                    "total_kw": 90.0,
                    "total_occupancy": 42.0,
                    "occupied_zones": 15.0,
                    "peak_zone_density": 8.0,
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        assert buf["total_occupancy"][-1] == 42.0
        assert buf["occupied_zones"][-1] == 15.0
        assert buf["peak_zone_density"][-1] == 8.0

    def test_occupancy_partial_readings_accepted(self):
        """If only total_occupancy is available, it still reaches buffer."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-SITE-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "total_occupancy": 30.0,
                    # occupied_zones and peak_zone_density missing
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        assert buf["total_occupancy"][-1] == 30.0

    def test_occupancy_zero_is_valid(self):
        """Occupancy of 0 (zone empty) must be stored, not treated as missing."""
        feeder = SentinelMLFeeder()
        equipment_states = {
            "S002-SITE-AGG": {
                "type": "site_aggregate",
                "sensor_readings": {
                    "total_occupancy": 0.0,
                    "occupied_zones": 0.0,
                    "peak_zone_density": 0.0,
                },
            }
        }
        feeder.ingest(equipment_states, datetime.utcnow())

        buf = feeder._buffers["site_aggregate"]
        assert buf["total_occupancy"][-1] == 0.0
        assert buf["occupied_zones"][-1] == 0.0
        assert buf["peak_zone_density"][-1] == 0.0


class TestSiteAggregateTypeNotInChillerMapping:
    """Fix 1 — chiller mapping must not include lighting_kw."""

    def test_chiller_mapping_has_no_lighting_kw(self):
        """Explicit: chiller mapping keys must not include lighting_kw."""
        keys = list(SENSOR_MAPPING.get("chiller", {}).keys())
        assert "lighting_kw" not in keys

    def test_chiller_mapping_has_no_site_aggregate_readings(self):
        """site_aggregate readings (flow_lpm, pressure_bar) must not be in chiller mapping."""
        keys = list(SENSOR_MAPPING.get("chiller", {}).keys())
        assert "flow_lpm" not in keys
        assert "pressure_bar" not in keys
        assert "zone_count" not in keys
