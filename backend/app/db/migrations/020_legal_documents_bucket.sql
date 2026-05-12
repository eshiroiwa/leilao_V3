-- =============================================================================
-- Migration 020 — bucket Storage privado `legal-documents` (Agente Legal)
-- =============================================================================
--   Cria o bucket Supabase Storage onde o endpoint POST /properties/{id}/legal/matricula
--   persiste o PDF de matrícula enviado pelo usuário.
--
--     legal-documents/{property_id}/matricula_{epoch}.pdf
--
--   Bucket é PRIVADO. Frontend recebe signed URL temporária (1h) via
--   GET /properties/{id}/legal-checks/latest. Escrita só via service_role
--   (backend) — RLS bloqueia anônimos.
--
-- Idempotente.
-- =============================================================================

-- 1. Cria (ou atualiza para privado) o bucket.
insert into storage.buckets (id, name, public)
values ('legal-documents', 'legal-documents', false)
on conflict (id) do update
  set public = excluded.public;

-- 2. Sem policy para anônimos — bucket é privado.
--    service_role (usado pelo backend) bypassa RLS automaticamente, então
--    não precisamos de policy adicional para upload/leitura via backend.
--    Frontend acessa exclusivamente via signed URLs geradas pelo backend.
