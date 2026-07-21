-- Remove lifecycle_simulation_tasks from Supabase.
-- The lifecycle simulation is site-side runtime state, not a SENTINEL
-- operational table, and this table is not used by the active app code.

DROP TABLE IF EXISTS public.lifecycle_simulation_tasks;
