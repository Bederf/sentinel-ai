-- Solar schema for site configs and assets

create table if not exists public.solar_sites (
  site_id text primary key,
  site_name text not null,
  latitude numeric,
  longitude numeric,
  created_at timestamptz not null default now()
);

create table if not exists public.solar_plants (
  plant_id text primary key,
  site_id text not null references public.solar_sites(site_id) on delete cascade,
  name text not null,
  capacity_kwp numeric,
  panel_count integer,
  panel_model text,
  panel_rating_w numeric,
  commissioning_date date,
  orientation numeric,
  tilt numeric
);

create table if not exists public.solar_inverters (
  inverter_id text primary key,
  site_id text not null references public.solar_sites(site_id) on delete cascade,
  plant_id text not null references public.solar_plants(plant_id) on delete cascade,
  name text not null,
  manufacturer text,
  model text,
  rated_kva numeric,
  mppt_count integer,
  protocol text,
  ip text,
  port integer,
  unit_id integer,
  strings_per_mppt integer,
  panels_per_string integer
);

create table if not exists public.solar_bess (
  bess_id text primary key,
  site_id text not null references public.solar_sites(site_id) on delete cascade,
  container_id text,
  name text,
  manufacturer text,
  model text,
  capacity_kwh numeric,
  rated_power_kw numeric,
  rack_count integer,
  cell_chemistry text,
  protocol text
);

create table if not exists public.solar_meters (
  meter_id text primary key,
  site_id text not null references public.solar_sites(site_id) on delete cascade,
  name text not null,
  manufacturer text,
  model text,
  protocol text,
  ip text,
  port integer
);

create index if not exists idx_solar_plants_site on public.solar_plants(site_id);
create index if not exists idx_solar_inverters_site on public.solar_inverters(site_id);
create index if not exists idx_solar_inverters_plant on public.solar_inverters(plant_id);
create index if not exists idx_solar_bess_site on public.solar_bess(site_id);
create index if not exists idx_solar_meters_site on public.solar_meters(site_id);
