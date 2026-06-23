---
title: "SENTINEL → iDNa BDP Schema Definition"
type: "architecture"
status: "draft"
version: "1.1.0"
created: "2026-04-16"
updated: "2026-04-16"
author: "SENTINEL Architecture Office"
tags: ["idna", "bdp", "simbiot", "schema", "data-engineering", "migration", "ai-labs", "azure-openai"]
domain: "data-platform"
audience: ["iDNa Data Engineers", "SDP/AbInitio Team", "SENTINEL Architecture Office"]
complexity: "intermediate"
estimated_read_time: 30
related: ["SIMBIOT Universal Adapter Pattern", "Module Registry", "Naming Conventions"]
---

# SENTINEL → iDNa BDP Schema Definition

**Purpose:** This document defines the canonical SENTINEL data schema as consumed by the SIMBIOT BMS adapter layer and presented to iDNa Data Engineers for BDP Reservoir onboarding. It is the authoritative reference for all table definitions, column types, naming conventions, and BDP Landing Zone folder structure.

**Schema Owner:** SENTINEL Architecture Office
**BDP Landing Zone:** `sentinel/{domain}/{site_id}/{yyyy}/{mm}/{dd}/`
**Status:** Awaiting iDNa SDP flow provisioning

---

## 1. Design Principles

1. **Fixed schema, adaptive ingestion.** SENTINEL's BDP schema never changes per building. SIMBIOT adapts any BMS format (BACnet/IP, Modbus TCP, oBIX, Fox, CSV) to the canonical schema — no per-site schema variation.
2. **Site isolation.** All tables include `site_id` or `building_id`. Multi-site queries are explicit; cross-site aggregation requires explicit fan-out.
3. **Naming as architecture.** Equipment codes encode site, type, and canonical zone or plant location. Occupied zone = `{site}-{type}-{zone_id}`. Basement/roof plant = `{site}-{type}-{loc}-{seq}`. Raw BMS/vendor names are preserved separately as provenance.
4. **Immutable provenance.** Raw source records are frozen at ingestion. Canonical points carry full provenance chain from BMS device to BDP record.
5. **Safety-classified points.** Every point carries a `safety_class` (CRITICAL / HIGH / MEDIUM / LOW) that gates write-back authority in supervised/auto modes.

---

## 2. Site and Equipment Naming

### 2.1 Site Codes

| Field | Format | Example |
|-------|--------|---------|
| `buildings.code` | `site-{###}` | `site-002` |
| Equipment prefix | `S{###}-` | `S002-` |
| Fairland Campus | `site-002` / `S002` | — |

### 2.2 Equipment Naming Pattern

**Zones** (per-zone equipment — FCU, VAV, luminaires, sensors):
```
{site}-{type}-{zone_id}
```
Examples: `S005-AHU-003`, `S002-FCU-100`, `S002-VAV-204`, `S005-DALI-510`

**Plants** (basement/roof plant-room equipment — chillers, generators, UPS, transformers, cooling towers):
```
{site}-{type}-{floor}-{seq}
```
Examples: `S002-CHILLER-B1-001`, `S002-GEN-B1-001`, `S002-UPS-B1-001`

Canonical zone codes are three digits: `001`-`099` = Ground/L0, `100`-`199` = L1, `200`-`299` = L2, `500`-`599` = L5. The first zone on L1 is `Zone-100`; the eleventh zone on L5 is `Zone-510`. Site-specific source labels such as `L3-ICU` or `L3-TH1` are stored as raw/source identifiers or zone aliases and mapped to canonical zones during onboarding.

Runtime compatibility note: the canonical relationship source is still `equipment_zone_relationships`, but zone records are also populated with direct equipment pointers for live read paths. In practice, both `zones` and `hvac_zones` may carry `fcu_id`, `vav_id`, `ahu_id`, and `lighting_id` as denormalized fields, and onboarding keeps them synchronized from the canonical mapping.

### 2.3 Floor Codes

| Code | Meaning |
|------|---------|
| `B1`, `B2` | Basement 1, 2 |
| `G` | Ground floor |
| `L0`–`L99` | Level 0–99 |
| `R` | Roof |

### 2.4 Equipment Type Codes

| Category | Types |
|---------|-------|
| **HVAC** | `CHILLER`, `AHU`, `FCU`, `VAV`, `SPLIT`, `CT` (cooling tower), `CRAC`, `PUMP`, `BOILER` |
| **Electrical** | `GEN`, `UPS`, `ATS`, `MSB`, `MTR`, `PFC`, `FDR`, `MV`, `TX` (transformer) |
| **Lighting** | `DALI` |
| **Fire/Security** | `FIRE`, `ACC` (access control), `CCTV`, `LIFT` |
| **Other** | `BMS`, `JACE`, `PXC`, `MEDGAS` |

---

## 3. Core Tables

### 3.1 `buildings`

Single row per site.

