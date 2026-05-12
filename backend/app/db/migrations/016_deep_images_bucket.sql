-- =============================================================================
-- Migration 016 — bucket Storage `deep-images` (AGENTE 4)
-- =============================================================================
--   Cria o bucket Supabase Storage onde o nó CONDITION ASSESSMENT do Agente 4
--   persiste o pacote visual da análise:
--
--     deep-images/{property_id}/{analysis_id}/{slot}.jpg
--
--   Slots: aerial, sv_front, sv_left, sv_right, sv_back, listing.
--
--   Bucket é PÚBLICO (somente leitura para anônimos) — os URLs são exibidos
--   no DeepAnalysisCard do frontend. Escrita só via service_role (backend).
--
-- Idempotente.
-- =============================================================================

-- 1. Cria (ou ignora se já existe) o bucket público.
insert into storage.buckets (id, name, public)
values ('deep-images', 'deep-images', true)
on conflict (id) do update
  set public = excluded.public;

-- 2. Policy de leitura anônima — qualquer um pode baixar (URLs são públicas).
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'deep-images public read'
  ) then
    create policy "deep-images public read"
      on storage.objects for select
      using (bucket_id = 'deep-images');
  end if;
end$$;

-- 3. Escrita: só `service_role` (backend). O cliente Supabase já usa
--    a chave service_role no backend, então NÃO precisamos de policy aberta
--    para insert/update — RLS bloqueia anônimos e service_role faz bypass.
