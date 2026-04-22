-- Migration: rename_niagara_bacnet_to_bacnet.sql
-- Phase: 190-site-id-normalization, Plan 01, Step 6
-- Date: 2026-04-22
-- Description: Rename NIAGARA_BACNET enum value to BACNET in integration_reports.connection_type
--
-- Context: The ConnectionType enum in app/models/integration.py renamed NIAGARA_BACNET
-- from "niagara_bacnet" to "bacnet" for consistency with the brand-agnostic probe naming
-- convention (BACnet is a standard protocol, not a brand).
--
-- Verify current distribution BEFORE updating:
-- SELECT connection_type, count(*)
-- FROM integration_reports
-- GROUP BY connection_type;

-- Perform the rename
UPDATE integration_reports
SET connection_type = 'bacnet'
WHERE connection_type = 'niagara_bacnet';

-- Verify no stale records remain
SELECT connection_type, count(*)
FROM integration_reports
GROUP BY connection_type;