```sql
CREATE TABLE sentinel.core_buildings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id         TEXT UNIQUE NOT NULL,           -- 'site-002'
    name            TEXT NOT NULL,
    address         TEXT,
    region          TEXT,
    building_type   TEXT CHECK (building_type IN (
                        'branch','regional_office','data_center','retail','warehouse')),
    sqm             INTEGER,
    floors          INTEGER,
    year_built      INTEGER,
    operating_hours JSONB,                          -- {"weekday": "07:00-19:00", ...}
    occupancy_pattern TEXT,
    latitude        DECIMAL(10, 8),
    longitude        DECIMAL(11, 8),
    contact_email   TEXT,
    contact_phone   TEXT,
    optimization_enabled BOOLEAN DEFAULT FALSE,
    optimization_settings JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**Indexes:** `idx_buildings_site_id`

**Partitioning recommendation:** By `site_id`. Initial load: 1 site (Fairland / site-002). Target: 600+ sites.

---

### 3.2 `equipment`

Canonical equipment registry. One row per physical device. Populated by SIMBIOT adapter discovery.

```sql
CREATE TABLE sentinel.core_equipment (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT UNIQUE NOT NULL,           -- 'S002-CHILLER-B1-001'
    site_id         TEXT NOT NULL,                  -- FK to buildings.site_id
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,                  -- 'CHILLER', 'AHU', 'FCU', etc.
    manufacturer    TEXT,
    model           TEXT,
    capacity        TEXT,
    serial_number   TEXT,
    install_date    DATE,
    last_service    DATE,
    status          TEXT CHECK (status IN (
                        'normal','warning','critical','offline','maintenance')),
    health_score   INTEGER CHECK (health_score BETWEEN 0 AND 100),
    location        TEXT,                           -- 'Basement Level 1, Zone A'
    brick_class     TEXT,                           -- Brick ontology class, e.g. 'brick:Chiller'
    safety_class    TEXT DEFAULT 'MEDIUM' CHECK (safety_class IN (
                        'CRITICAL','HIGH','MEDIUM','LOW')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**Indexes:** `idx_equipment_site_id`, `idx_equipment_type`, `idx_equipment_status`, `idx_equipment_health`

**Partitioning:** By `site_id`.

---

### 3.3 `sensors`

Individual measurement points attached to equipment.

```sql
CREATE TABLE sentinel.core_sensors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT UNIQUE NOT NULL,           -- 'S002-CHILLER-B1-001.supply_temp'
    equipment_code  TEXT NOT NULL,                  -- FK to equipment.code
    point_name      TEXT NOT NULL,                  -- 'supply_temp'
    point_type      TEXT NOT NULL CHECK (point_type IN (
                        'analog_input','analog_output',
                        'binary_input','binary_output',
                        'multi_state')),
    category        TEXT NOT NULL CHECK (category IN (
                        'temperature','humidity','pressure','flow',
                        'energy','vibration','status','command')),
    unit            TEXT NOT NULL,                  -- '°C', 'kPa', 'kW', '%', 'ppm'
    min_value       DECIMAL(10, 2),
    max_value       DECIMAL(10, 2),
    current_value   DECIMAL(10, 2),
    brick_point     TEXT,                           -- 'brick:Supply_Chilled_Water_Temperature_Sensor'
    safety_class    TEXT DEFAULT 'MEDIUM',
    bacnet_object_type TEXT,                       -- 'analogInput', 'binaryInput', etc.
    bacnet_instance  INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**Indexes:** `idx_sensors_equipment_code`, `idx_sensors_point_type`, `idx_sensors_category`

---

### 3.4 `equipment_telemetry` (Time-Series)

High-frequency telemetry readings. Written by SIMBIOT adapter on poll cycle (5-min default).

```sql
CREATE TABLE sentinel.timeseries_equipment_telemetry (
    time            TIMESTAMPTZ NOT NULL,
    site_id         TEXT NOT NULL,
    equipment_code  TEXT NOT NULL,
    point_name      TEXT NOT NULL,
    value           DECIMAL(14, 4),
    quality         TEXT DEFAULT 'good' CHECK (quality IN ('good','uncertain','fault')),
    source          TEXT NOT NULL,                  -- 'bacnet', 'modbus', 'obix', 'simulated'
    device_id       TEXT,                           -- Original BMS device ID
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, site_id, equipment_code, point_name)
)
PARTITION BY RANGE (time);

-- Create monthly partitions
CREATE TABLE sentinel.timeseries_equipment_telemetry_y2026m04
    PARTITION OF sentinel.timeseries_equipment_telemetry
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
```

**Retention:** 30 days hot (EEH Kafka + BDP streaming layer), 5 years cold (BDP Reservoir).

---

### 3.5 `hvac_zones`

Zone-level HVAC state. One row per zone per site.

```sql
CREATE TABLE sentinel.hvac_zones (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id             TEXT UNIQUE NOT NULL,       -- 'Zone-100'
    site_id             TEXT NOT NULL,
    zone_name           TEXT NOT NULL,             -- 'Level 1 North'
    floor               TEXT NOT NULL,             -- 'L1'
    fcu_id              TEXT,
    vav_id              TEXT,
    ahu_id              TEXT,
    temp_sensor         TEXT,
    co2_sensor          TEXT,
    humidity_sensor     TEXT,
    typical_occupancy   INTEGER,
    area_sqm            INTEGER,
    priority            TEXT DEFAULT 'P3' CHECK (priority IN ('P1','P2','P3','P4','P5')),
    setpoint            DECIMAL(4,1) DEFAULT 22.0,
    heating_setpoint    DECIMAL(4,1),
    cooling_setpoint    DECIMAL(4,1),
    current_temp        DECIMAL(4,1),
    current_humidity    DECIMAL(4,1),
    current_co2         INTEGER,
    status              TEXT DEFAULT 'idle' CHECK (status IN (
                            'running','idle','heating','cooling','fault','offline')),
    mode                TEXT DEFAULT 'auto' CHECK (mode IN ('auto','heat','cool','off')),
    fan_speed           TEXT DEFAULT 'auto' CHECK (fan_speed IN (
                            'auto','low','medium','high','off')),
    last_updated        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.5.1 Zone Pointer Compatibility

Several live services still read zone equipment pointers directly from zone tables. To keep those paths stable, SENTINEL mirrors the canonical equipment relationship into the zone record itself:

- `zones.fcu_id`
- `zones.vav_id`
- `zones.ahu_id`
- `zones.lighting_id`
- `hvac_zones.fcu_id`
- `hvac_zones.vav_id`
- `hvac_zones.ahu_id`
- `hvac_zones.lighting_id`

These fields are denormalized compatibility columns, not the source of truth. The source of truth remains `equipment_zone_relationships` plus the canonical equipment records written during onboarding.

---

### 3.6 `hvac_zone_history`

Time-series zone telemetry.

```sql
CREATE TABLE sentinel.timeseries_hvac_zone_history (
    time            TIMESTAMPTZ NOT NULL,
    zone_id         TEXT NOT NULL,
    site_id         TEXT NOT NULL,
    temp            DECIMAL(4,1),
    humidity        DECIMAL(4,1),
    co2             INTEGER,
    setpoint        DECIMAL(4,1),
    status          TEXT,
    occupancy       INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, zone_id, site_id)
)
PARTITION BY RANGE (time);
```

---

## 4. Alerts, Predictions, Work Orders

### 4.1 `alerts`

```sql
CREATE TABLE sentinel.ops_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id         TEXT NOT NULL,
    equipment_code  TEXT,
    alert_type      TEXT NOT NULL,
    severity        TEXT CHECK (severity IN ('info','warning','critical')),
    status          TEXT CHECK (status IN ('active','acknowledged','resolved')),
    title           TEXT NOT NULL,
    message         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT,
    resolved_at     TIMESTAMPTZ
);
```

**Indexes:** `idx_alerts_site_status`, `idx_alerts_severity`, `idx_alerts_created`

---

### 4.2 `predictions`

ML-generated failure predictions.

```sql
CREATE TABLE sentinel.ops_predictions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                    TEXT UNIQUE NOT NULL,
    site_id                 TEXT NOT NULL,
    equipment_code          TEXT NOT NULL,
    prediction_type         TEXT NOT NULL,
    probability_percent     INTEGER CHECK (probability_percent BETWEEN 0 AND 100),
    confidence              TEXT CHECK (confidence IN ('high','medium','low')),
    predicted_failure_date  DATE,
    timeframe_days          INTEGER,
    evidence                JSONB NOT NULL,
    contributing_factors    JSONB,
    similar_failures        JSONB,
    repair_cost_zar        DECIMAL(12, 2),
    replacement_cost_zar    DECIMAL(12, 2),
    downtime_cost_per_hour_zar DECIMAL(12, 2),
    potential_loss_zar      DECIMAL(12, 2),
    severity               TEXT CHECK (severity IN ('critical','high','medium','low')),
    recommended_action      TEXT,
    parts_required          TEXT[],
    urgency                 TEXT,
    status                  TEXT CHECK (status IN (
                            'active','acknowledged','resolved','false_positive')),
    created_at              TIMESTAMPTZ DEFAULT NOW()
);
```

---

### 4.3 `work_orders`

```sql
CREATE TABLE sentinel.ops_work_orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                TEXT UNIQUE NOT NULL,           -- 'WO-2026-0001'
    site_id             TEXT NOT NULL,
    equipment_code     TEXT,
    prediction_id       UUID,
    title               TEXT NOT NULL,
    description         TEXT,
    priority            TEXT CHECK (priority IN ('low','medium','high','urgent')),
    status              TEXT CHECK (status IN (
                        'draft','scheduled','in_progress','completed','cancelled')),
    scheduled_date     DATE,
    scheduled_start     TIME,
    scheduled_end       TIME,
    estimated_duration_hours INTEGER,
    assigned_to         TEXT,
    assigned_team      TEXT,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    actual_duration_hours INTEGER,
    labor_cost_zar     DECIMAL(10, 2),
    parts_cost_zar      DECIMAL(10, 2),
    total_cost_zar      DECIMAL(10, 2),
    parts_required      TEXT[],
    parts_used          JSONB,
    work_performed      TEXT,
    findings            TEXT,
    follow_up_required  BOOLEAN DEFAULT FALSE,
    parent_work_order_id UUID,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    created_by          TEXT
);
```

**Indexes:** `idx_work_orders_site_status`, `idx_work_orders_scheduled`, `idx_work_orders_assigned`

---

## 5. Solar & BESS Tables

All solar/energy data uses text IDs (`site_id`, `plant_id`, `inverter_id`, `bess_id`) for manufacturer compatibility.

### 5.1 `solar_sites`

```sql
CREATE TABLE sentinel.energy_solar_sites (
    site_id         TEXT PRIMARY KEY,
    site_name       TEXT NOT NULL,
    latitude        NUMERIC,
    longitude       NUMERIC,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

### 5.2 `solar_plants`

```sql
CREATE TABLE sentinel.energy_solar_plants (
    plant_id            TEXT PRIMARY KEY,
    site_id             TEXT NOT NULL REFERENCES sentinel.energy_solar_sites(site_id),
    name                TEXT NOT NULL,
    capacity_kwp        NUMERIC,
    panel_count         INTEGER,
    panel_model         TEXT,
    panel_rating_w      NUMERIC,
    commissioning_date   DATE,
    orientation         NUMERIC,                        -- degrees from north
    tilt               NUMERIC                         -- degrees from horizontal
);
```

---

### 5.3 `solar_inverters`

```sql
CREATE TABLE sentinel.energy_solar_inverters (
    inverter_id      TEXT PRIMARY KEY,
    site_id         TEXT NOT NULL,
    plant_id       TEXT NOT NULL,
    name           TEXT NOT NULL,
    manufacturer   TEXT,
    model          TEXT,
    rated_kva      NUMERIC,
    mppt_count     INTEGER,
    protocol       TEXT DEFAULT 'modbus_tcp',
    ip             INET,
    port           INTEGER,
    unit_id        INTEGER,
    strings_per_mppt INTEGER,
    panels_per_string INTEGER
);
```

**Indexes:** `idx_inverters_site`, `idx_inverters_plant`

---

### 5.4 `solar_bess`

```sql
CREATE TABLE sentinel.energy_solar_bess (
    bess_id         TEXT PRIMARY KEY,
    site_id         TEXT NOT NULL,
    container_id    TEXT,
    name            TEXT NOT NULL,
    manufacturer    TEXT DEFAULT 'Huawei',
    model           TEXT DEFAULT 'LUNA2000',
    capacity_kwh   NUMERIC,
    rated_power_kw  NUMERIC,
    rack_count      INTEGER,
    cell_chemistry  TEXT,
    protocol        TEXT DEFAULT 'modbus_tcp'
);
```

---

### 5.5 `solar_meters`

```sql
CREATE TABLE sentinel.energy_solar_meters (
    meter_id        TEXT PRIMARY KEY,
    site_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    manufacturer    TEXT,
    model           TEXT,
    protocol        TEXT,
    ip              INET,
    port            INTEGER
);
```

---

### 5.6 `solar_hourly_snapshots`

Annual simulation output — 8,760 rows per scenario per year.

```sql
CREATE TABLE sentinel.energy_solar_hourly_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id             TEXT NOT NULL,
    scenario            TEXT NOT NULL DEFAULT 'actual',
    year                INTEGER NOT NULL,
    hour                INTEGER NOT NULL CHECK (hour >= 0 AND hour < 8760),
    date                DATE NOT NULL,
    month               INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    day_of_year         INTEGER NOT NULL CHECK (day_of_year >= 1 AND day_of_year <= 366),
    hour_of_day         INTEGER NOT NULL CHECK (hour_of_day >= 0 AND hour_of_day <= 23),
    solar_gen_kw        FLOAT NOT NULL DEFAULT 0,
    building_load_kw     FLOAT NOT NULL DEFAULT 0,
    bess_soc_pct        FLOAT NOT NULL DEFAULT 50,
    bess_charge_kw      FLOAT NOT NULL DEFAULT 0,
    bess_discharge_kw    FLOAT NOT NULL DEFAULT 0,
    grid_import_kw      FLOAT NOT NULL DEFAULT 0,
    grid_export_kw       FLOAT NOT NULL DEFAULT 0,
    tariff_band          TEXT NOT NULL DEFAULT 'standard',
    tariff_rate_c_kwh   FLOAT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (site_id, scenario, year, hour)
);
```

---

### 5.7 `solar_daily_aggregates`

```sql
CREATE TABLE sentinel.energy_solar_daily_aggregates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id             TEXT NOT NULL,
    scenario            TEXT NOT NULL DEFAULT 'actual',
    year                INTEGER NOT NULL,
    date                DATE NOT NULL,
    month               INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    day_of_year         INTEGER NOT NULL CHECK (day_of_year >= 1 AND day_of_year <= 366),
    solar_gen_kwh       FLOAT NOT NULL DEFAULT 0,
    building_load_kwh   FLOAT NOT NULL DEFAULT 0,
    bess_charge_kwh    FLOAT NOT NULL DEFAULT 0,
    bess_discharge_kwh  FLOAT NOT NULL DEFAULT 0,
    grid_import_kwh     FLOAT NOT NULL DEFAULT 0,
    grid_export_kwh     FLOAT NOT NULL DEFAULT 0,
    peak_generation_kw  FLOAT NOT NULL DEFAULT 0,
    avg_bess_soc_pct    FLOAT NOT NULL DEFAULT 50,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (site_id, scenario, year, date)
);
```

---

## 6. Energy & Electrical

### 6.1 `energy_consumption_history`

```sql
CREATE TABLE sentinel.energy_consumption_history (
    id              BIGSERIAL PRIMARY KEY,
    site_id         TEXT NOT NULL,
    date            DATE NOT NULL,
    hvac_kwh        NUMERIC(10,2) NOT NULL DEFAULT 0,
    lighting_kwh    NUMERIC(10,2) NOT NULL DEFAULT 0,
    other_kwh       NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_kwh       NUMERIC(10,2) NOT NULL GENERATED ALWAYS AS (
                        hvac_kwh + lighting_kwh + other_kwh) STORED,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (site_id, date)
);
```

---

### 6.2 `power_meter_validations`

Daily meter validation against statistical baseline.

```sql
CREATE TABLE sentinel.energy_power_meter_validations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id             TEXT NOT NULL,
    meter_id            TEXT NOT NULL,
    validation_date     DATE NOT NULL,
    hour                INTEGER,
    reading_kwh         NUMERIC(10,2),
    baseline_mean       NUMERIC(10,2),
    baseline_stdev      NUMERIC(10,2),
    variance_pct        NUMERIC(6,2),
    validation_status   TEXT NOT NULL DEFAULT 'normal',
    severity            TEXT NOT NULL DEFAULT 'normal',
    cop_current         NUMERIC(4,2),
    cop_design          NUMERIC(4,2) DEFAULT 3.5,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (site_id, meter_id, validation_date, hour)
);
```

---

## 7. Lighting & DALI-2

### 7.1 `dali_controllers`

```sql
CREATE TABLE sentinel.lighting_dali_controllers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    controller_id       TEXT UNIQUE NOT NULL,       -- 'S002-DALI-101'
    site_id             TEXT NOT NULL,
    name                TEXT NOT NULL,
    location            TEXT NOT NULL,
    ip_address          INET,
    bacnet_device_id    INTEGER,
    channels            INTEGER DEFAULT 3,
    firmware_version    TEXT,
    status              TEXT DEFAULT 'online' CHECK (status IN ('online','offline','degraded')),
    last_seen           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

