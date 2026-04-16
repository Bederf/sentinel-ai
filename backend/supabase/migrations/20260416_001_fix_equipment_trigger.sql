-- Migration 20260416_001: Fix equipment trigger to use site_id instead of building_id
--
-- Problem: equipment table has site_id column (not building_id) after buildings→sites rename.
-- The update_building_equipment_counts trigger still references OLD/NEW.building_id which
-- causes ALL equipment updates to fail with: record "old" has no field "building_id"
--
-- Fix: Drop the broken trigger. The equipment_count column on buildings/sites is also
-- maintained by a PostgreSQL trigger (trigger_maintain_equipment_count) that uses site_id.

BEGIN;

-- Drop the broken trigger and function
DROP TRIGGER IF EXISTS trigger_update_building_equipment_counts ON equipment;
DROP FUNCTION IF EXISTS update_building_equipment_counts();

COMMIT;

-- Verify: equipment_count on buildings should still be maintained automatically
-- If no such trigger exists, create one using the correct site_id column
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.triggers
    WHERE trigger_name = 'trigger_maintain_equipment_count'
    AND event_object_table = 'equipment'
  ) THEN
    -- Create the correct trigger using site_id
    CREATE OR REPLACE FUNCTION maintain_equipment_count()
    RETURNS TRIGGER AS $$
    BEGIN
      IF TG_OP = 'INSERT' THEN
        UPDATE buildings SET equipment_count = equipment_count + 1 WHERE id = NEW.site_id;
        RETURN NEW;
      ELSIF TG_OP = 'DELETE' THEN
        UPDATE buildings SET equipment_count = GREATEST(equipment_count - 1, 0) WHERE id = OLD.site_id;
        RETURN OLD;
      ELSIF TG_OP = 'UPDATE' AND OLD.site_id != NEW.site_id THEN
        UPDATE buildings SET equipment_count = GREATEST(equipment_count - 1, 0) WHERE id = OLD.site_id;
        UPDATE buildings SET equipment_count = equipment_count + 1 WHERE id = NEW.site_id;
        RETURN NEW;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trigger_maintain_equipment_count
      AFTER INSERT OR UPDATE OR DELETE ON equipment
      FOR EACH ROW EXECUTE FUNCTION maintain_equipment_count();
  END IF;
END;
$$;
