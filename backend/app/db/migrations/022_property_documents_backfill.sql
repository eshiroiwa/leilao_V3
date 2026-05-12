-- =============================================================================
-- Migration 022 — backfill: legal_checks.matricula_ocr → property_documents
-- =============================================================================
--   Cria uma row em `property_documents` para cada `pdf_path` distinto já
--   referenciado em `legal_checks.matricula_ocr` (PDFs de matrícula que
--   foram subidos antes da migração 021).
--
--   Considerações:
--     * `size_bytes=0` é sentinel — não temos o tamanho real retroativamente.
--     * `mime_type='application/pdf'` é seguro (endpoint legacy só aceitava PDF).
--     * `original_filename` é derivado do basename do path (matricula_<epoch>.pdf).
--     * `created_at` reflete o `created_at` do legal_check para manter ordem
--       histórica plausível na UI.
--     * Idempotente via `WHERE NOT EXISTS` em storage_path.
--
--   `legal_checks.matricula_ocr` NÃO é apagado — continua disponível como
--   fonte legada para `LegalSummary` quando não houver `document_analyses`.
-- =============================================================================

insert into public.property_documents (
    property_id,
    doc_type,
    custom_label,
    original_filename,
    storage_path,
    mime_type,
    size_bytes,
    created_at
)
select
    lc.property_id,
    'matricula'::text                                          as doc_type,
    null                                                       as custom_label,
    regexp_replace(lc.matricula_ocr->>'pdf_path', '.*/', '')   as original_filename,
    lc.matricula_ocr->>'pdf_path'                              as storage_path,
    'application/pdf'                                          as mime_type,
    0                                                          as size_bytes,
    lc.created_at                                              as created_at
from public.legal_checks lc
where
    lc.matricula_ocr is not null
    and (lc.matricula_ocr->>'pdf_path') is not null
    and not exists (
        select 1
        from public.property_documents pd
        where pd.storage_path = lc.matricula_ocr->>'pdf_path'
    );
