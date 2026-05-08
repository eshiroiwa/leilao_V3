-- =============================================================================
-- Migration 005 — AGENTE 3 (Análise de Oportunidade)
-- =============================================================================
--   1. Campos extras em `properties` que o AGENTE 1 passa a extrair do edital:
--        * iptu_arrears        (IPTU em atraso)
--        * condo_arrears       (condomínio em atraso)
--        * auctioneer_fee_pct  (% comissão do leiloeiro, quando declarada)
--   2. Tabela `opportunity_analyses` para persistir as análises rodadas.
--
-- Idempotente: pode rodar quantas vezes precisar.
-- =============================================================================

-- ---------- 1. Properties: novos campos opcionais --------------------------
alter table public.properties
  add column if not exists iptu_arrears        numeric(14,2);
alter table public.properties
  add column if not exists condo_arrears       numeric(14,2);
alter table public.properties
  add column if not exists auctioneer_fee_pct  numeric(5,4);  -- ex.: 0.0500 = 5%

comment on column public.properties.iptu_arrears
  is 'IPTU em atraso declarado no edital (BRL). null = não declarado.';
comment on column public.properties.condo_arrears
  is 'Condomínio em atraso declarado no edital (BRL). null = não declarado.';
comment on column public.properties.auctioneer_fee_pct
  is 'Comissão do leiloeiro declarada no edital (0..1). null = usar default da tabela de premissas.';


-- ---------- 2. opportunity_analyses ----------------------------------------
create table if not exists public.opportunity_analyses (
  id                       uuid primary key default gen_random_uuid(),

  property_id              uuid not null references public.properties(id) on delete cascade,
  valuation_id             uuid references public.valuations(id) on delete set null,
  agent_run_id             uuid references public.agent_runs(id) on delete set null,

  -- ========== Inputs do usuário (snapshot — para auditoria) ==========
  buyer_type               text not null check (buyer_type in ('PF','PJ')),
  target_net_roi_pct       numeric(5,4) not null,            -- 0..1, ex.: 0.40
  renovation_level         text not null check (renovation_level in
                              ('none','basic','moderate','full','premium')),
  bid_amount               numeric(14,2) not null,
  other_costs              numeric(14,2) not null default 0,
  iptu_arrears             numeric(14,2) not null default 0,
  condo_arrears            numeric(14,2) not null default 0,

  -- ========== Resultado (3 cenários) ==========
  -- scenarios = {
  --   "pessimista": {sale_price, investment, auctioneer_fee, itbi,
  --                  registration, iptu_arrears, condo_arrears,
  --                  renovation_cost, other_costs, total_acquisition_cost,
  --                  realtor_fee, gross_profit, income_tax, net_profit,
  --                  gross_roi_pct, net_roi_pct},
  --   "realista":   {...},
  --   "otimista":   {...}
  -- }
  scenarios                jsonb not null,

  -- Lance máximo para atingir o ROI alvo (cenário REALISTA)
  max_bid_for_target       numeric(14,2),

  -- ========== Parecer ==========
  verdict                  text not null check (verdict in
                            ('BOA_OPORTUNIDADE',
                             'BOA_COM_RESSALVAS',
                             'NEUTRO',
                             'INVIAVEL',
                             'INDETERMINADO')),
  warnings                 jsonb,            -- ["ônus declarado", "imóvel ocupado", ...]

  -- ========== Auditoria ==========
  -- Snapshot das alíquotas usadas: ITBI, registro, IR, comissão leiloeiro,
  -- R$/m² da reforma. Permite reproduzir o cálculo no futuro mesmo se as
  -- tabelas mudarem.
  assumptions              jsonb not null,

  created_at               timestamptz not null default now()
);

create index if not exists idx_opp_analyses_property      on public.opportunity_analyses(property_id);
create index if not exists idx_opp_analyses_created_at    on public.opportunity_analyses(created_at desc);
create index if not exists idx_opp_analyses_verdict       on public.opportunity_analyses(verdict);

-- ---------- RLS ----------
alter table public.opportunity_analyses enable row level security;

drop policy if exists "public read opportunity_analyses" on public.opportunity_analyses;
create policy "public read opportunity_analyses"
  on public.opportunity_analyses for select using (true);
