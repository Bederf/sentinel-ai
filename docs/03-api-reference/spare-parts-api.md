---
title: "Spare Parts Catalog API"
type: "reference"
status: "active"
version: "1.0.0"
created: "2026-05-24"
updated: "2026-05-24"
tags: ["sentinel", "documentation", "api", "spare-parts", "maintenance"]
domain: "bms"
audience: "developers", "technicians"
complexity: "intermediate"
estimated_read_time: 8
---

# Spare Parts Catalog API

REST API for the spare parts catalog, inventory management, and OEM part number lookup. Built as part of Phase 209.

## Data Model

Two tables:

- **`spare_parts`**: Part catalog entries linked to equipment type, manufacturer, and model. Stores OEM part numbers, costs, and replacement intervals.
- **`spare_parts_inventory`**: Stock levels per part — quantity on hand, min/max thresholds, location.

### Spare Part Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `equipment_id` | UUID? | FK to specific equipment instance (nullable — generic parts are type-scoped) |
| `equipment_type` | TEXT | e.g., `chiller`, `ahu`, `fcu`, `vav`, `pump`, `cooling_tower`, `generator`, `ups`, `bess`, `meter`, `dali` |
| `manufacturer` | TEXT? | OEM manufacturer (for manufacturer-specific parts) |
| `model` | TEXT? | OEM model number |
| `part_name` | TEXT | Human-readable part name |
| `part_number` | TEXT? | OEM part number |
| `alternate_part_numbers` | TEXT[] | Cross-reference part numbers |
| `unit_cost_zar` | DECIMAL? | Cost per unit in ZAR |
| `typical_replacement_interval_days` | INT? | Expected service life |
| `criticality` | TEXT | `critical`, `essential`, or `consumable` |
| `source` | TEXT | `curated` (seeded), `scraped` (Firecrawl OEM), or `manual` (technician-added) |
| `is_active` | BOOLEAN | Soft delete flag |

## Endpoints

### `GET /api/parts/equipment/{code}`

Get spare parts for a specific equipment instance by its equipment code (e.g., `S002-AHU-B01`). Resolves equipment code to UUID, queries by `equipment_id` first, then falls back to type + manufacturer + model match.

**Response:** Array of spare part objects with nested inventory.

```
GET /api/parts/equipment/S002-AHU-B01
```
```json
[
  {
    "id": "...", "part_name": "V-belt set",
    "part_number": "BELT-AHU-B", "unit_cost_zar": 550.00,
    "criticality": "essential", "source": "curated",
    "spare_parts_inventory": { "quantity_on_hand": 5, "min_threshold": 2 }
  }
]
```

### `GET /api/parts`

Search the parts catalog with filters. All query parameters are optional.

| Param | Type | Description |
|-------|------|-------------|
| `query` | TEXT | Search by part name or part number |
| `type` | TEXT | Filter by equipment type |
| `manufacturer` | TEXT | Filter by manufacturer |
| `model` | TEXT | Filter by model |
| `low_stock` | BOOL | Return only parts below min_threshold |

### `GET /api/parts/{part_id}`

Get a single part by UUID with full inventory details.

### `POST /api/parts`

Create a new spare part entry. Automatically creates an inventory record with initial stock.

**Body:**
```json
{
  "equipment_type": "ahu",
  "part_name": "V-belt set",
  "part_number": "BELT-AHU-B",
  "unit_cost_zar": 550.00,
  "criticality": "essential",
  "initial_stock": 5,
  "min_threshold": 2
}
```

### `PATCH /api/parts/{part_id}`

Update part fields (name, number, cost, criticality, etc.). Only provided fields are updated.

### `PATCH /api/parts/{part_id}/inventory`

Update stock quantity.

**Body:**
```json
{
  "quantity_on_hand": 10,
  "location": "Store Room A"
}
```

### `POST /api/parts/{part_id}/decrement`

Decrement inventory by quantity (default 1). Used when a part is consumed on a work order.

### `POST /api/parts/{part_id}/link/{equipment_code}`

Link a generic (equipment-type-scoped) part to a specific equipment instance. Used when a technician identifies that a generic part belongs to a specific asset.

## Integration Points

### Technician Chat

When a technician completes a diagnosis session, the resolution step queries `spare_parts` for the identified equipment type. Parts with OEM part numbers are included in the `parts_needed` list alongside repair steps and safety notes.

### Work Order Creation

When a technician work order is created via `POST /api/work-orders/technician`, if `parts_needed` is empty, the system auto-populates it from the spare parts catalog based on the equipment type.

### Work Order Completion

When a work order is completed via `POST /api/work-orders/technician/{id}/complete`, the `parts_used` list is matched against the spare parts catalog and inventory is decremented automatically.

## OEM Scraping (Firecrawl)

Parts can be populated automatically from OEM websites using Firecrawl. Requires `FIRECRAWL_API_KEY` in `.env`.

**Flow:**
1. Equipment onboarded via SIMBIOT wizard → manufacturer + model captured in `device_info`
2. Background task fires `scrape_oem_parts(manufacturer, model, equipment_type)`
3. Firecrawl searches OEM parts sites + scrapes product pages for part numbers
4. Found parts inserted into `spare_parts` with `source: 'scraped'`
5. If scraping fails or returns nothing → falls back to curated seed data

**Curated fallback:** 49 parts across 11 equipment types are pre-seeded with OEM part numbers and default stock levels.

### Part Population Strategy (3-tier)

1. Firecrawl OEM scraping (best-effort)
2. Manufacturer-specific curated (Carrier chiller, Trane chiller, Grundfos pump, etc.)
3. Generic type-based curated (49 parts by equipment type — always works)

## Seeded Parts (49 entries)

| Equipment Type | Parts Count | Example Parts |
|---------------|-------------|---------------|
| chiller | 6 | Oil filter, filter drier, compressor oil, coil cleaner, temp sensor, expansion valve kit |
| ahu | 5 | V-belt set, MERV-13 filters, fan bearing, motor capacitor, drain trap |
| fcu | 5 | EC fan motor, air filters, valve actuator, thermostat, drain pan kit |
| vav | 4 | Damper actuator, flow sensor, reheat valve, controller board |
| pump | 4 | Mechanical seal, bearing set, impeller, gasket set |
| cooling_tower | 5 | Fan belt set, motor bearing, fill media, drift eliminator, level sensor |
| generator | 5 | Oil filter, fuel filter, air filter, battery set, coolant |
| bess | 4 | HV battery module, BMS comm board, thermal sensor harness, contact relay |
| ups | 4 | Battery cartridge, capacitor bank, cooling fan, surge module |
| meter | 3 | CT clamp 500A, PSU module, RS485 comm module |
| dali | 4 | DALI PSU, controller board, LED emergency driver, bus coupler |
