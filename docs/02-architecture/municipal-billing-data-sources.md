# Municipal Billing Data Sources

## Overview

Municipal billing uses **BMS‑derived aggregates** rather than direct sensor reads. This matches SENTINEL’s deployment model (sits on top of BMS platforms).

## Current Demo Sources (Supabase)

- **Energy consumption**: `energy_consumption_history`
  - Daily kWh totals by site
- **Water consumption**: `water_consumption`
  - Cumulative volume readings for each site
- **Maximum demand**: `municipal_demand_history`
  - Daily peak kW/kVA and peak timestamp

## Notes

- In production, each BMS integration should map its aggregate outputs into these tables.
- Direct sensor queries are not required for baseline municipal billing functions.

## Simulation Integration

The BMS simulation service seeds daily peak demand into `municipal_demand_history` for demo sites. This keeps municipal billing analytics consistent with other simulated telemetry sources.

- Service: `backend/app/services/bms_simulation_service.py`
- Method: `_seed_municipal_demand_history`

## Simulation Seeding (Tariffs + Invoices)

The simulation service seeds:
- `municipal_tariff_schedules` with a demo City Power TOU tariff
- `municipal_accounts` for demo sites
- `municipal_invoices` (monthly)

This ensures the municipal billing UI can run end‑to‑end without manual uploads.

## Province-Based Municipality Mapping

Municipality and tariff selection during simulation is based on `buildings.region`:

- Gauteng → City Power Johannesburg (TOU Commercial)
- Western Cape → City of Cape Town (Commercial TOU)
- KwaZulu-Natal → eThekwini (Commercial TOU)
- Eastern Cape → Nelson Mandela Bay (Commercial TOU)
- Free State → Mangaung (Commercial TOU)
- Limpopo → Polokwane (Commercial TOU)
- Mpumalanga → Mbombela (Commercial TOU)
- North West → Rustenburg (Commercial TOU)
- Northern Cape → Sol Plaatje (Commercial TOU)
