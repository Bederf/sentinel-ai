-- Migration: 214_add_work_order_notes_column
-- Add missing notes column to work_orders for technician guidance

ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS notes TEXT;

-- Reload PostgREST schema cache so the column is immediately visible
NOTIFY pgrst, 'reload schema';
