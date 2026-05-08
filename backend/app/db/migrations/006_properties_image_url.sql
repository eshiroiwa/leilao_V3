-- =============================================================================
-- Migration 006 — AGENTE 1 captura a URL da foto principal do imóvel
-- =============================================================================
--   Adiciona `image_url` em `properties`. O Agente 1 escolhe a 1ª fotografia
--   do imóvel no markdown gerado pelo Firecrawl (ignorando logos, ícones, etc).
--   O frontend usa essa URL como thumbnail do card.
--
-- Idempotente.
-- =============================================================================
alter table public.properties
  add column if not exists image_url text;

comment on column public.properties.image_url
  is 'URL da imagem principal (1ª foto) do imóvel — capturada pelo Agente 1 do site do leiloeiro.';
