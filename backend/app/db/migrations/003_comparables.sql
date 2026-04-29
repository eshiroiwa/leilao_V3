-- =============================================================================
-- Migration 003 — AGENTE 2 (Comparáveis / Avaliação CMA)
-- =============================================================================
-- Adiciona três tabelas:
--   * listings              → anúncios coletados de portais (VivaReal/ZAP/...)
--   * valuations            → resultado de cada avaliação (CMA) de um property
--   * valuation_comparables → join (valuation × listing) com peso e razão
--
-- Idempotente: rode no SQL Editor do Supabase quantas vezes precisar.
-- =============================================================================

-- ---------- Pré-requisitos (já existem do schema base, mas garantimos) ------
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";
create extension if not exists "postgis";

-- =============================================================================
-- listings — anúncios de mercado (comparáveis-candidatos)
-- =============================================================================
create table if not exists public.listings (
  id                       uuid primary key default gen_random_uuid(),

  -- Origem
  source                   text not null,                              -- 'vivareal' | 'zap' | 'olx' | ...
  source_url               text not null unique,
  external_id              text,                                       -- id do anúncio no portal

  -- Características
  property_type            text,
  area_total_m2            numeric(10,2),
  area_useful_m2           numeric(10,2),
  bedrooms                 smallint,
  bathrooms                smallint,
  parking_spaces           smallint,
  condo_name               text,
  amenities                jsonb,                                      -- ["piscina","portaria 24h",...]

  -- Endereço
  address_full             text,
  street                   text,
  number                   text,
  neighborhood             text,
  city                     text,
  state                    text,
  postal_code              text,

  -- Geolocalização (mesmo padrão de properties: PostGIS + colunas geradas)
  location                 geography(Point, 4326),
  latitude                 double precision generated always as (
                              ST_Y(location::geometry)
                           ) stored,
  longitude                double precision generated always as (
                              ST_X(location::geometry)
                           ) stored,
  geocoding_confidence     text,                                       -- HIGH | MEDIUM | LOW | POSTAL_CODE | REJECTED

  -- Valores
  listed_price             numeric(14,2),
  monthly_condo_fee        numeric(10,2),
  iptu                     numeric(10,2),
  currency                 char(3) default 'BRL',

  -- Sinais
  photos_count             smallint,
  advertiser_type          text,                                       -- 'imobiliaria' | 'autonomo' | 'desconhecido'
  reliability_score        numeric(4,3),                               -- 0.000 a 1.000

  -- Datas
  listed_at                date,
  scraped_at               timestamptz not null default now(),

  -- Auditoria
  raw_markdown             text,
  raw_extraction           jsonb,
  errors                   jsonb,

  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

drop trigger if exists trg_listings_updated on public.listings;
create trigger trg_listings_updated
before update on public.listings
for each row execute function public.set_updated_at();

create index if not exists idx_listings_location_gix     on public.listings using gist(location);
create index if not exists idx_listings_city_neighborhood on public.listings(city, neighborhood, property_type);
create index if not exists idx_listings_scraped_at       on public.listings(scraped_at desc);
create index if not exists idx_listings_condo_name       on public.listings(condo_name) where condo_name is not null;
create index if not exists idx_listings_lat_lng          on public.listings(latitude, longitude);

-- =============================================================================
-- valuations — uma avaliação (CMA) de um imóvel num momento
-- =============================================================================
create table if not exists public.valuations (
  id                       uuid primary key default gen_random_uuid(),

  property_id              uuid not null references public.properties(id) on delete cascade,
  agent_run_id             uuid references public.agent_runs(id) on delete set null,

  -- Resultado
  estimated_price          numeric(14,2),
  price_lower_bound        numeric(14,2),
  price_upper_bound        numeric(14,2),
  ppm2_estimated           numeric(10,2),                              -- R$/m² mediano ponderado
  confidence               text not null check (confidence in
                             ('HIGH','MEDIUM','LOW','INSUFFICIENT')),
  method                   text,                                       -- 'weighted_median_ppm2' | ...

  -- Diagnóstico
  comparables_used         smallint not null default 0,
  comparables_rejected     smallint not null default 0,
  search_radius_m          integer,                                    -- raio final em metros
  search_strategy          text,                                       -- 'condo' | 'street' | 'neighborhood' | 'radius'

  -- Custo
  firecrawl_calls          smallint not null default 0,                -- total (search + scrape)
  llm_calls                smallint not null default 0,
  cost_estimate_brl        numeric(10,4),

  metadata                 jsonb,                                      -- detalhes livres
  errors                   jsonb,

  created_at               timestamptz not null default now()
);

create index if not exists idx_valuations_property    on public.valuations(property_id);
create index if not exists idx_valuations_created_at  on public.valuations(created_at desc);
create index if not exists idx_valuations_confidence  on public.valuations(confidence);

-- =============================================================================
-- valuation_comparables — join com peso, distância e motivo de aceite/rejeição
-- =============================================================================
create table if not exists public.valuation_comparables (
  valuation_id        uuid not null references public.valuations(id)  on delete cascade,
  listing_id          uuid not null references public.listings(id)    on delete cascade,

  distance_m          numeric(10,2),
  similarity_score    numeric(4,3),                                   -- 0–1
  weight              numeric(6,4),                                   -- peso final no cálculo
  used                boolean not null default false,                 -- true = entrou no cálculo
  rejection_reason    text,

  primary key (valuation_id, listing_id)
);

create index if not exists idx_valcomp_listing on public.valuation_comparables(listing_id);

-- =============================================================================
-- RLS
-- =============================================================================
alter table public.listings              enable row level security;
alter table public.valuations            enable row level security;
alter table public.valuation_comparables enable row level security;

drop policy if exists "public read listings" on public.listings;
create policy "public read listings" on public.listings for select using (true);

drop policy if exists "public read valuations" on public.valuations;
create policy "public read valuations" on public.valuations for select using (true);

drop policy if exists "public read valuation_comparables" on public.valuation_comparables;
create policy "public read valuation_comparables" on public.valuation_comparables for select using (true);
