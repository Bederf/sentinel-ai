-- Migration 081: Add NMD and Tariff Configuration to Buildings Table
-- Purpose: Store extracted NMD limits and demand charges from municipal bills
-- Allows Phase 081 coordinator to use real data instead of hardcoded values
-- Date: 2026-02-12

-- Add columns to buildings table for NMD and tariff data
ALTER TABLE buildings
ADD COLUMN IF NOT EXISTS nmd_limit_kva FLOAT COMMENT 'Notified Maximum Demand (kVA) from municipal contract',
ADD COLUMN IF NOT EXISTS demand_charge_per_kva FLOAT COMMENT 'Demand charge rate (R/kVA) from municipal tariff',
ADD COLUMN IF NOT EXISTS electricity_provider TEXT COMMENT 'Electricity provider (e.g., City Power, Eskom, Ekurhuleni)',
ADD COLUMN IF NOT EXISTS billing_cycle_start_date DATE COMMENT 'Start of billing cycle (for demand tracking)',
ADD COLUMN IF NOT EXISTS billing_cycle_end_date DATE COMMENT 'End of billing cycle',
ADD COLUMN IF NOT EXISTS bill_last_uploaded_at TIMESTAMP COMMENT 'When the most recent bill was uploaded and processed',
ADD COLUMN IF NOT EXISTS bill_document_path TEXT COMMENT 'Storage path to the uploaded municipal bill PDF',
ADD COLUMN IF NOT EXISTS nmd_extracted_from_bill BOOLEAN DEFAULT false COMMENT 'Flag indicating NMD was extracted from bill (vs hardcoded)',
ADD COLUMN IF NOT EXISTS tariff_band TEXT COMMENT 'Current tariff band (e.g., peak, off-peak, shoulder)';

-- Create index on buildings.nmd_limit_kva for demand coordinator queries
CREATE INDEX IF NOT EXISTS idx_buildings_nmd_limit ON buildings(nmd_limit_kva) WHERE nmd_limit_kva IS NOT NULL;

-- Create index on buildings.bill_last_uploaded_at for bill ingestion tracking
CREATE INDEX IF NOT EXISTS idx_buildings_bill_uploaded ON buildings(bill_last_uploaded_at) WHERE bill_last_uploaded_at IS NOT NULL;

-- Add comments to explain the fields
COMMENT ON COLUMN buildings.nmd_limit_kva IS 'Notified Maximum Demand limit in kVA extracted from municipal electricity bill. Used by peak demand coordinator to determine headroom alerts.';
COMMENT ON COLUMN buildings.demand_charge_per_kva IS 'Monthly demand charge rate (R/kVA) extracted from municipal tariff. Used to calculate peak shaving cost savings.';
COMMENT ON COLUMN buildings.nmd_extracted_from_bill IS 'True if NMD value was extracted from uploaded municipal bill; False if using default/manual value.';

-- Populate default NMD for existing buildings (Site-002 = 6000 kVA, Site-005 = 8000 kVA)
UPDATE buildings
SET 
  nmd_limit_kva = CASE 
    WHEN code = 'S002' THEN 6000.0
    WHEN code = 'site-005' THEN 8000.0
    ELSE 5000.0
  END,
  demand_charge_per_kva = 155.50,  -- City Power rate 2026
  electricity_provider = 'City Power',
  nmd_extracted_from_bill = false
WHERE nmd_limit_kva IS NULL;

-- Log the migration
INSERT INTO schema_migrations (name, description, executed_at)
VALUES (
  '081_add_nmd_and_tariff_to_buildings',
  'Add NMD limit and tariff configuration columns to buildings table for real municipal bill data integration',
  NOW()
) ON CONFLICT DO NOTHING;
