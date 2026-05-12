-- =============================================================================
-- Migration 019 — colunas estendidas em `legal_checks` (Agente Legal)
-- =============================================================================
--   Adiciona 3 colunas JSONB nullable:
--     * web_findings    — achados na web (Firecrawl) ligados ao proprietário
--                         (anulatórias/embargos). Lista de WebFinding.
--     * matricula_ocr   — saída do OCR estruturado do PDF da matrícula
--                         (proprietário, CPF, número, CRI, ônus ativos).
--                         Schema: MatriculaOcrResult.
--     * processes_full  — lista COMPLETA dos processos DataJud (até 100 por
--                         tribunal), com categoria legível. `sample_processes`
--                         segue como compactação retrocompat (até 20 críticos).
--
--   Rows antigas (pré-019) ficam com NULL nas 3 colunas e o frontend trata
--   como ausência — comportamento pré-rodada preservado.
--
-- Idempotente.
-- =============================================================================
alter table public.legal_checks
  add column if not exists web_findings jsonb,
  add column if not exists matricula_ocr jsonb,
  add column if not exists processes_full jsonb;

comment on column public.legal_checks.web_findings is
  'Achados na web via Firecrawl: lista de WebFinding (title, url, snippet, '
  'query, score). Filtra Jusbrasil/redes sociais. Score alto sinaliza '
  'menção a anulatória/embargos.';

comment on column public.legal_checks.matricula_ocr is
  'OCR estruturado do PDF da matrícula (Vision GPT-4o): proprietário, '
  'CPF/CNPJ, número, cartório, lista de ônus ativos. Schema segue '
  'MatriculaOcrResult (agents/legal/schemas.py). pdf_path aponta para '
  'bucket privado legal-documents.';

comment on column public.legal_checks.processes_full is
  'Lista COMPLETA dos processos DataJud (até 100 por tribunal) com '
  'category legível. sample_processes (coluna pré-existente) segue como '
  'compactação top-20 com críticos primeiro.';
