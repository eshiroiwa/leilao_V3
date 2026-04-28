-- =============================================================================
-- Migration 002 — adiciona colunas latitude/longitude geradas a partir de `location`.
-- Idempotente. Rode no SQL Editor do Supabase.
-- =============================================================================

alter table public.properties
  add column if not exists latitude  double precision generated always as (
    ST_Y(location::geometry)
  ) stored,
  add column if not exists longitude double precision generated always as (
    ST_X(location::geometry)
  ) stored;

create index if not exists idx_properties_lat_lng
  on public.properties (latitude, longitude);
