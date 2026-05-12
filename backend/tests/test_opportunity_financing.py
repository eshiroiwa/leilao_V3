"""Testes de financing/parcelamento + ROI alavancado (Agente 3)."""

from __future__ import annotations

import math

import pytest

from app.agents.opportunity import assumptions as A
from app.agents.opportunity.pricing_math import (
    MaxBidNumericParams,
    compute_financing_terms,
    compute_profit_and_roi,
    solve_max_bid_numeric,
)


# =============================================================================
# compute_financing_terms
# =============================================================================
class TestFinancingTerms:
    def test_cash_returns_full_entry_no_loan(self) -> None:
        f = compute_financing_terms(
            bid=300_000, holding_months=12, payment_mode="cash",
        )
        assert f.mode == "cash"
        assert f.entry == 300_000
        assert f.financed_amount == 0
        assert f.pmt == 0
        assert f.balance_at_sale == 0
        assert f.interest_paid_holding == 0

    def test_financed_bank_default_30pct_240m(self) -> None:
        """Entrada 30%, prazo 240 meses, taxa 10% a.a."""
        f = compute_financing_terms(
            bid=300_000, holding_months=12,
            payment_mode="financed_bank",
            loan_rate_annual_pct=0.10,  # 10% a.a.
        )
        assert f.mode == "financed_bank"
        assert f.entry == pytest.approx(90_000)  # 30% × 300k
        assert f.financed_amount == pytest.approx(210_000)
        # Taxa mensal equivalente de 10% a.a. ≈ 0.7974%/m
        assert f.rate_monthly_pct == pytest.approx(
            (1.10) ** (1 / 12) - 1, rel=1e-6,
        )
        assert f.loan_months == 240
        # PMT Price com 210k, 0.7974%/m (eq. anual), 240 meses ≈ R$ 1.967
        assert f.pmt == pytest.approx(1967, abs=15)
        # Holding 12 meses → 12 parcelas pagas
        assert f.holding_payments == pytest.approx(f.pmt * 12)
        # Saldo após 12 meses > 0 (longe de quitar)
        assert 195_000 < f.balance_at_sale < 210_000
        # Juros pagos = total pago − amortização
        assert f.interest_paid_holding > 0

    def test_balance_zero_when_holding_ge_loan_months(self) -> None:
        """Se holding cobre o financiamento inteiro, saldo é zero."""
        f = compute_financing_terms(
            bid=100_000, holding_months=60,
            payment_mode="financed_bank",
            loan_months=60, loan_rate_annual_pct=0.10,
        )
        assert f.balance_at_sale == pytest.approx(0, abs=1)

    def test_judicial_no_correction_linear_installments(self) -> None:
        """Sem correção: pmt = (bid − entrada) / n_parcelas."""
        f = compute_financing_terms(
            bid=400_000, holding_months=12,
            payment_mode="installments_judicial",
            down_payment_pct=0.25,
            installments_count=30,
            installments_index="none",
        )
        assert f.entry == pytest.approx(100_000)
        assert f.financed_amount == pytest.approx(300_000)
        assert f.rate_monthly_pct == 0
        # Sem juros → cada parcela = 300k/30 = 10k
        assert f.pmt == pytest.approx(10_000)
        # Holding 12m → 12 parcelas → saldo = 18 × 10k = 180k
        assert f.holding_payments == pytest.approx(120_000)
        assert f.balance_at_sale == pytest.approx(180_000)
        assert f.interest_paid_holding == pytest.approx(0, abs=1)

    def test_judicial_with_ipca_applies_monthly_correction(self) -> None:
        f = compute_financing_terms(
            bid=300_000, holding_months=12,
            payment_mode="installments_judicial",
            installments_count=30,
            installments_index="ipca",
            ipca_annual=0.05,
        )
        # IPCA 5% a.a. → mensal ≈ 0.407%
        assert f.rate_monthly_pct > 0
        assert f.rate_monthly_pct < 0.005
        # Com juros, há saldo de juros pagos > 0
        assert f.interest_paid_holding > 0


