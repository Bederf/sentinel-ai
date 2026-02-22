"""Tests for solar configuration API endpoints."""


def test_create_solar_site_success(test_client) -> None:
    """Test successful solar site creation."""
    request_data = {
        "site_id": "S001",
        "site_name": "Test Solar Site",
        "latitude": -26.13,
        "longitude": 27.97,
        "config": {
            "plants": [
                {
                    "plant_id": "test-rooftop",
                    "name": "Rooftop Array",
                    "capacity_kwp": 100,
                    "panel_model": "Test Panel",
                    "panel_count": 250,
                }
            ],
            "inverters": {},
            "utility": "City Power",
            "tariff": "standard",
        },
    }

    response = test_client.post("/api/solar-config/sites", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["site_id"] == "S001"
    assert "message" in data


def test_validate_config_valid(test_client) -> None:
    """Test configuration validation with valid config."""
    request_data = {
        "site_id": "S002",
        "site_name": "Valid Config Site",
        "latitude": -26.13,
        "longitude": 27.97,
        "config": {
            "plants": [
                {
                    "plant_id": "valid-plant",
                    "name": "Valid Plant",
                    "capacity_kwp": 100,
                    "panel_count": 250,
                }
            ],
            "inverters": {},
        },
    }

    response = test_client.post("/api/solar-config/validate", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert len(data["errors"]) == 0


def test_validate_config_missing_plants(test_client) -> None:
    """Test validation fails when no plants specified."""
    request_data = {
        "site_id": "S003",
        "site_name": "No Plants Site",
        "latitude": -26.13,
        "longitude": 27.97,
        "config": {
            "plants": [],
            "inverters": {},
        },
    }

    response = test_client.post("/api/solar-config/validate", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0


def test_equipment_code_validation(test_client) -> None:
    """Test equipment code pattern validation."""
    # Invalid equipment code format
    request_data = {
        "site_id": "S004",
        "site_name": "Invalid Code Site",
        "latitude": -26.13,
        "longitude": 27.97,
        "config": {
            "plants": [
                {
                    "plant_id": "invalid-plant",
                    "name": "Plant with Invalid Inverter Code",
                    "capacity_kwp": 100,
                    "panel_count": 250,
                }
            ],
            "inverters": {
                "invalid-plant": [
                    {
                        "equipment_id": "INVALID",  # Wrong format
                        "manufacturer": "Test",
                        "model": "Test Model",
                        "rated_kva": 100,
                        "modbus_ip": "192.168.1.1",
                    }
                ]
            },
        },
    }

    response = test_client.post("/api/solar-config/validate", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("Invalid equipment code" in error for error in data["errors"])


def test_inverter_coverage_warning(test_client) -> None:
    """Test inverter coverage validation warning."""
    # Inverter coverage < 80%
    request_data = {
        "site_id": "S005",
        "site_name": "Low Coverage Site",
        "latitude": -26.13,
        "longitude": 27.97,
        "config": {
            "plants": [
                {
                    "plant_id": "low-coverage",
                    "name": "Low Coverage Plant",
                    "capacity_kwp": 100,
                    "panel_count": 250,
                }
            ],
            "inverters": {
                "low-coverage": [
                    {
                        "equipment_id": "S005-INV-R-001",
                        "manufacturer": "Huawei",
                        "model": "SUN2000",
                        "rated_kva": 50,  # Only 50% coverage
                        "modbus_ip": "192.168.1.1",
                    }
                ]
            },
        },
    }

    response = test_client.post("/api/solar-config/validate", json=request_data)
    assert response.status_code == 200
    data = response.json()
    # Should have a warning about coverage
    assert any("coverage" in error.lower() for error in data["errors"])


def test_create_solar_site_with_bess(test_client) -> None:
    """Test solar site creation with BESS configuration."""
    request_data = {
        "site_id": "S006",
        "site_name": "Site with BESS",
        "latitude": -26.13,
        "longitude": 27.97,
        "config": {
            "plants": [
                {
                    "plant_id": "with-bess",
                    "name": "Plant with BESS",
                    "capacity_kwp": 100,
                    "panel_count": 250,
                }
            ],
            "inverters": {},
            "bess": {
                "equipment_id": "S006-BESS-B1-001",
                "manufacturer": "Tesla",
                "model": "Powerwall",
                "capacity_kwh": 1000,
                "rated_power_kw": 500,
                "modbus_ip": "192.168.1.200",
            },
        },
    }

    response = test_client.post("/api/solar-config/sites", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_create_solar_site_with_grid_meter(test_client) -> None:
    """Test solar site creation with grid meter."""
    request_data = {
        "site_id": "S007",
        "site_name": "Site with Grid Meter",
        "latitude": -26.13,
        "longitude": 27.97,
        "config": {
            "plants": [
                {
                    "plant_id": "with-meter",
                    "name": "Plant with Meter",
                    "capacity_kwp": 100,
                    "panel_count": 250,
                }
            ],
            "inverters": {},
            "grid_meter": {
                "equipment_id": "S007-MTR-R-GRID",
                "manufacturer": "Siemens",
                "modbus_ip": "192.168.1.201",
            },
        },
    }

    response = test_client.post("/api/solar-config/sites", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_create_solar_site_multiple_plants(test_client) -> None:
    """Test solar site creation with multiple plants."""
    request_data = {
        "site_id": "S008",
        "site_name": "Multi-Plant Site",
        "latitude": -26.13,
        "longitude": 27.97,
        "config": {
            "plants": [
                {
                    "plant_id": "carport-east",
                    "name": "East Carport",
                    "capacity_kwp": 300,
                    "panel_count": 750,
                },
                {
                    "plant_id": "carport-west",
                    "name": "West Carport",
                    "capacity_kwp": 300,
                    "panel_count": 750,
                },
            ],
            "inverters": {},
        },
    }

    response = test_client.post("/api/solar-config/sites", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_invalid_gps_coordinates(test_client) -> None:
    """Test validation fails for invalid GPS coordinates."""
    request_data = {
        "site_id": "S009",
        "site_name": "Invalid GPS Site",
        "latitude": 95,  # Invalid latitude
        "longitude": 27.97,
        "config": {
            "plants": [
                {
                    "plant_id": "invalid-gps",
                    "name": "Invalid GPS Plant",
                    "capacity_kwp": 100,
                    "panel_count": 250,
                }
            ],
            "inverters": {},
        },
    }

    response = test_client.post("/api/solar-config/validate", json=request_data)
    assert response.status_code == 422  # Validation error from Pydantic


def test_equipment_code_pattern_valid(test_client) -> None:
    """Test valid equipment code patterns."""
    valid_codes = [
        "S002-INV-R-001",
        "S010-BESS-B1-001",
        "S005-MTR-R-GRID",
        "S001-INV-G-005",
    ]

    for code in valid_codes:
        request_data = {
            "site_id": f"S{code[1:4]}",
            "site_name": f"Test {code}",
            "latitude": -26.13,
            "longitude": 27.97,
            "config": {
                "plants": [
                    {
                        "plant_id": f"plant-{code}",
                        "name": f"Plant {code}",
                        "capacity_kwp": 100,
                        "panel_count": 250,
                    }
                ],
                "inverters": {
                    f"plant-{code}": [
                        {
                            "equipment_id": code,
                            "manufacturer": "Test",
                            "model": "Test",
                            "rated_kva": 100,
                            "modbus_ip": "192.168.1.1",
                        }
                    ]
                    if "INV" in code
                    else [],
                },
            },
        }

        response = test_client.post("/api/solar-config/validate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        # Valid code should not produce format errors
        assert not any("Invalid equipment code" in error for error in data["errors"])


def test_equipment_code_pattern_invalid(test_client) -> None:
    """Test invalid equipment code patterns are rejected."""
    invalid_codes = [
        "INV-001",  # Missing site prefix
        "S2-INV-R-001",  # Site code too short
        "S002-inverter-R-001",  # Lowercase type
        "S002-INV-ROOF-001",  # Location too long
        "S002-INV",  # Missing location and sequence
    ]

    for code in invalid_codes:
        request_data = {
            "site_id": "S002",
            "site_name": "Invalid Code Test",
            "latitude": -26.13,
            "longitude": 27.97,
            "config": {
                "plants": [
                    {
                        "plant_id": "test-plant",
                        "name": "Test Plant",
                        "capacity_kwp": 100,
                        "panel_count": 250,
                    }
                ],
                "inverters": {
                    "test-plant": [
                        {
                            "equipment_id": code,
                            "manufacturer": "Test",
                            "model": "Test",
                            "rated_kva": 100,
                            "modbus_ip": "192.168.1.1",
                        }
                    ]
                },
            },
        }

        response = test_client.post("/api/solar-config/validate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        # Invalid code should produce format error
        assert data["valid"] is False or any("Invalid equipment code" in error for error in data["errors"])
