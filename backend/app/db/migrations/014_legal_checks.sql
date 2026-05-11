-- =============================================================================
-- Migration 014 — `legal_checks`: histórico de verificações jurídicas
-- =============================================================================
--   Persistência do resultado do Agente Legal:
--     * CNJ DataJud (processos do proprietário/executado);
--     * ONR (matrícula — stub por ora, integração paga sob demanda).
--
--   Modelo "uma row por execução" — não sobrescrevemos verificações
--   anteriores. Isso permite ver evolução temporal (ex.: novo processo
--   surgiu entre a 1ª e a 2ª praça do leilão).
--
--   Campos jsonb evitam expansão de schema quando o Agente Legal
--   ganhar novas fontes (Escavador, JUDIT, GeoSampa fiscal etc.).
--
-- Idempotente.
-- =============================================================================
create table if not exists public.legal_checks (
    id                   uuid primary key default gen_random_uuid(),
    property_id          uuid not null references public.properties(id) on delete cascade,
    started_at           timestamptz not null default now(),
    completed_at         timestamptz,
    duration_ms          integer,

    -- Snapshot completo do resultado (LegalCheckResult.model_dump).
    owner_processes      jsonb not null default '{}'::jsonb,
    matricula_check      jsonb not null default '{}'::jsonb,
    has_critical_findings boolean not null default false,
    critical_findings    jsonb not null default '[]'::jsonb,

    created_at           timestamptz not null default now()
);

comment on table public.legal_checks is
    'Verificações jurídicas (CNJ DataJud + ONR stub) por property. Modelo '
    '"uma row por execução" — preserva histórico para ver evolução entre '
    'execuções da mesma property (ex.: novo processo surgiu).';

-- Lookup mais comum: última verificação de uma property.
create index if not exists ix_legal_checks_property_created
    on public.legal_checks (property_id, created_at desc);

-- Filtro útil: listar todas as properties com red flag crítico.
create index if not exists ix_legal_checks_critical
    on public.legal_checks (property_id)
    where has_critical_findings;
