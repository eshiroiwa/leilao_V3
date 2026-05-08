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
  image_url                text,                                    -- 1ª foto do imóvel (extraída pelo Agente 1)

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

  -- Custos declarados no edital (extraídos pelo Agente 1 quando disponíveis;
  -- usados pelo Agente 3 com fallback para input manual no UI).
  iptu_arrears             numeric(14,2),                           -- IPTU em atraso, BRL
  condo_arrears            numeric(14,2),                           -- condomínio em atraso, BRL
  auctioneer_fee_pct       numeric(5,4),                            -- comissão leiloeiro, 0..1

  -- Custos do edital (extraídos pelo Agente 1 quando disponíveis;
  -- alimentam a análise financeira do Agente 3).
  iptu_arrears             numeric(14,2),                           -- IPTU atrasado (BRL)
  condo_arrears            numeric(14,2),                           -- condomínio atrasado (BRL)
  auctioneer_fee_pct       numeric(6,4),                            -- 0.05 = 5% (NULL = default)

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
-- AGENTE 2 — Comparáveis (CMA)
-- =============================================================================
-- listings → anúncios coletados de portais (VivaReal/ZAP)
create table if not exists public.listings (
  id                       uuid primary key default gen_random_uuid(),
  source                   text not null,
  source_url               text not null unique,
  external_id              text,
  property_type            text,
  area_total_m2            numeric(10,2),
  area_useful_m2           numeric(10,2),
  bedrooms                 smallint,
  bathrooms                smallint,
  parking_spaces           smallint,
  condo_name               text,
  amenities                jsonb,
  address_full             text,
  street                   text,
  number                   text,
  neighborhood             text,
  city                     text,
  state                    text,
  postal_code              text,
  location                 geography(Point, 4326),
  latitude                 double precision generated always as (ST_Y(location::geometry)) stored,
  longitude                double precision generated always as (ST_X(location::geometry)) stored,
  geocoding_confidence     text,
  listed_price             numeric(14,2),
  monthly_condo_fee        numeric(10,2),
  iptu                     numeric(10,2),
  currency                 char(3) default 'BRL',
  photos_count             smallint,
  advertiser_type          text,
  reliability_score        numeric(4,3),
  listed_at                date,
  scraped_at               timestamptz not null default now(),
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

create index if not exists idx_listings_location_gix      on public.listings using gist(location);
create index if not exists idx_listings_city_neighborhood on public.listings(city, neighborhood, property_type);
create index if not exists idx_listings_scraped_at        on public.listings(scraped_at desc);
create index if not exists idx_listings_condo_name        on public.listings(condo_name) where condo_name is not null;
create index if not exists idx_listings_lat_lng           on public.listings(latitude, longitude);
-- Dedup canônica por anúncio: (source, external_id) é o id real do
-- anúncio no portal. Quando ele existe, NUNCA permitimos duas rows.
-- (PARCIAL — quando external_id é NULL, só o UNIQUE em source_url protege.)
create unique index if not exists uq_listings_source_external_id
  on public.listings (source, external_id)
  where external_id is not null;

-- valuations → resultado de cada CMA
create table if not exists public.valuations (
  id                       uuid primary key default gen_random_uuid(),
  property_id              uuid not null references public.properties(id) on delete cascade,
  agent_run_id             uuid references public.agent_runs(id) on delete set null,
  estimated_price          numeric(14,2),
  price_lower_bound        numeric(14,2),
  price_upper_bound        numeric(14,2),
  ppm2_estimated           numeric(10,2),
  confidence               text not null check (confidence in ('HIGH','MEDIUM','LOW','INSUFFICIENT')),
  method                   text,
  comparables_used         smallint not null default 0,
  comparables_rejected     smallint not null default 0,
  search_radius_m          integer,
  search_strategy          text,
  firecrawl_calls          smallint not null default 0,
  llm_calls                smallint not null default 0,
  cost_estimate_brl        numeric(10,4),
  metadata                 jsonb,
  errors                   jsonb,
  created_at               timestamptz not null default now()
);

create index if not exists idx_valuations_property   on public.valuations(property_id);
create index if not exists idx_valuations_created_at on public.valuations(created_at desc);
create index if not exists idx_valuations_confidence on public.valuations(confidence);

-- valuation_comparables → join (peso, distância, motivo)
create table if not exists public.valuation_comparables (
  valuation_id        uuid not null references public.valuations(id) on delete cascade,
  listing_id          uuid not null references public.listings(id)   on delete cascade,
  distance_m          numeric(10,2),
  similarity_score    numeric(4,3),
  weight              numeric(6,4),
  used                boolean not null default false,
  rejection_reason    text,
  primary key (valuation_id, listing_id)
);

create index if not exists idx_valcomp_listing on public.valuation_comparables(listing_id);

-- =============================================================================
-- AGENTE 3 — opportunity_analyses
-- =============================================================================
create table if not exists public.opportunity_analyses (
  id                  uuid primary key default gen_random_uuid(),

  property_id         uuid not null references public.properties(id)  on delete cascade,
  valuation_id        uuid          references public.valuations(id)  on delete set null,
  agent_run_id        uuid          references public.agent_runs(id)  on delete set null,

  buyer_type          text not null check (buyer_type in ('PF','PJ')),
  target_net_roi_pct  numeric(5,4) not null,
  renovation_level    text not null check (renovation_level in
                       ('none','basic','moderate','full','premium')),
  bid_amount          numeric(14,2) not null,
  other_costs         numeric(14,2) not null default 0,
  iptu_arrears        numeric(14,2) not null default 0,
  condo_arrears       numeric(14,2) not null default 0,

  scenarios           jsonb not null,
  max_bid_for_target  numeric(14,2),

  verdict             text not null check (verdict in
                       ('BOA_OPORTUNIDADE','BOA_COM_RESSALVAS','NEUTRO',
                        'INVIAVEL','INDETERMINADO')),
  warnings            jsonb,
  assumptions         jsonb not null,

  -- overrides do formulário (sale_price + alíquotas) para reproduzir a
  -- análise no frontend; opcional (analyses pré-migration têm null).
  input_overrides     jsonb,

  created_at          timestamptz not null default now()
);

create index if not exists idx_opp_analyses_property
  on public.opportunity_analyses (property_id, created_at desc);
create index if not exists idx_opp_analyses_verdict
  on public.opportunity_analyses (verdict);

-- =============================================================================
-- Row Level Security (placeholder — refine conforme regras de auth do projeto)
-- =============================================================================
alter table public.auctioneers           enable row level security;
alter table public.properties            enable row level security;
alter table public.agent_runs            enable row level security;
alter table public.listings              enable row level security;
alter table public.valuations            enable row level security;
alter table public.valuation_comparables enable row level security;
alter table public.opportunity_analyses  enable row level security;

-- Política de leitura pública (ajuste conforme necessidade real)
drop policy if exists "public read auctioneers" on public.auctioneers;
create policy "public read auctioneers" on public.auctioneers
  for select using (true);

drop policy if exists "public read properties" on public.properties;
create policy "public read properties" on public.properties
  for select using (true);

drop policy if exists "public read listings" on public.listings;
create policy "public read listings" on public.listings for select using (true);

drop policy if exists "public read valuations" on public.valuations;
create policy "public read valuations" on public.valuations for select using (true);

drop policy if exists "public read valuation_comparables" on public.valuation_comparables;
create policy "public read valuation_comparables" on public.valuation_comparables for select using (true);

drop policy if exists "public read opportunity_analyses" on public.opportunity_analyses;
create policy "public read opportunity_analyses" on public.opportunity_analyses for select using (true);

-- Escritas só via service_role (a API roda como service_role no backend).
