-- =====================================================
-- Migration 212: Equipment replacement tracking
-- =====================================================

ALTER TABLE equipment
ADD COLUMN IF NOT EXISTS replaced_on date DEFAULT NULL,
ADD COLUMN IF NOT EXISTS replacement_notes text DEFAULT NULL;
