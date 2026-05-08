-- =============================================================================
-- Migration 004 — listings: dedup por (source, external_id)
-- =============================================================================
-- Garante que NUNCA exista mais de um listing para o MESMO anúncio (mesmo
-- portal + mesmo id no portal), independente da `source_url` (que pode mudar
-- por canonicalização, query strings, fallback synthetic vs URL real, etc.).
--
-- Por que parcial?
--   * `external_id` é NULL quando vem de batch extraction sem URL real
--     (cards antigos, fallback synthetic). Para esses, o UNIQUE em
--     `source_url` continua sendo a única defesa — não conseguimos forçar
--     unicidade global sem id do portal.
--
-- Idempotente: pode rodar quantas vezes precisar.
-- =============================================================================

-- ---------- Limpeza preventiva de duplicatas existentes ----------------------
-- Mantém a row MAIS RECENTE (created_at mais alto) por (source, external_id);
-- apaga as outras. Se você prefere validar antes, comente este bloco.
-- =============================================================================
with ranked as (
  select
    id,
    source,
    external_id,
    created_at,
    row_number() over (
      partition by source, external_id
      order by created_at desc, scraped_at desc, id
    ) as rn
  from public.listings
  where external_id is not null
),
to_delete as (
  select id from ranked where rn > 1
)
delete from public.listings
where id in (select id from to_delete);

-- ---------- Índice único parcial ---------------------------------------------
create unique index if not exists uq_listings_source_external_id
  on public.listings (source, external_id)
  where external_id is not null;

-- ---------- Índice de leitura para o lookup (source, external_id) ------------
-- O unique acima já é usado pelo planner, mas deixamos um índice explícito
-- para deixar a intenção clara em revisões.
create index if not exists idx_listings_source_external_id
  on public.listings (source, external_id)
  where external_id is not null;
