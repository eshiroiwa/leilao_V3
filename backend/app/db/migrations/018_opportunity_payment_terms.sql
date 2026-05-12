-- =============================================================================
-- Migration 018 — coluna `payment_terms` em `opportunity_analyses` (AGENTE 3)
-- =============================================================================
--   Coluna nova JSONB que persiste a modalidade de pagamento da análise:
--     * payment_mode: cash / financed_bank / installments_judicial
--     * down_payment_pct, loan_months, loan_rate_annual_pct (financiado)
--     * installments_count, installments_index (judicial)
--     * Métricas calculadas para auditoria: pmt, balance_at_sale,
--       interest_paid_holding (snapshotadas no momento da análise)
--
--   Schema segue PaymentTerms inferido de FinancingTerms + AnalysisInput
--   (agents/opportunity/schemas.py). A coluna é nullable — análises antigas
--   continuam válidas com payment_mode tratado como "cash" pelo frontend.
--
-- Idempotente.
-- =============================================================================
alter table public.opportunity_analyses
  add column if not exists payment_terms jsonb;

comment on column public.opportunity_analyses.payment_terms is
  'Modalidade de pagamento + premissas (mode, down_payment_pct, loan_months, '
  'loan_rate_annual_pct, installments_count, installments_index, pmt, '
  'balance_at_sale, interest_paid_holding). JSONB livre para evolução; '
  'NULL em análises pré-018 = comportamento "cash".';
