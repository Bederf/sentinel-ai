---
title: "Municipal Tariff Updates (Annual)"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Municipal Tariff Updates (Annual)

Municipal tariffs typically change once per year (FY). The system supports annual refresh via a tariff ingestion service that downloads official PDF sources and registers them in `municipal_tariff_schedules`.

## Source Registry

Source list: `backend/app/data/municipal_tariff_sources.json`

Each entry includes:
- `municipality`
- `tariff_name`
- `effective_date`
- `source_url`
- `notes`

## Ingestion Service

Service: `backend/app/services/municipal_tariff_ingestion_service.py`

- Downloads PDFs into `backend/app/data/municipal_tariffs_raw/`
- Creates/updates `municipal_tariff_schedules` records
- Stores `source_url` and `source_file_path`

## Operational Flow

1. Update `municipal_tariff_sources.json` annually (May–July)
2. Run ingestion job (manual or scheduled)
3. Review/parse updated tariffs into structured `tariff_data`

## Notes

- Parsing can be iterative; raw PDFs are stored for audit.
- Where PDFs are not directly accessible, a manual download is required.

## Manual Update Checklist

1. Download the latest tariff PDF from the official municipal source.
2. Update `backend/app/data/municipal_tariff_sources.json` with the new `source_url` and `effective_date`.
3. Run `POST /api/municipal-billing/tariffs/ingest` to store the PDF reference.
4. Verify the new record in `municipal_tariff_schedules` (effective date + source URL).
5. If structured `tariff_data` is needed for calculations, parse and update the record manually.
