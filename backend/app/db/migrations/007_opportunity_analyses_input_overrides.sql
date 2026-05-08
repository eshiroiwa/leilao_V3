-- Persiste os overrides do formulário ("Alíquotas" e "Sale price") junto com
-- cada análise, para que o frontend possa restaurar exatamente os parâmetros
-- usados ao clicar em uma análise antiga do histórico.
--
-- Estrutura esperada (todos os campos são opcionais):
--   {
--     "itbi_pct_override":         number | null,
--     "registration_pct_override": number | null,
--     "auctioneer_fee_pct_override": number | null,
--     "sale_price_override":       number | null
--   }
alter table public.opportunity_analyses
  add column if not exists input_overrides jsonb;
