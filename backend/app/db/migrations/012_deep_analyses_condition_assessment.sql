-- =============================================================================
-- Migration 012 — `condition_assessment` jsonb em `deep_analyses`
-- =============================================================================
--   Coluna nova jsonb que persiste o resultado do nó CONDITION ASSESSMENT
--   (Vision LLM sobre foto do edital). Inclui:
--     * conservation_level: novo/bom/regular/mau/ruina
--     * suggested_renovation_level: none/basic/moderate/full/premium
--     * risk_flags: lista de itens problemáticos OBSERVADOS na foto
--     * confidence: HIGH/MEDIUM/LOW
--
--   A coluna é nullable — em deep_analyses antigas (rodadas antes da
--   feature) fica NULL e o frontend ignora.
--
-- Idempotente.
-- =============================================================================
alter table public.deep_analyses
  add column if not exists condition_assessment jsonb;

comment on column public.deep_analyses.condition_assessment is
  'Saída do nó Vision (GPT-4o multimodal) sobre image_url do property. '
  'Sinal opcional — NÃO sobrescreve renovation_level do Agente 3. Schema '
  'segue ConditionAssessmentResult (agents/deep/schemas.py).';
