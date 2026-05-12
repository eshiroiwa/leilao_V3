-- =============================================================================
-- Migration 021 — `property_documents`: gerenciador genérico de docs por imóvel
-- =============================================================================
--   Substitui o fluxo single-shot de upload de matrícula (que persistia direto
--   em `legal_checks.matricula_ocr` + bucket `legal-documents`) por um modelo
--   unificado onde qualquer documento relevante ao imóvel (matrícula, edital,
--   laudo, peças processuais, outros) vira uma row separada.
--
--   Importante:
--     * O upload NÃO dispara análise. OCR/LLM acontecem sob demanda quando
--       o usuário seleciona docs e clica "Analisar selecionados". Resultado
--       vai em `document_analyses` (migration 023).
--     * Bucket continua o `legal-documents` (privado) — apenas o path muda:
--       `{property_id}/{uuid4}.{ext}` (preserva a extensão original).
--
--   doc_type CHECK espelha exatamente o Literal Pydantic em
--   `agents/documents/schemas.py::DocumentType`. Qualquer novo tipo pede
--   migration de DROP/ADD CONSTRAINT junto da mudança no Literal.
--
-- Idempotente.
-- =============================================================================

create table if not exists public.property_documents (
    id                  uuid primary key default gen_random_uuid(),
    property_id         uuid not null references public.properties(id) on delete cascade,

    -- Tipo canônico. `outros` é categoria genérica com label livre.
    doc_type            text not null
        check (doc_type in (
            'matricula',
            'edital',
            'laudo_avaliacao',
            'pecas_processuais',
            'outros'
        )),
    -- Só preenchido (e obrigatório) quando doc_type='outros'.
    custom_label        text,

    original_filename   text not null,
    storage_path        text not null,
    mime_type           text not null,
    -- 0 é sentinel usado pelo backfill de rows pré-021 (tamanho real
    -- não estava disponível). UI mostra "—" quando 0.
    size_bytes          bigint not null check (size_bytes >= 0),

    -- Placeholder de auditoria. Sem auth real hoje (vide schema.sql:405-429);
    -- pode receber e-mail/identificador via header ou ficar null.
    uploaded_by         text,

    created_at          timestamptz not null default now(),

    constraint property_documents_custom_label_only_when_outros
        check ((doc_type = 'outros') = (custom_label is not null))
);

comment on table public.property_documents is
    'Documentos anexados a uma property (matrícula, edital, laudo, peças, outros). '
    'Upload não dispara análise; análise consolidada via /documents/analyze grava '
    'em document_analyses.';

comment on column public.property_documents.doc_type is
    'Tipo canônico — espelha Literal DocumentType em agents/documents/schemas.py. '
    'CHECK constraint deve ser atualizado JUNTO de qualquer mudança no Literal.';

comment on column public.property_documents.custom_label is
    'Rótulo livre. Obrigatório quando doc_type=outros, proibido caso contrário '
    '(reforçado por CHECK).';

comment on column public.property_documents.storage_path is
    'Path no bucket privado legal-documents. Formato: {property_id}/{uuid4}.{ext}.';

comment on column public.property_documents.size_bytes is
    'Tamanho do arquivo em bytes. 0 é sentinel para rows criadas via backfill '
    '(migration 022) quando o tamanho real não estava disponível.';

-- Lookup mais comum: listar docs da property em ordem decrescente de upload.
create index if not exists ix_property_documents_property_created
    on public.property_documents (property_id, created_at desc);

-- Filtro por tipo (ex.: "última matrícula desta property").
create index if not exists ix_property_documents_property_type
    on public.property_documents (property_id, doc_type);

alter table public.property_documents enable row level security;

-- Stub público de leitura (segue padrão atual; backend usa service_role).
drop policy if exists "property_documents_read_all" on public.property_documents;
create policy "property_documents_read_all"
    on public.property_documents
    for select using (true);
