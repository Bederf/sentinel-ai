-- Create lifecycle_simulation_tasks table (replaces solar_annual_tasks for all simulations)
CREATE TABLE IF NOT EXISTS lifecycle_simulation_tasks (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  task_id TEXT UNIQUE NOT NULL,
  site_id TEXT NOT NULL,
  scenario TEXT NOT NULL,
  simulation_type TEXT NOT NULL DEFAULT 'lifecycle',
  status TEXT NOT NULL DEFAULT 'queued',
  progress_pct INTEGER DEFAULT 0,
  days_completed INTEGER DEFAULT 0,
  duration_minutes FLOAT DEFAULT 240.0,

  -- Checkpoint state for crash recovery
  state_snapshot JSONB,
  error_message TEXT,

  -- Timestamps
  created_at TIMESTAMP DEFAULT NOW(),
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_lifecycle_tasks_status ON lifecycle_simulation_tasks(status);
CREATE INDEX IF NOT EXISTS idx_lifecycle_tasks_site ON lifecycle_simulation_tasks(site_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_tasks_created ON lifecycle_simulation_tasks(created_at DESC);
