-- =============================================================================
-- Migration 010 — `auctioneer_name` em `properties`
-- =============================================================================
--   No portal da Caixa (`venda-imoveis.caixa.gov.br`), nem todo lote tem
--   leiloeiro designado. A presença do leiloeiro é a regra de negócio
--   que distingue:
--
--     * Lote COM "Leiloeiro(a): FULANO" no markdown → tem comissão (5%
--       padrão histórico — Decreto 21.981/1932).
--     * Lote em "Compra Direta" / "Venda Online" → SEM leiloeiro,
--       SEM comissão.
--
--   Hoje só populamos `auctioneer_id` para os portais que conhecemos
--   pela tabela `auctioneers` (Zuk, Mega, Biasi, Sodré-Santoro). Para
--   leiloeiros pessoa-física que assinam editais Caixa precisamos de
--   um campo livre. Esta migration adiciona `auctioneer_name text`,
--   preenchido pelo Agente 1 quando o markdown contiver o padrão
--   "Leiloeiro(a): …".
--
--   Quando `auctioneer_id` está populado (portal conhecido), o nome
--   pode ficar `null` — a presença do `auctioneer_id` já é sinal de
--   que existe leiloeiro/comissão. O AGENTE 3 trata as duas colunas
--   como sinais alternativos.
--
-- Idempotente.
-- =============================================================================
alter table public.properties
  add column if not exists auctioneer_name text;

comment on column public.properties.auctioneer_name
  is 'Nome do leiloeiro extraído do edital (texto livre). Sinal usado '
     'pelo AGENTE 3 para decidir se há comissão de leiloeiro. Útil '
     'principalmente para lotes Caixa, onde nem todo edital tem '
     'leiloeiro designado e o `auctioneer_id` permanece NULL.';
