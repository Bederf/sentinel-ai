# Zone Ingestion API Testing Guide

This document provides step-by-step procedures for testing the zone ingestion system via API endpoints.

## Prerequisites

- Backend running: `./start-backend.sh` (http://localhost:9095)
- Supabase instance running (local or cloud)
- `curl` or Postman for API testing
- Optional: `jq` for JSON formatting

## API Base Path

All zone ingestion endpoints are prefixed with: `/api/buildings/{building_id}/zone-ingestion`

## Test Scenarios

### Scenario 1: Single Building Zone Configuration (site-002)

**Description:** Test ingesting zone configuration for site-002 with 15 zones (5 per floor × 3 floors).

#### Step 1: Ingest Zones

```bash
curl -X POST http://localhost:9095/api/buildings/site-002/zone-ingestion/zones \
  -H "Content-Type: application/json" \
  -d '{
    "zones": [
      {
        "zone_id": "Zone-L0-A",
        "zone_name": "Level 0 Zone A",
        "floor": "L0",
        "zone_letter": "A",
        "zone_type": "open_office",
        "typical_occupancy": 20,
        "area_sqm": 200
      },
      {
        "zone_id": "Zone-L0-B",
        "zone_name": "Level 0 Zone B",
        "floor": "L0",
        "zone_letter": "B",
        "zone_type": "meeting_room",
        "typical_occupancy": 10,
        "area_sqm": 100
      },
      {
        "zone_id": "Zone-L0-C",
        "zone_name": "Level 0 Zone C",
        "floor": "L0",
        "zone_letter": "C",
        "zone_type": "plant_room",
        "typical_occupancy": 5,
        "area_sqm": 150
      },
      {
        "zone_id": "Zone-L0-D",
        "zone_name": "Level 0 Zone D",
        "floor": "L0",
        "zone_letter": "D",
        "zone_type": "storage",
        "typical_occupancy": 0,
        "area_sqm": 80
      },
      {
        "zone_id": "Zone-L0-E",
        "zone_name": "Level 0 Zone E",
        "floor": "L0",
        "zone_letter": "E",
        "zone_type": "corridor",
        "typical_occupancy": 0,
        "area_sqm": 120
      },
      {
        "zone_id": "Zone-L1-A",
        "zone_name": "Level 1 Zone A",
        "floor": "L1",
        "zone_letter": "A",
        "zone_type": "open_office",
        "typical_occupancy": 20,
        "area_sqm": 200
      },
      {
        "zone_id": "Zone-L1-B",
        "zone_name": "Level 1 Zone B",
        "floor": "L1",
        "zone_letter": "B",
        "zone_type": "open_office",
        "typical_occupancy": 20,
        "area_sqm": 200
      },
      {
        "zone_id": "Zone-L1-C",
        "zone_name": "Level 1 Zone C",
        "floor": "L1",
        "zone_letter": "C",
        "zone_type": "open_office",
        "typical_occupancy": 20,
        "area_sqm": 200
      },
      {
        "zone_id": "Zone-L1-D",
        "zone_name": "Level 1 Zone D",
        "floor": "L1",
        "zone_letter": "D",
        "zone_type": "meeting_room",
        "typical_occupancy": 15,
        "area_sqm": 150
      },
      {
        "zone_id": "Zone-L1-E",
        "zone_name": "Level 1 Zone E",
        "floor": "L1",
        "zone_letter": "E",
        "zone_type": "cafeteria",
        "typical_occupancy": 30,
        "area_sqm": 250
      },
      {
        "zone_id": "Zone-L2-A",
        "zone_name": "Level 2 Zone A",
        "floor": "L2",
        "zone_letter": "A",
        "zone_type": "open_office",
        "typical_occupancy": 20,
        "area_sqm": 200
      },
      {
        "zone_id": "Zone-L2-B",
        "zone_name": "Level 2 Zone B",
        "floor": "L2",
        "zone_letter": "B",
        "zone_type": "open_office",
        "typical_occupancy": 20,
        "area_sqm": 200
      },
      {
        "zone_id": "Zone-L2-C",
        "zone_name": "Level 2 Zone C",
        "floor": "L2",
        "zone_letter": "C",
        "zone_type": "open_office",
        "typical_occupancy": 20,
        "area_sqm": 200
      },
      {
        "zone_id": "Zone-L2-D",
        "zone_name": "Level 2 Zone D",
        "floor": "L2",
        "zone_letter": "D",
        "zone_type": "server_room",
        "typical_occupancy": 2,
        "area_sqm": 100
      },
      {
        "zone_id": "Zone-L2-E",
        "zone_name": "Level 2 Zone E",
        "floor": "L2",
        "zone_letter": "E",
        "zone_type": "mechanical",
        "typical_occupancy": 0,
        "area_sqm": 120
      }
    ]
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "zones_created": 15
}
```

#### Step 2: Ingest Desks (20 per zone, 300 total)

```bash
curl -X POST http://localhost:9095/api/buildings/site-002/zone-ingestion/desks \
  -H "Content-Type: application/json" \
  -d '{
    "desks": [
      {
        "desk_id": "1001",
        "desk_name": "Desk 1001",
        "floor": "L0",
        "zone_id": "Zone-L0-A",
        "context": "near_window",
        "coordinates": {"x": 2.5, "y": 3.5, "z": 5.0}
      },
      {
        "desk_id": "1002",
        "desk_name": "Desk 1002",
        "floor": "L0",
        "zone_id": "Zone-L0-A",
        "context": "open_plan",
        "coordinates": {"x": 3.8, "y": 3.5, "z": 7.5}
      },
      {
        "desk_id": "1003",
        "desk_name": "Desk 1003",
        "floor": "L0",
        "zone_id": "Zone-L0-A",
        "context": "near_printer",
        "coordinates": {"x": 5.0, "y": 3.5, "z": 10.0}
      }
    ]
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "desks_created": 3
}
```

### Scenario 2: Zone Centroid Calculation

**Description:** Test that zone centroids are correctly calculated from desk positions.

#### Retrieve Zone Centroid

```bash
curl -X GET http://localhost:9095/api/buildings/site-002/desks/zones/Zone-L0-A/centroid
```

**Expected Response:**
```json
{
  "zone_id": "Zone-L0-A",
  "centroid": {
    "x": 3.77,
    "z": 7.5
  }
}
```

### Scenario 3: Multi-Building Support

**Description:** Ingest zones for a second building (site-003) with different configuration.

#### Step 1: Ingest Zones for site-003 (6 zones)

```bash
curl -X POST http://localhost:9095/api/buildings/site-003/zone-ingestion/zones \
  -H "Content-Type: application/json" \
  -d '{
    "zones": [
      {"zone_id": "Zone-L1-A", "zone_name": "Zone A", "floor": "L1", "zone_type": "open_office"},
      {"zone_id": "Zone-L1-B", "zone_name": "Zone B", "floor": "L1", "zone_type": "meeting_room"},
      {"zone_id": "Zone-L1-C", "zone_name": "Zone C", "floor": "L1", "zone_type": "plant_room"},
      {"zone_id": "Zone-L2-A", "zone_name": "Zone A", "floor": "L2", "zone_type": "open_office"},
      {"zone_id": "Zone-L2-B", "zone_name": "Zone B", "floor": "L2", "zone_type": "open_office"},
      {"zone_id": "Zone-L2-C", "zone_name": "Zone C", "floor": "L2", "zone_type": "storage"}
    ]
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "zones_created": 6
}
```

#### Verify site-002 and site-003 have different configurations

```bash
# Verify site-002 has 15 zones
curl -X GET http://localhost:9095/api/buildings/site-002/desks/centroids | jq '.centroids | length'
# Expected: 15

# Verify site-003 has 6 zones
curl -X GET http://localhost:9095/api/buildings/site-003/desks/centroids | jq '.centroids | length'
# Expected: 6
```

### Scenario 4: Error Handling

**Description:** Test validation and error handling.

#### Test Duplicate Zone IDs

```bash
curl -X POST http://localhost:9095/api/buildings/site-004/zone-ingestion/zones \
  -H "Content-Type: application/json" \
  -d '{
    "zones": [
      {"zone_id": "Zone-L1-A", "zone_name": "Zone A", "floor": "L1", "zone_type": "open_office"},
      {"zone_id": "Zone-L1-A", "zone_name": "Duplicate", "floor": "L1", "zone_type": "meeting_room"}
    ]
  }'
```

**Expected Response (Error):**
```json
{
  "status": "error",
  "message": "Duplicate zone_ids detected"
}
```

#### Test Invalid Zone Reference

```bash
curl -X POST http://localhost:9095/api/buildings/site-004/zone-ingestion/zones \
  -H "Content-Type: application/json" \
  -d '{"zones": [{"zone_id": "Zone-L1-A", "zone_name": "Zone A", "floor": "L1", "zone_type": "open_office"}]}'

# Then try to add desk referencing non-existent zone
curl -X POST http://localhost:9095/api/buildings/site-004/zone-ingestion/desks \
  -H "Content-Type: application/json" \
  -d '{
    "desks": [
      {"desk_id": "1001", "zone_id": "Zone-L99-Z", "floor": "L99", "context": "open_plan", "coordinates": {"x": 1, "y": 3.5, "z": 1}}
    ]
  }'
```

**Expected Response (Error):**
```json
{
  "status": "error",
  "message": "Invalid zone_id: Zone-L99-Z"
}
```

## Performance Validation

### Payload Size Comparison

```bash
# Full desk data (300 desks, ~120KB)
curl -s http://localhost:9095/api/buildings/site-002/desks | wc -c

# Zone centroids only (15 centroids, ~1.5KB)
curl -s http://localhost:9095/api/buildings/site-002/desks/centroids | wc -c

# Expected: Centroids should be ~80x smaller payload
```

### Response Time Benchmarks

```bash
# Measure time to get all desks
time curl -s http://localhost:9095/api/buildings/site-002/desks > /dev/null

# Measure time to get centroids
time curl -s http://localhost:9095/api/buildings/site-002/desks/centroids > /dev/null

# Expected: Centroids should respond much faster
```

## Data Integrity Checks

### Verify Zone Count

```bash
# SQL check: Count zones in Supabase
psql $DATABASE_URL -c "SELECT COUNT(*) FROM zones WHERE building_id = 'site-002';"
# Expected: 15
```

### Verify Desk Count

```bash
# SQL check: Count desks in Supabase
psql $DATABASE_URL -c "SELECT COUNT(*) FROM desks WHERE building_id = 'site-002';"
# Expected: 300

# Verify desks per zone
psql $DATABASE_URL -c "SELECT zone_id, COUNT(*) FROM desks WHERE building_id = 'site-002' GROUP BY zone_id;"
# Expected: Each zone should have 20 desks
```

### Verify Centroid Calculation

```bash
# Manual verification: Calculate centroid for Zone-L0-A
psql $DATABASE_URL -c "
  SELECT 
    AVG(coordinates->>'x')::numeric(10,2) as avg_x,
    AVG(coordinates->>'z')::numeric(10,2) as avg_z
  FROM desks
  WHERE building_id = 'site-002' AND zone_id = 'Zone-L0-A';
"
```

## Visual Verification (Frontend)

### Step 1: Open Digital Twin

Navigate to: http://localhost:9096/digital-twin

### Step 2: Select Building

Choose site-002 from building selector

### Step 3: Select Floor

Select L1 floor using floor tabs

### Step 4: Verify Equipment Positioning

- Equipment should be spread across 5 zones (A, B, C, D, E)
- No equipment overlap (minimum 0.5m spacing)
- Equipment types should have different Z positions within zones:
  - FCU: Slightly left (-1m from zone center)
  - VAV: Slightly front (-2m from zone center)
  - DALI: Spread right (+1m from zone center)

### Step 5: Switch Buildings (Optional)

If site-003 has been onboarded:
- Switch to site-003
- Verify equipment positions adapt to new zone configuration
- Confirm different zone structure visually

## Success Criteria

✅ All 20 zone ingestion validation tests pass
✅ Zones and desks can be ingested without errors
✅ Zone centroids calculated correctly
✅ Multi-building support works (different configurations)
✅ Validation prevents duplicates and invalid references
✅ Performance: Centroid queries <50ms, full desk queries <200ms
✅ Data integrity: Correct zone/desk counts in Supabase
✅ Visual: Equipment positioned correctly in Digital Twin across zones

## Common Issues & Solutions

### Issue: "Supabase client not available"
**Solution:** Ensure Supabase is running. For local: `supabase start`. For cloud: check connection string in `.env`

### Issue: Duplicate zone IDs rejected
**Solution:** This is expected validation. Use unique zone IDs for each zone within a building.

### Issue: Invalid zone reference on desk ingestion
**Solution:** Ensure all desk zone_ids match zone_ids that were previously ingested for that building.

### Issue: Centroids not calculated
**Solution:** Ensure desks have been ingested for the zone. Empty zones return null for centroid.

### Issue: Equipment not positioned correctly in Digital Twin
**Solution:** Clear browser cache and reload. Verify zone centroids endpoint returns correct data.