---

### 7.2 `dali_luminaires`

```sql
CREATE TABLE sentinel.lighting_dali_luminaires (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    controller_id       UUID NOT NULL REFERENCES sentinel.lighting_dali_controllers(id),
    luminaire_id        TEXT UNIQUE NOT NULL,       -- 'S002-LUM-101'
    dali_address        INTEGER NOT NULL CHECK (dali_address BETWEEN 0 AND 63),
    channel             INTEGER NOT NULL CHECK (channel BETWEEN 1 AND 3),
    name                TEXT,
    location            TEXT,
    zone_id             TEXT NOT NULL,
    wattage             INTEGER,
    current_level       INTEGER DEFAULT 0 CHECK (current_level BETWEEN 0 AND 100),
    power_consumption   REAL DEFAULT 0.0,
    operating_hours    INTEGER DEFAULT 0,
    fault_status        BOOLEAN DEFAULT FALSE,
    last_updated        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

---

### 7.3 `dali_sensors`

```sql
CREATE TABLE sentinel.lighting_dali_sensors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    controller_id       UUID NOT NULL REFERENCES sentinel.lighting_dali_controllers(id),
    sensor_id           TEXT UNIQUE NOT NULL,       -- 'S002-PIR-L12-025'
    dali_address        INTEGER NOT NULL CHECK (dali_address BETWEEN 0 AND 63),
    channel             INTEGER NOT NULL,
    location            TEXT,
    zone_id             TEXT NOT NULL,
    desk_id             TEXT,
    has_pir             BOOLEAN DEFAULT TRUE,
    has_daylight        BOOLEAN DEFAULT TRUE,
    occupancy           BOOLEAN DEFAULT FALSE,
    lux_level           REAL DEFAULT 0.0 CHECK (lux_level BETWEEN 0 AND 2000),
    fault_status        BOOLEAN DEFAULT FALSE,
    last_updated        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

