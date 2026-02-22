---
title: "Security Module Database Schema (Phase 69)"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-22"
updated: "2026-02-22"
author: "Sentinel Development Team"
tags: ["database", "security", "schema", "access-rules", "occupancy"]
domain: "security"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 5
---

# Security Module Database Schema (Phase 69)

Migration: `supabase/migrations/security_module.sql`
Extends: `supabase/migrations/033_security_module_schema.sql` (Phase 33 base schema)

## Tables

### access_rules

Configurable access restrictions per zone. Supports time-based scheduling, occupancy-based limits, and emergency protocols.

```sql
CREATE TABLE access_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id TEXT NOT NULL,
    rule_type TEXT NOT NULL DEFAULT 'time_based'
        CHECK (rule_type IN ('time_based', 'occupancy_based', 'emergency')),
    rule_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Indexes:**
- `idx_access_rules_zone_id` on `zone_id`
- `idx_access_rules_active` on `(active, rule_type)`

**Trigger:** `trigger_access_rules_updated_at` auto-updates `updated_at` on row change.

**Rule types and config shapes:**

| Rule Type | Config Shape | Example |
|-----------|-------------|---------|
| `time_based` | `{"start_hour": 6, "end_hour": 22, "days": ["mon","tue",...]}` | Business hours access |
| `occupancy_based` | `{"max_occupancy": 5, "alert_threshold": 4}` | Plant room occupancy limit |
| `emergency` | `{"unlock_all_doors": true, "notify_security": true, "evacuation_route": "north_stairwell"}` | Evacuation protocol |

### security_occupancy (extended columns)

Added to existing table from migration 033:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `max_capacity` | INTEGER | 50 | Fire code maximum occupancy per zone |
| `percent_full` | DECIMAL(5,2) | 0.0 | Computed fullness percentage (`occupancy_count / max_capacity * 100`) |

### security_cameras (extended columns)

Added to existing table from migration 033:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `stream_url` | TEXT | `''` | RTSP stream URL for camera feed |
| `camera_model` | TEXT | `''` | Camera hardware model (e.g., "Hikvision DS-2CD2143G2-IU") |

## Sample Data

The migration includes sample data for demo mode:

**Zone occupancy (4 zones):**

| Zone | Name | Occupancy | Capacity | % Full |
|------|------|-----------|----------|--------|
| `zone_000` | Ground Floor Lobby | 12 | 50 | 24.0% |
| `zone_001` | Level 1 Open Plan | 22 | 40 | 55.0% |
| `zone_002` | Level 2 Executive | 8 | 35 | 22.9% |
| `zone_plant` | Plant Room B1 | 0 | 10 | 0.0% |

**Access rules (4 rules):**

| Zone | Type | Description |
|------|------|-------------|
| `zone_000` | time_based | Business hours (06:00-22:00, Mon-Fri) |
| `zone_001` | time_based | Office hours (07:00-20:00, Mon-Fri) |
| `zone_plant` | occupancy_based | Max 5 people, alert at 4 |
| `zone_000` | emergency | Evacuation protocol (inactive by default) |

## Related Documentation

- [Security API Reference](../03-api-reference/security-api.md)
- [Security Module Feature Spec](../04-features/58-security-module.md)
- [Base Security Schema (Migration 033)](../../supabase/migrations/033_security_module_schema.sql)
