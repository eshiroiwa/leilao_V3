-- =============================================================================
-- Migration 011 — `city_ppm2_stats`: histórico de preço médio por cidade
-- =============================================================================
--   Tabela alimentada pelo script ``backend/scripts/update_fipezap.py`` que
--   baixa o PDF mensal da FipeZAP (residencial venda) e parseia o ranking
--   de cidades. A FipeZAP cobre até 56 cidades, atualizado uma vez por mês.
--
--   Uso no balisador:
--     * Calibração de σ no Agente 2 (CMA) com base no preço médio da cidade.
--     * Sanity check: warning na CMA quando a mediana dos comparáveis distoa
--       em mais de 30% do FipeZAP da mesma cidade.
--     * Tendência: com vários meses, calcular variação a.a. e marcar
--       cidades em alta/baixa no Agente 4 (Deep).
--
--   `asof_year` + `asof_month` formam a chave temporal — preservamos o
--   histórico completo (não sobrescrevemos meses anteriores). Isso permite
--   reproduzir uma análise antiga consultando o snapshot daquela época.
--
-- Idempotente.
-- =============================================================================
create table if not exists public.city_ppm2_stats (
    city text not null,
    state text,
    mean_ppm2_brl numeric(12, 2) not null,
    asof_year smallint not null,
    asof_month smallint not null check (asof_month between 1 and 12),
    source text not null default 'fipezap',
    created_at timestamptz not null default now(),
    -- Chave composta: uma leitura por (cidade, UF, mês). Cidades homônimas
    -- em UFs diferentes (ex.: Campinas SP vs Campinas RJ) coexistem.
    primary key (city, state, asof_year, asof_month)
);

comment on table public.city_ppm2_stats is
    'Preço médio R$/m² por cidade extraído do PDF mensal FipeZAP residencial venda.';

comment on column public.city_ppm2_stats.mean_ppm2_brl is
    'Preço médio anunciado em R$/m² na cidade no mês de referência. NÃO confundir '
    'com índice (base 100) — apenas valores absolutos em BRL.';

-- Índice secundário pra lookup rápido por cidade ordenado por mês desc.
create index if not exists ix_city_ppm2_stats_city_asof
    on public.city_ppm2_stats (city, asof_year desc, asof_month desc);
