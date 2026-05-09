-- =============================================================================
-- Migration 009 — `condo_name` em `properties`
-- =============================================================================
--   O Agente 1 raramente consegue extrair o nome do prédio do edital de
--   leilão (a Caixa, por exemplo, costuma listar só o endereço). Mas o
--   nome do condomínio é o sinal mais forte que existe para o AGENTE 2:
--   anúncios do MESMO prédio têm R$/m² muito mais consistente do que
--   anúncios da mesma rua/bairro (que misturam empreendimentos diferentes).
--
--   Esta migration adiciona o campo `condo_name` em `properties` para
--   que:
--
--     1. O usuário possa preencher manualmente quando souber (UI),
--     2. O Agente 1 possa preencher quando conseguir extrair (futuro),
--     3. O Agente 2 use esse valor como query primária ("condo strategy")
--        e como bônus forte no scoring/pricing.
--
-- Idempotente.
-- =============================================================================
alter table public.properties
  add column if not exists condo_name text;

comment on column public.properties.condo_name
  is 'Nome do condomínio/edifício do imóvel-alvo. Quando preenchido, o '
     'AGENTE 2 prioriza listings do MESMO prédio nos comparáveis '
     '(scoring + pricing).';

create index if not exists idx_properties_condo_name
  on public.properties (condo_name)
  where condo_name is not null;
