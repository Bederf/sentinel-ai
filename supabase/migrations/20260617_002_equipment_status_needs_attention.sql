ALTER TABLE public.equipment
DROP CONSTRAINT IF EXISTS equipment_status_check;

ALTER TABLE public.equipment
ADD CONSTRAINT equipment_status_check
CHECK (
  status = ANY (
    ARRAY[
      'normal'::text,
      'warning'::text,
      'critical'::text,
      'offline'::text,
      'maintenance'::text,
      'needs_attention'::text,
      'unknown'::text
    ]
  )
);
