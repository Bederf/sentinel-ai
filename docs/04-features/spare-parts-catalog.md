---
title: "Spare Parts Catalog & Inventory Management"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-05-24"
updated: "2026-05-24"
tags: ["sentinel", "documentation", "spare-parts", "maintenance", "inventory"]
domain: "bms"
audience: "technicians", "developers"
complexity: "intermediate"
estimated_read_time: 10
phase: "209"
---

# Spare Parts Catalog & Inventory Management

The Spare Parts Catalog provides a searchable, equipment-linked database of OEM spare parts with real-time inventory tracking. It connects the SIMBIOT onboarding wizard, technician diagnosis chat, and work order lifecycle into a unified parts management pipeline.

## Architecture

```
SIMBIOT Onboarding
  └─ add_site_devices_tool
       └─ equipment created with manufacturer + model
            └─ Background task: _populate_parts_background()
                 ├─ Firecrawl OEM scrape (searches manufacturer parts sites)
                 ├─ Manufacturer-specific curated fallback
                 └─ Generic type-based fallback (49 curated parts)
                      │
                      ▼
               spare_parts table (OEM part numbers, costs, intervals)
                    │
                    ├─ Technician Chat resolution step
                    │    └─ Parts displayed with OEM numbers in repair plan
                    │
                    ├─ Work Order creation
                    │    └─ parts_required auto-populated from catalog
                    │
                    └─ Work Order completion
                         └─ parts_used decrements spare_parts_inventory
```

## Key Capabilities

### Equipment-Specific Parts

When equipment is onboarded via SIMBIOT, the system automatically looks up relevant spare parts:

1. **Firecrawl OEM Scraping** — Searches manufacturer websites (Carrier, Trane, York, Daikin, Grundfos, etc.) for part numbers matching the equipment model. Requires `FIRECRAWL_API_KEY` in `.env`.
2. **Manufacturer-Specific Curated** — Pre-seeded data for common manufacturer + type combinations (e.g., Carrier chiller 30XA oil filter with OEM part number).
3. **Generic Type-Based** — 49 parts pre-seeded across 11 equipment types. Always works as a fallback.

### Inventory Tracking

Each part has an inventory record tracking quantity on hand, minimum threshold, and maximum threshold. When inventory drops below the minimum threshold, the part is flagged as low stock.

### Integration with Technician Workflow

**Technician Chat:** When a technician completes a diagnosis (e.g., "AHU showing E4"), the resolution step includes relevant spare parts with OEM part numbers and stock levels.

**Work Order Creation:** Creating a technician work order auto-populates `parts_required` from the spare parts catalog based on the equipment type.

**Work Order Completion:** When a work order is completed with `parts_used`, matching parts in inventory are automatically decremented.

### Parts Population Strategy

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | Firecrawl OEM scrape | Real-time search of manufacturer parts sites |
| 2 | Manufacturer-specific curated | Pre-seeded Carrier, Trane, York, Daikin, Grundfos parts |
| 3 | Generic type-based curated | 49 parts across 11 equipment types |

## Database Schema

### `spare_parts` Table

```sql
CREATE TABLE spare_parts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id UUID REFERENCES equipment(id) ON DELETE CASCADE,
    equipment_type TEXT NOT NULL,
    manufacturer TEXT,
    model TEXT,
    part_name TEXT NOT NULL,
    part_number TEXT,
    alternate_part_numbers TEXT[] DEFAULT '{}',
    unit_cost_zar DECIMAL(10,2),
    typical_replacement_interval_days INTEGER,
    criticality TEXT CHECK (criticality IN ('critical','essential','consumable')),
    source TEXT CHECK (source IN ('curated','scraped','manual')) DEFAULT 'curated',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `spare_parts_inventory` Table

```sql
CREATE TABLE spare_parts_inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL REFERENCES spare_parts(id) ON DELETE CASCADE,
    quantity_on_hand INTEGER NOT NULL DEFAULT 0,
    min_threshold INTEGER DEFAULT 2,
    max_threshold INTEGER DEFAULT 10,
    location TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Maintenance Page UI

The spare parts section appears in the Maintenance History tabs on the Failure Prediction Details modal. It shows:

- Part name and OEM part number
- Stock level with color coding (OK / Low / Out of Stock)
- Cost per unit in ZAR
- Criticality badge (critical / essential / consumable)
- Source indicator (curated / scraped / manual)
- "-1" button to mark a part as used (decrements inventory)
- Expandable/collapsible section header with warning indicator when stock or criticality issues exist

## Technician Chat Integration

When diagnosing equipment, the resolution step includes:

1. **Repair steps** from fault code database or DEFAULT_MAINTENANCE_ACTIONS
2. **Parts needed** with OEM part numbers from the spare parts catalog
3. **Safety notes** from fault lookup or generic LOTO/PPE reminders
4. **Maintenance guidance** from DEFAULT_MAINTENANCE_ACTIONS per equipment type + risk level

## API Endpoints

See [Spare Parts API Reference](../03-api-reference/spare-parts-api.md) for full endpoint documentation.

Key endpoints:
- `GET /api/parts/equipment/{code}` — Parts for specific equipment
- `GET /api/parts` — Search/filter catalog
- `POST /api/parts` — Create new part
- `PATCH /api/parts/{id}/inventory` — Update stock
- `POST /api/parts/{id}/decrement` — Decrement stock after use

## Default Maintenance Actions

Per-equipment-type maintenance guidance is provided via `DEFAULT_MAINTENANCE_ACTIONS` in `maintenance_recommender.py`. This dict maps equipment types (chiller, ahu, generator, etc.) to risk-level-specific actions (critical, high, medium, low). The technician chat resolution injects these actions as guidance during diagnosis.

## OEMS Scraping Setup

1. Sign up at [firecrawl.dev](https://firecrawl.dev) for an API key
2. Add `FIRECRAWL_API_KEY=fc-xxx` to `backend/.env`
3. Onboarding will automatically search OEM sites for parts
4. Search queries combine manufacturer + model + equipment type
5. Results are cached in the `spare_parts` table with `source: 'scraped'`