---

### 7.4 `occupancy_history`

```sql
CREATE TABLE sentinel.lighting_occupancy_history (
    time            TIMESTAMPTZ NOT NULL,
    sensor_id       TEXT NOT NULL,
    zone_id         TEXT NOT NULL,
    occupied        BOOLEAN NOT NULL,
    lux_level       REAL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (time, sensor_id)
)
PARTITION BY RANGE (time);
```

---

## 8. Service Records & Maintenance

### 8.1 `service_records`

```sql
CREATE TABLE sentinel.maintenance_service_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                TEXT UNIQUE NOT NULL,           -- 'SR-2026-001234'
    work_order_id       UUID,
    site_id             TEXT NOT NULL,
    equipment_code      TEXT NOT NULL,
    service_type        TEXT CHECK (service_type IN (
                            'minor','major','breakdown','callout')),
    technician_id       TEXT NOT NULL,
    technician_name     TEXT NOT NULL,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    status              TEXT CHECK (status IN (
                            'notified','in_progress','data_collection','complete','closed'))
                            DEFAULT 'notified',
    telegram_chat_id    TEXT,
    telegram_message_id TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 9. Asset Health

### 9.1 `asset_health_snapshots`

```sql
CREATE TABLE sentinel.health_asset_health_snapshots (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id                 TEXT NOT NULL,
    equipment_code          TEXT NOT NULL,
    snapshot_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    health_score           NUMERIC(5,1) NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    health_status          TEXT NOT NULL CHECK (health_status IN (
                            'healthy','warning','critical')),
    assessment_state       TEXT NOT NULL DEFAULT 'normal' CHECK (assessment_state IN (
                            'normal','degraded_data','insufficient_data')),
    confidence             TEXT NOT NULL DEFAULT 'high' CHECK (confidence IN (
                            'high','medium','low')),
    baseline_alignment_score    NUMERIC(5,1),
    service_compliance_score    NUMERIC(5,1),
    runtime_age_score          NUMERIC(5,1),
    fault_burden_score         NUMERIC(5,1),
    trend_momentum_score        NUMERIC(5,1),
    data_freshness_minutes     NUMERIC(10,1),
    snapshot_count_24h         INTEGER,
    valid_point_ratio         NUMERIC(5,3),
    baseline_age_days          INTEGER,
    health_source             TEXT NOT NULL DEFAULT 'calculator' CHECK (health_source IN (
                                'calculator','simulation','manual_override')),
    formula_version          TEXT NOT NULL DEFAULT 'v1',
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Indexes:** `idx_health_snapshots_equipment_time`, `idx_health_snapshots_site_time`, `idx_health_snapshots_status`

---

### 9.2 `asset_health_daily_rollups`

```sql
CREATE TABLE sentinel.health_asset_health_daily_rollups (
    site_id         TEXT NOT NULL,
    equipment_code  TEXT NOT NULL,
    date            DATE NOT NULL,
    score_min       NUMERIC(5,1),
    score_max       NUMERIC(5,1),
    score_avg       NUMERIC(5,1),
    status_mode     TEXT,
    confidence_mode TEXT,
    snapshot_count  INTEGER DEFAULT 0,
    PRIMARY KEY (site_id, equipment_code, date)
);
```

---

## 10. Document Intelligence (RAG)

### 10.1 `documents`

```sql
CREATE TABLE sentinel.ai_documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code                TEXT UNIQUE NOT NULL,
    title               TEXT NOT NULL,
    document_type       TEXT NOT NULL CHECK (document_type IN (
                        'equipment_manual','maintenance_procedure','troubleshooting_guide',
                        'failure_pattern','technical_bulletin','service_report',
                        'safety_procedure','startup_procedure','shutdown_procedure')),
    equipment_type      TEXT NOT NULL,
    manufacturer        TEXT,
    model               TEXT,
    applies_to_equipment_ids JSONB,
    source              TEXT NOT NULL CHECK (source IN (
                        'oem_manual','internal_procedure','service_history',
                        'technician_notes','manufacturer_bulletin','industry_standard')),
    source_url          TEXT,
    version             TEXT DEFAULT '1.0',
    summary             TEXT,
    page_count          INTEGER,
    keywords            TEXT[],
    failure_modes       TEXT[],
    indexing_status     TEXT CHECK (indexing_status IN (
                        'pending','chunking','embedded','failed')) DEFAULT 'pending',
    chunk_count         INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

---

### 10.2 `document_chunks`

```sql
CREATE TABLE sentinel.ai_document_chunks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES sentinel.ai_documents(id) ON DELETE CASCADE,
    chunk_index         INTEGER NOT NULL,
    content             TEXT NOT NULL,
    content_length      INTEGER NOT NULL,
    token_count         INTEGER,
    -- embedding         vector(384)          -- pgvector; BDP equivalent: FAISS or Pinecode
    section_title       TEXT,
    page_number         INTEGER,
    equipment_type      TEXT NOT NULL,
    document_type       TEXT NOT NULL,
    manufacturer       TEXT,
    model              TEXT,
    keywords            TEXT[],
    failure_modes       TEXT[],
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
```

**Note on embeddings:** BDP does not ship pgvector. Embedding storage options for iDNa:
1. **Pinecone** (if approved for internal use)
2. **Azure AI Search** (within AI Labs)
3. **BDP HDFS + FAISS** (build a small FAISS index per site)

---

## 11. Cross-Module State Tables

### 11.1 `zone_display_mappings`

Physical-to-digital zone mapping for the space intelligence module.

```sql
CREATE TABLE sentinel.space_zone_display_mappings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id             TEXT NOT NULL,
    zone_id             TEXT NOT NULL,
    display_zone_id    TEXT NOT NULL,
    display_zone_name   TEXT NOT NULL,
    floor               INTEGER NOT NULL CHECK (floor >= 0 AND floor <= 4),
    coordinates         JSONB NOT NULL,              -- {"x": 0, "y": 0, "w": 100, "h": 80}
    max_occupancy      INTEGER NOT NULL DEFAULT 10,
    zone_type           TEXT NOT NULL CHECK (zone_type IN (
                        'entry','office','meeting','common','utility','corridor')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (site_id, display_zone_id)
);
```

---

## 12. BDP Landing Zone Structure

### 12.1 Folder Hierarchy

```
sentinel/
├── core/
│   └── {site_id}/
│       └── {yyyy}/{mm}/{dd}/
│           ├── buildings.json
│           └── equipment.jsonl
├── timeseries/
│   └── {site_id}/
│       └── {yyyy}/{mm}/{dd}/
│           ├── equipment_telemetry/
│           │   └── {equipment_code}/
│           │       └── {date}.parquet
│           ├── hvac_zone_history/
│           │   └── {zone_id}/
│           │       └── {date}.parquet
│           └── occupancy_history/
│               └── {zone_id}/
│                   └── {date}.parquet
├── ops/
│   └── {site_id}/
│       └── {yyyy}/{mm}/{dd}/
│           ├── alerts.jsonl
│           ├── predictions.jsonl
│           └── work_orders.jsonl
├── energy/
│   └── {site_id}/
│       └── {yyyy}/{mm}/{dd}/
│           ├── solar_hourly_snapshots/
│           ├── solar_daily_aggregates/
│           └── consumption_history/
├── lighting/
│   └── {site_id}/
│       └── {yyyy}/{mm}/{dd}/
│           ├── occupancy_history/
│           └── luminaire_state/
├── health/
│   └── {site_id}/
│       └── {yyyy}/{mm}/{dd}/
│           └── asset_health_snapshots/
├── maintenance/
│   └── {site_id}/
│       └── {yyyy}/{mm}/{dd}/
│           └── service_records.jsonl
└── ai/
    └── {site_id}/
        └── {yyyy}/{mm}/{dd}/
            ├── documents/
            └── chunks/
```

### 12.2 File Formats

| Data Type | Format | Rationale |
|-----------|--------|-----------|
| High-frequency telemetry | Parquet | Columnar, compressed, schema evolution friendly |
| Alerts / Work Orders | JSONL | Row-based, human-readable, audit-friendly |
| Equipment registry | JSON | Rarely changes, full rewrite per sync |
| Documents | PDF + extracted text | Binary in BDP Storage, metadata in JSONL |

---

## 13. Brick Ontology Reference

All equipment maps to [Brick Schema](https://brickschema.org/) classes for cross-vendor semantic interoperability.

### 13.1 Equipment → Brick Class

| SENTINEL Type | Brick Class IRI |
|--------------|----------------|
| `chiller` | `brick:Chiller` |
| `ahu` | `brick:AHU` |
| `vav` | `brick:VAV` |
| `fcu` | `brick:Fan_Coil_Unit` |
| `pump` | `brick:Pump` |
| `generator` | `brick:Generator` |
| `ups` | `brick:UPS` |
| `cooling_tower` | `brick:Cooling_Tower` |
| `boiler` | `brick:Boiler` |
| `meter` | `brick:Electrical_Meter` |
| `dali_controller` | `brick:Lighting_Equipment` |
| `split` | `brick:CRAC` |

### 13.2 Point → Brick Point Class (examples)

| Point Name Pattern | Brick Point Class |
|-------------------|------------------|
| `chiller.supply.temperature` | `brick:Supply_Chilled_Water_Temperature_Sensor` |
| `chiller.return.temperature` | `brick:Return_Chilled_Water_Temperature_Sensor` |
| `ahu.supply.air.temperature` | `brick:Supply_Air_Temperature_Sensor` |
| `zone.air.temperature` | `brick:Zone_Air_Temperature_Sensor` |

### 13.3 Generic Point Classification Heuristics

When explicit mapping is absent:

| Name/Unit Pattern | Brick Class |
|------------------|-------------|
| `temp`, `degC`, `°C` | `brick:Temperature_Sensor` |
| `pressure`, `kPa`, `psi` | `brick:Pressure_Sensor` |
| `flow`, `l/s`, `m3/h` | `brick:Flow_Sensor` |
| `speed`, `Hz`, `rpm` | `brick:Speed_Sensor` |
| `cmd`, `command` | `brick:Command` |
| `status` | `brick:Status` |
| (default) | `brick:Point` |

---

## 14. BACnet Point Type Mapping

All BACnet object types map to five canonical point types used throughout SENTINEL:

| BACnet Object Type | SENTINEL Canonical Type | Direction |
|-------------------|------------------------|-----------|
| `analogInput` | `analog_input` | Read-only sensor |
| `analogOutput` | `analog_output` | Writable setpoint/command |
| `analogValue` | `analog_input` | Read-only computed value |
| `binaryInput` | `binary_input` | Read-only status/alarm |
| `binaryOutput` | `binary_output` | Writable binary command |
| `binaryValue` | `binary_input` | Read-only binary status |
| `multiStateInput` | `multi_state` | Read-only multi-state |
| `multiStateOutput` | `multi_state` | Writable multi-state |

---

## 15. Safety Classification Reference

Every point carries a `safety_class` used by the AEGIS safety engine to gate write-back authority:

| Class | Description | Requires Approval |
|-------|-------------|-----------------|
| `CRITICAL` | Physical safety, fire, life safety | Always human-in-loop |
| `HIGH` | BESS dispatch, generator control, HVAC setpoints | Supervised mode + approval |
| `MEDIUM` | Lighting dimming, DALI scenes | Advisory mode OK |
| `LOW` | Analytics, predictions, notifications | Shadow mode sufficient |

**AEGIS Phase gates:**
- `AEGIS_BESS_WRITER_ENABLED=false` (Phase 0/Shadow): All writes blocked
- Phase 1 entry requires 14-day simulation + 14-day live-read + all tripwires clear
- Phase 3 (`AEGIS_BESS_WRITER_ENABLED=true`): Only after supervised mode validation

---

## 16. SDP Ingestion Notes

### 16.1 Outlook Resource Scheduler → `zone_display_mappings`

The Space Module requires room booking data. SDP flow must:
1. Query Outlook Resource Scheduler API for all room mailboxes at Fairland
2. Extract: room email, capacity, floor, building, features
3. Upsert into `sentinel.space_zone_display_mappings`

**SDP Ticket:** Pending (in flight)

### 16.2 REMS Helpdesk → `work_orders`

Maintenance tickets from the REMS system must flow into `ops_work_orders`. SDP flow must:
1. Poll REMS API for new/updated tickets tagged to SENTINEL-monitored sites
2. Map: REMS ticket ID → `work_orders.code`, priority, assigned technician
3. Upsert into `sentinel.ops_work_orders`

**SDP Ticket:** Pending (in flight)

---

## 17. iDNa Service Mapping Summary

| SENTINEL Data | iDNa Service | Protocol | Notes |
|--------------|-------------|---------|-------|
| Equipment telemetry (BACnet/Modbus) | EEH (Kafka) | MQTT → Kafka | SIMBIOT adapter produces |
| ESP32 occupancy events | EEH (Kafka) | MQTT | Low-volume, 5-min poll |
| Solar/BESS telemetry | EEH (Kafka) | Modbus TCP → MQTT | SmartLogger3000A bridge |
| Historical telemetry | BDP (Cloudera) | SDP / Batch | Parquet landing zone |
| ML training data (hourly/daily aggregates) | BDP (Cloudera) | SDP / Batch | 5-year retention |
| AI inference | AI Labs | Internal Azure OpenAI | GPT-4o via Team Jarvis |
| SentryBot on Telegram | Logging → BDP | SDP / Batch | Audit log export |
| SentryBot on WhatsApp | CBP Routing | WhatsApp Business API | Space Module only |

---

## 17. iDNa Service Mapping Summary

| SENTINEL Data | iDNa Service | Protocol | Notes |
|--------------|-------------|---------|-------|
| Equipment telemetry (BACnet/Modbus) | EEH (Kafka) | MQTT → Kafka | SIMBIOT adapter produces |
| ESP32 occupancy events | EEH (Kafka) | MQTT | Low-volume, 5-min poll |
| Solar/BESS telemetry | EEH (Kafka) | Modbus TCP → MQTT | SmartLogger3000A bridge |
| Historical telemetry | BDP (Cloudera) | SDP / Batch | Parquet landing zone |
| ML training data (hourly/daily aggregates) | BDP (Cloudera) | SDP / Batch | 5-year retention |
| AI inference | AI Labs | Internal Azure OpenAI | GPT-4o via Team Jarvis |
| SentryBot on Telegram | Logging → BDP | SDP / Batch | Audit log export |
| SentryBot on WhatsApp | CBP Routing | WhatsApp Business API | Space Module only |

---

## 18. AI Labs Integration (Azure OpenAI / Team Jarvis)

### 18.1 Model Gateway — `idna` Routing Profile

SENTINEL's model gateway is provider-agnostic by design. The existing architecture uses ordered fallback chains per task class (`heavy`, `medium`, `light`, `chat_ai`, `chat_tech`). A new `idna` profile wires Azure OpenAI as the primary provider.

**Current profiles:**

| Profile | Mode | Fallback | Primary Provider |
|---------|------|----------|----------------|
| `api_prod` | `api` | Yes | MiniMax → Anthropic → OpenAI |
| `cloud_dev` | `api` | Yes | MiniMax → Anthropic → OpenAI |
| `local_full` | `local` | No | Ollama only |
| `idna` | `api` | TBD | Azure OpenAI (Team Jarvis) |

**Proposed `idna` profile (pending DL-Jarvis confirmation):**

```python
ROUTING_PROFILES: dict[str, dict[str, Any]] = {
    "idna": {
        "mode": "api",
        "fallback_enabled": True,  # or False — confirm with DL-Jarvis
        "routing": {
            "heavy": [
                {"provider": "azure_openai", "model": "gpt-4o"},
            ],
            "medium": [
                {"provider": "azure_openai", "model": "gpt-4o"},
            ],
            "light": [
                {"provider": "azure_openai", "model": "gpt-4o-mini"},
            ],
            "chat_ai": [
                {"provider": "azure_openai", "model": "gpt-4o"},
            ],
            "chat_tech": [
                {"provider": "azure_openai", "model": "gpt-4o"},
            ],
        },
    },
}
```

**SENTINEL code change required:** Add `azure_openai` provider to `backend/app/services/model_gateway.py` and create the `idna` profile in `backend/app/config/routing_profiles.py`.

---

### 18.2 Model Capability Requirements

SENTINEL uses LLM calls for three distinct capability areas — all must be available on the Azure OpenAI deployment:

| Capability | Models Required | SENTINEL Use Case |
|-----------|----------------|-------------------|
| **Function calling / tool use** | GPT-4o | Structured JSON extraction from free-text technician reports, work order parsing, equipment identification |
| **Structured JSON output** | GPT-4o | RAG answer synthesis, prediction evidence formatting, alert triage |
| **Streaming** | GPT-4o, GPT-4o-mini | SentryBot Telegram responses (token-by-token for long explanations) |
| **Long context** | GPT-4o (128k window) | Full document chunk analysis for RAG, multi-equipment incident correlation |
| **Fast inference** | GPT-4o-mini | Light classification tasks, confidence band assignment |

---

### 18.3 Embedding Storage for RAG

pgvector does not ship on BDP. The document intelligence pipeline (Section 10) requires a BDP-native embedding store. Options, in order of preference:

| Option | Status | Notes |
|--------|--------|-------|
| **Azure AI Search** | Preferred | Within AI Labs perimeter; approved for internal RAG workloads; supports hybrid search |
| **Pinecone** | Requires approval | If Azure AI Search is not available in the iDNa tenant |
| **BDP HDFS + FAISS** | Fallback | Build per-site FAISS index; more operational overhead |

**Discovery question for DL-Jarvis:** Is Azure AI Search available in the iDNa AI Labs tenant? What is the approved vector store for RAG workloads?

---

### 18.4 Prompt Governance

SENTINEL does not send raw user prompts to the LLM. All prompts pass through:
1. **Prompt guard** — input filtering (length, character class, injection prevention)
2. **Template rendering** — Jinja2 templates with `{{ }}` escaping (`_esc()`) for all user-supplied text
3. **Output filter** — response validation before passing to downstream systems

Prompt templates are stored in `backend/app/prompts/` as versioned `.j2` files. Governance question for DL-Jarvis:
- **Pre-approved prompt library**: Can SENTINEL submit its prompt templates for one-time review and approval (fast path)?
- **Per-prompt review**: Or does each prompt change require DL-Jarvis re-approval (slow path, affects sprint velocity)?

---

### 18.5 Discovery Questions for DL-Jarvis

1. What is the Azure OpenAI endpoint URL and authentication method for the internal Team Jarvis deployment?
2. Which models are available (`gpt-4o`, `gpt-4o-mini`, others)?
3. Is `fallback_enabled: true` supported, or is single-provider mode required?
4. Is Azure AI Search available in the iDNa AI Labs tenant for RAG embedding storage?
5. What is the prompt governance process — one-time library approval or per-prompt review?
6. Are there rate limits or quotas that affect SENTINEL's 600-site scale target?
7. Is the internal Azure OpenAI deployment in the same region as BDP/EEH (for latency)?

---

**Document Status:** Draft — awaiting iDNa Data Engineering discovery session
**Next Step:** Confirm BDP Landing Zone provisioning timeline and SDP flow lead time
**Owner:** SENTINEL Architecture Office
**Version:** 1.0.0
