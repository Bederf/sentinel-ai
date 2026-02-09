# Municipal Billing API

Base prefix: `/api/municipal-billing`

## Invoice Upload

`POST /invoices/upload`

Form fields:
- `file` (PDF)
- `site_id`
- `municipality`
- `utility_type` (electricity | water | gas | sewerage | refuse)
- `account_number`
- `tariff_type` (optional)
- `meter_number` (optional)

Returns:
- `invoice`
- `reconciliation` (if parsed data available)
- `pdf_path`

`POST /invoices/upload-batch`

Form fields:
- `files[]`
- `site_id`
- `municipality`
- `utility_type`
- `account_number`
- `tariff_type` (optional)

## Invoice Management

`GET /invoices`

Query params:
- `site_id`
- `municipality`
- `utility_type`
- `billing_period`
- `reconciliation_status`
- `limit` (default 50)
- `offset` (default 0)

`GET /invoices/{invoice_id}`

`GET /invoices/{invoice_id}/pdf`

`POST /invoices/{invoice_id}/approve`

Form fields:
- `approved_by`

`POST /invoices/{invoice_id}/dispute`

Form fields:
- `dispute_reason`
- `disputed_by`

`GET /invoices/{invoice_id}/dispute-pack`

Returns a structured evidence payload for municipal disputes.

## Tariffs

`GET /tariffs`

Query params:
- `municipality`
- `utility_type`
- `active_date` (YYYY-MM-DD)

`POST /tariffs`

Form fields:
- `municipality`
- `tariff_name`
- `utility_type`
- `effective_date` (YYYY-MM-DD)
- `tariff_data` (JSON string)

`GET /tariffs/{municipality}/{tariff_name}/calculate`

Query params:
- `site_id`
- `month`
- `year`

`POST /tariffs/ingest`

Triggers ingestion of official tariff PDFs based on the source registry.

## Reconciliation

`GET /reconciliation/portfolio`

Query params:
- `billing_period` (YYYY-MM)

`GET /reconciliation/{site_id}/load-profile`

Query params:
- `period_start` (YYYY-MM-DD)
- `period_end` (YYYY-MM-DD)

`GET /reconciliation/{site_id}/maximum-demand`

Query params:
- `period_start` (YYYY-MM-DD)
- `period_end` (YYYY-MM-DD)
- `meter_id` (optional)
- `sensor_type` (optional, default: `power`)
