-- =============================================================================
-- Migration 015 — estende `renovation_level` para 7 níveis
-- =============================================================================
--   Adiciona dois níveis intermediários abaixo do "basic" (R$ 500/m²):
--     * cosmetic — R$ 150/m² (só pintura/limpeza)
--     * light    — R$ 300/m² (pintura + pequenos reparos)
--
--   Mantém os 5 níveis anteriores (none/basic/moderate/full/premium) —
--   análises antigas continuam válidas.
--
--   O CHECK constraint da tabela `opportunity_analyses` (migration 005)
--   precisa ser substituído para aceitar os 2 novos valores. Sem isso,
--   o INSERT falha com erro 23514:
--
--      new row for relation "opportunity_analyses" violates check
--      constraint "opportunity_analyses_renovation_level_check"
--
-- Idempotente.
-- =============================================================================

-- DROP do constraint antigo (se existir) e CREATE do novo.
alter table public.opportunity_analyses
    drop constraint if exists opportunity_analyses_renovation_level_check;

alter table public.opportunity_analyses
    add constraint opportunity_analyses_renovation_level_check
    check (renovation_level in (
        'none', 'cosmetic', 'light', 'basic', 'moderate', 'full', 'premium'
    ));

comment on column public.opportunity_analyses.renovation_level is
    'Nível de reforma escolhido pelo usuário no AGENTE 3. R$/m² associados '
    'estão em opportunity/assumptions.RENOVATION_PER_M2: none=0, '
    'cosmetic=150, light=300, basic=500 (default), moderate=1000, '
    'full=1500, premium=2500.';
