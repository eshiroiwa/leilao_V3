-- =============================================================================
-- AGENTE 4 — Deep Analysis (análise aprofundada do imóvel + bairro)
--
-- Tabela com workflow assíncrono: o POST cria uma row em 'pending' e dispara
-- a tarefa em background; o frontend faz polling em GET /deep-analyses/{id}
-- até `status` virar 'completed' ou 'failed'.
--
-- Dimensões cobertas (8): demografia, liquidez, outlier, flipping/teto,
-- tendência de preço, amenidades, riscos urbanos, histórico de leilão.
--
-- A dimensão "segurança por bairro" foi DESCARTADA: dados oficiais brasileiros
-- não descem ao nível de bairro de forma confiável. Decisão consciente de
-- não vender pseudo-precisão.
-- =============================================================================
create table if not exists public.deep_analyses (
  id                       uuid primary key default gen_random_uuid(),
  property_id              uuid not null references public.properties(id) on delete cascade,
  -- Liga à análise de oportunidade que disparou o estudo (opcional).
  opportunity_analysis_id  uuid references public.opportunity_analyses(id) on delete set null,
  agent_run_id             uuid references public.agent_runs(id) on delete set null,

  -- ----- Workflow assíncrono ------------------------------------------------
  status                   text not null default 'pending'
                              check (status in ('pending','running','completed','failed')),
  error_message            text,
  started_at               timestamptz,
  completed_at             timestamptz,
  duration_ms              integer,

  -- ----- Demografia / liquidez ----------------------------------------------
  city_population          integer,
  city_population_year     integer,
  city_population_source   text,
  liquidity_score          smallint check (liquidity_score between 1 and 5),
  liquidity_confidence     text check (liquidity_confidence in ('HIGH','MEDIUM','LOW')),
  liquidity_evidence       jsonb,

  -- ----- Outlier vs vizinhança ----------------------------------------------
  is_outlier_size          boolean,
  is_outlier_price         boolean,
  size_zscore              numeric(6,2),
  price_zscore             numeric(6,2),
  outlier_evidence         jsonb,

  -- ----- Teto / house flipping ---------------------------------------------
  neighborhood_price_max   numeric(14,2),
  neighborhood_price_p90   numeric(14,2),
  neighborhood_ppm2_p90    numeric(10,2),
  flipping_potential_score smallint check (flipping_potential_score between 1 and 5),
  flipping_evidence        jsonb,

  -- ----- Tendência de preço (12 m) ------------------------------------------
  price_trend_12m_pct      numeric(6,2),
  price_trend_confidence   text check (price_trend_confidence in ('HIGH','MEDIUM','LOW')),
  price_trend_evidence     jsonb,

  -- ----- Amenidades (Google Places) -----------------------------------------
  nearest_metro_m          integer,
  nearest_school_m         integer,
  nearest_hospital_m       integer,
  amenities_evidence       jsonb,

  -- ----- Riscos urbanos ------------------------------------------------------
  urban_risks              jsonb,

  -- ----- Histórico de leilão -------------------------------------------------
  prior_auction_count      integer,
  prior_auction_evidence   jsonb,

  -- ----- Síntese (LLM consolidador) -----------------------------------------
  overall_score            smallint check (overall_score between 1 and 5),
  summary_text             text,
  red_flags                jsonb,
  green_flags              jsonb,
  recommendations          jsonb,

  -- ----- Auditoria -----------------------------------------------------------
  raw_findings             jsonb,
  source_documents         jsonb,
  cost_estimate_usd        numeric(10,4),
  firecrawl_calls          smallint not null default 0,
  llm_calls                smallint not null default 0,

  created_at               timestamptz not null default now()
);

create index if not exists idx_deep_analyses_property
  on public.deep_analyses (property_id, created_at desc);
create index if not exists idx_deep_analyses_status
  on public.deep_analyses (status);
-- Permite achar a "última completada" rapidamente para fins de cache.
create index if not exists idx_deep_analyses_property_completed
  on public.deep_analyses (property_id, created_at desc) where status = 'completed';

-- RLS
alter table public.deep_analyses enable row level security;
drop policy if exists "public read deep_analyses" on public.deep_analyses;
create policy "public read deep_analyses" on public.deep_analyses
  for select using (true);
