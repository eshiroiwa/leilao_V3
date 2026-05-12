-- =============================================================================
-- Migration 017 — coluna `neighborhood_class` em `deep_analyses` (AGENTE 4)
-- =============================================================================
--   Coluna nova JSONB que persiste o resultado do nó NEIGHBORHOOD CLASS:
--     * tier (A/B/C/D), tier_label (premium/médio-alto/médio/popular)
--     * target_ppm2_median, city_ppm2_brl, ratio
--     * competing_neighborhoods: lista de até 3 bairros próximos com
--       ppm² similar (nome, distância em km, ppm², n_listings)
--     * confidence (HIGH/MEDIUM/LOW), evidence (dict livre)
--
--   Schema segue NeighborhoodClassResult (agents/deep/schemas.py). A coluna
--   é nullable — análises antigas continuam válidas (campo vira null).
--
-- Idempotente.
-- =============================================================================
alter table public.deep_analyses
  add column if not exists neighborhood_class jsonb;

comment on column public.deep_analyses.neighborhood_class is
  'Saída do nó NEIGHBORHOOD CLASS: tier A/B/C/D do bairro-alvo (pela razão '
  'ppm²_bairro/ppm²_cidade FipeZAP), + até 3 bairros concorrentes com '
  'ppm² semelhante em raio 10km. Schema segue NeighborhoodClassResult '
  '(agents/deep/schemas.py).';
