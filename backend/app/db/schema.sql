-- =============================================================================
-- Leilão IA v3 — Schema base (PostgreSQL 15 / Supabase)
-- Execute este arquivo no SQL Editor do Supabase.
-- Idempotente: pode ser rodado várias vezes sem efeitos colaterais.
-- =============================================================================

-- ---------- Extensões ----------
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";
create extension if not exists "postgis";

-- ---------- Função utilitária para updated_at ----------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- =============================================================================
-- Tabela: auctioneers (leiloeiros)
-- =============================================================================
create table if not exists public.auctioneers (
  id           uuid primary key default gen_random_uuid(),
  slug         text not null unique,                -- ex: 'zuk', 'mega-leiloes'
  name         text not null,
  base_url     text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

drop trigger if exists trg_auctioneers_updated on public.auctioneers;
create trigger trg_auctioneers_updated
before update on public.auctioneers
for each row execute function public.set_updated_at();

-- Seed básico (idempotente). On conflict atualiza name/base_url para refletir
-- ajustes futuros sem precisar limpar a tabela manualmente.
insert into public.auctioneers (slug, name, base_url) values
  ('zuk',          'Zuk Leilões',           'https://www.portalzuk.com.br'),
  ('mega-leiloes', 'Mega Leilões',          'https://www.megaleiloes.com.br'),
  ('sodre-santoro','Sodré Santoro',         'https://www.sodresantoro.com.br'),
  ('biasi',        'Biasi Leilões',         'https://www.biasileiloes.com.br')
on conflict (slug) do update
  set name     = excluded.name,
      base_url = excluded.base_url;

-- =============================================================================
-- Tabela: properties (imóveis extraídos pelo Agente 1)
-- =============================================================================
create table if not exists public.properties (
  id                       uuid primary key default gen_random_uuid(),

  -- Origem
  source_url               text not null unique,
  auctioneer_id            uuid references public.auctioneers(id) on delete set null,
  auctioneer_lot_id        text,                                    -- nº interno do lote no leiloeiro

  -- Identificação
  title                    text,
  description              text,
  property_type            text,                                    -- apartamento, casa, terreno, comercial...

  -- Endereço normalizado (Google Address Validation)
  address_full             text,                                    -- linha completa formatada
  street                   text,
  number                   text,
  complement               text,
  neighborhood             text,
  city                     text,
  state                    text,                                    -- UF (2 letras)
  postal_code              text,                                    -- CEP
  country                  text default 'BR',

  -- Geolocalização (PostGIS)
  location                 geography(Point, 4326),                  -- (lng lat)
  -- latitude/longitude derivadas de `location` (sempre coerentes; evita
  -- decodificar EWKB no frontend).
  latitude                 double precision generated always as (
                             ST_Y(location::geometry)
                           ) stored,
  longitude                double precision generated always as (
                             ST_X(location::geometry)
                           ) stored,
  google_place_id          text,
  geocoding_confidence     text,                                    -- HIGH | MEDIUM | LOW
  address_validation       jsonb,                                   -- payload bruto da API

  -- Características físicas
  area_total_m2            numeric(10,2),
  area_built_m2            numeric(10,2),
  bedrooms                 smallint,
  bathrooms                smallint,
  parking_spaces           smallint,

  -- Valores do leilão
  appraisal_value          numeric(14,2),                           -- valor de avaliação
  minimum_bid_first        numeric(14,2),                           -- 1ª praça
  minimum_bid_second       numeric(14,2),                           -- 2ª praça
  current_bid              numeric(14,2),
  currency                 char(3) default 'BRL',

  -- Datas do leilão
  first_auction_at         timestamptz,
  second_auction_at        timestamptz,

  -- Jurídico (preenchido por agentes futuros)
  legal_status             text,                                    -- judicial | extrajudicial | particular
  occupancy_status         text,                                    -- desocupado | ocupado | desconhecido
  encumbrances             jsonb,                                   -- ônus, dívidas, ações...

  -- Bruto / auditoria
  raw_markdown             text,                                    -- markdown vindo do Firecrawl
  raw_extraction           jsonb,                                   -- JSON completo extraído pelo LLM
  pricing_meta             jsonb,                                   -- output de agentes de precificação

  status                   text not null default 'scraped',         -- scraped | enriched | priced | error
  errors                   jsonb,

  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

drop trigger if exists trg_properties_updated on public.properties;
create trigger trg_properties_updated
before update on public.properties
for each row execute function public.set_updated_at();

-- ---------- Índices ----------
create index if not exists idx_properties_auctioneer       on public.properties(auctioneer_id);
create index if not exists idx_properties_status           on public.properties(status);
create index if not exists idx_properties_city_state       on public.properties(city, state);
create index if not exists idx_properties_first_auction_at on public.properties(first_auction_at desc);
create index if not exists idx_properties_location_gix     on public.properties using gist(location);
create index if not exists idx_properties_lat_lng          on public.properties (latitude, longitude);
create index if not exists idx_properties_raw_extraction   on public.properties using gin(raw_extraction);
create index if not exists idx_properties_encumbrances     on public.properties using gin(encumbrances);

-- =============================================================================
-- Tabela: agent_runs (auditoria de execuções dos agentes)
-- =============================================================================
create table if not exists public.agent_runs (
  id              uuid primary key default gen_random_uuid(),
  agent_name      text not null,                                  -- 'scraper', 'pricer', ...
  property_id     uuid references public.properties(id) on delete set null,
  input           jsonb,
  output          jsonb,
  status          text not null default 'running',                -- running | success | failed
  error_message   text,
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  duration_ms     integer
);

create index if not exists idx_agent_runs_agent      on public.agent_runs(agent_name);
create index if not exists idx_agent_runs_property   on public.agent_runs(property_id);
create index if not exists idx_agent_runs_status     on public.agent_runs(status);
create index if not exists idx_agent_runs_started_at on public.agent_runs(started_at desc);

-- =============================================================================
-- Row Level Security (placeholder — refine conforme regras de auth do projeto)
-- =============================================================================
alter table public.auctioneers enable row level security;
alter table public.properties  enable row level security;
alter table public.agent_runs  enable row level security;

-- Política de leitura pública (ajuste conforme necessidade real)
drop policy if exists "public read auctioneers" on public.auctioneers;
create policy "public read auctioneers" on public.auctioneers
  for select using (true);

drop policy if exists "public read properties" on public.properties;
create policy "public read properties" on public.properties
  for select using (true);

-- Escritas só via service_role (a API roda como service_role no backend).