# =============================================================================
# compute_profit_and_roi — ROI alavancado
# =============================================================================
class TestRoiAlavancado:
    def test_cash_unchanged_behavior(self) -> None:
        """Sem financing, ROI cai sobre o custo total — comportamento histórico."""
        pb = compute_profit_and_roi(
            sale_price=500_000,
            acquisition_cost_total=400_000,
            realtor_fee_pct=0.06,
            income_tax=10_000,
            holding_months=12,
        )
        # gross_profit = 500k − 400k − 30k = 70k; net = 60k
        assert pb.gross_profit == pytest.approx(70_000)
        assert pb.net_profit == pytest.approx(60_000)
        # ROI sobre 400k → 15%
        assert pb.net_roi_pct == pytest.approx(0.15, rel=1e-4)

    def test_financed_uses_leverage_for_higher_roi(self) -> None:
        """Mesmo deal financiado tem ROI maior (alavancagem)."""
        fin = compute_financing_terms(
            bid=300_000, holding_months=12,
            payment_mode="financed_bank",
            down_payment_pct=0.30,
            loan_months=240,
            loan_rate_annual_pct=0.10,
        )
        pb = compute_profit_and_roi(
            sale_price=500_000,
            # accessory_total (custos sem o bid): ITBI+leiloeiro+reforma etc.
            acquisition_cost_total=50_000,
            realtor_fee_pct=0.06,
            income_tax=10_000,
            holding_months=12,
            financing=fin,
        )
        # capital_alocado = entry (90k) + holding_payments (~23k) + 50k = ~163k
        capital = fin.entry + fin.holding_payments + 50_000
        assert pb.acquisition_cost_total == pytest.approx(capital, rel=1e-4)
        # ROI é sobre esse capital reduzido → bem maior que o cash equivalente
        assert pb.net_roi_pct > 0.10  # alavancado, mesmo após juros


# =============================================================================
# solve_max_bid_numeric — convergência
# =============================================================================
class TestMaxBidNumeric:
    def _params(self, **overrides):
        base = dict(
            sale_price=500_000,
            iptu_arrears=0,
            condo_arrears=0,
            renovation_cost=20_000,
            other_costs=5_000,
            auctioneer_fee_pct=0.05,
            itbi_pct=0.03,
            registration_pct=0.012,
            realtor_fee_pct=0.06,
            buyer_type="PF",
            pf_brackets=A.IR_PF_BRACKETS,
            pj_rate=A.IR_PJ_PCT,
            target_net_roi=0.20,  # 20% líquido
            holding_costs=0,
            holding_months=12,
            payment_mode="cash",
        )
        base.update(overrides)
        return MaxBidNumericParams(**base)

    def test_converges_for_cash(self) -> None:
        """Cash: numérico deve dar resultado válido (próximo do algébrico)."""
        p = self._params()
        bid = solve_max_bid_numeric(p)
        assert bid is not None
        assert 200_000 < bid < 400_000

    def test_financed_yields_higher_max_bid_than_cash(self) -> None:
        """Com financiamento, dado o mesmo target ROI, dá pra pagar MAIS."""
        p_cash = self._params(payment_mode="cash")
        p_fin = self._params(
            payment_mode="financed_bank",
            down_payment_pct=0.30,
            loan_months=240,
            loan_rate_annual_pct=0.10,
        )
        bid_cash = solve_max_bid_numeric(p_cash)
        bid_fin = solve_max_bid_numeric(p_fin)
        assert bid_cash is not None and bid_fin is not None
        # Alavancagem permite lance maior preservando o ROI alavancado.
        assert bid_fin > bid_cash

    def test_returns_none_when_target_unreachable(self) -> None:
        """ROI alvo muito alto + sale price baixo → inalcançável."""
        p = self._params(sale_price=10_000, target_net_roi=2.0)
        bid = solve_max_bid_numeric(p)
        assert bid is None
