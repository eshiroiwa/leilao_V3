-- =============================================================================
-- Migration 023 — `document_analyses`: histórico de análises consolidadas
-- =============================================================================
--   Uma row por execução do endpoint POST /documents/analyze. O usuário
--   seleciona N documentos (de property_documents) e a LLM produz um
--   relatório consolidado (ônus + riscos + recomendações) no formato
--   `DocumentAnalysisReport` (Pydantic em agents/documents/schemas.py).
--
--   Modelo "uma row por execução" — preserva histórico para o usuário
--   conseguir reabrir análises antigas / comparar entre execuções.
--
--   `document_ids` é snapshot: se um doc for deletado depois, a análise
--   permanece referenciando o uuid (fica como referência morta, mas o
--   conteúdo do report continua íntegro).
--
-- Idempotente.
-- =============================================================================

create table if not exists public.document_analyses (
    id                       uuid primary key default gen_random_uuid(),
    property_id              uuid not null references public.properties(id) on delete cascade,

    -- Snapshot de quais docs entraram nesta análise. Não é FK porque docs
    -- podem ser deletados depois — manter como uuid[] preserva o histórico.
    document_ids             uuid[] not null,

    -- DocumentAnalysisReport.model_dump (espelha o Pydantic).
    report                   jsonb not null,

    -- Campos hot-path para listagem/filtro sem precisar abrir o jsonb.
    confidence               text not null check (confidence in ('HIGH','MEDIUM','LOW')),
    has_critical_findings    boolean not null default false,
    cost_usd                 numeric(10, 4),
    model                    text not null,

    created_at               timestamptz not null default now()
);

comment on table public.document_analyses is
    'Histórico de análises consolidadas de documentos da property. '
    'Substitui o auto-OCR síncrono que vivia em legal_checks.matricula_ocr. '
    'Disparada via POST /properties/{id}/documents/analyze com document_ids.';

comment on column public.document_analyses.document_ids is
    'Snapshot dos property_documents que entraram nesta análise. Não é FK — '
    'documentos podem ser deletados depois sem invalidar o report.';

comment on column public.document_analyses.report is
    'DocumentAnalysisReport.model_dump (agents/documents/schemas.py): '
    'documents_analyzed, liens, risks, critical_findings, recommendations, '
    'confidence, cost_usd, extracted_at, model.';

-- Lookup mais comum: última análise de uma property.
create index if not exists ix_document_analyses_property_created
    on public.document_analyses (property_id, created_at desc);

alter table public.document_analyses enable row level security;

drop policy if exists "document_analyses_read_all" on public.document_analyses;
create policy "document_analyses_read_all"
    on public.document_analyses
    for select using (true);
