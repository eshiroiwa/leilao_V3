-- =============================================================================
-- Migration 013 — identificadores jurídicos/registrais em `properties`
-- =============================================================================
--   Adiciona 4 colunas que viabilizam consultas externas futuras:
--
--     * matricula             — número da matrícula no CRI
--     * registry_office       — nome do Cartório de Registro de Imóveis
--     * owner_cpf_cnpj        — documento do proprietário/executado (só dígitos)
--     * inscricao_municipal   — inscrição IPTU / SQL (SP) / cadastro municipal
--
--   Habilita:
--     - CNJ DataJud (consulta processos por CPF/CNPJ)
--     - ONR (certidão de matrícula via Operador Nacional do Registro)
--     - GeoSampa e congêneres (valor venal por inscrição municipal)
--
--   Idempotente — `IF NOT EXISTS` em cada coluna.
--
--   O Agente Deep já lê `prop.get("registry_number") or prop.get("matricula")`
--   em `agents/deep/service.py:206`, então a coluna `matricula` é o nome
--   esperado pelo consumidor.
-- =============================================================================
alter table public.properties
  add column if not exists matricula            text,
  add column if not exists registry_office      text,
  add column if not exists owner_cpf_cnpj       text,
  add column if not exists inscricao_municipal  text;

-- Constraint suave: CPF (11) ou CNPJ (14) — apenas dígitos. Aceita NULL.
-- Não usamos CHECK estrito (variações com pontuação podem persistir
-- durante migração); validação rigorosa fica no Pydantic schema.
comment on column public.properties.owner_cpf_cnpj is
  'CPF (11 dígitos) ou CNPJ (14 dígitos) do proprietário/executado — '
  'somente dígitos, sem pontuação. Usado pelo Agente Legal para '
  'consultar processos no CNJ DataJud.';

comment on column public.properties.matricula is
  'Número da matrícula do imóvel no Cartório de Registro de Imóveis '
  '(CRI). Usado pelo Agente Legal para consultar a matrícula no ONR.';

comment on column public.properties.registry_office is
  'Nome ou identificador do Cartório de Registro de Imóveis onde a '
  'matrícula está registrada (texto livre, sem normalização).';

comment on column public.properties.inscricao_municipal is
  'Inscrição imobiliária municipal — em SP, formato Setor/Quadra/Lote. '
  'Habilita consulta a portais municipais (GeoSampa etc.) para valor '
  'venal e dados de IPTU corrente.';

-- Índice em owner_cpf_cnpj para lookup eficiente quando consultarmos
-- DataJud em batch ("todos os imóveis do mesmo executado").
create index if not exists ix_properties_owner_cpf_cnpj
  on public.properties (owner_cpf_cnpj)
  where owner_cpf_cnpj is not null;
