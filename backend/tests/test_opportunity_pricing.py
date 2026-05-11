"""Testes do AGENTE 3 — núcleo matemático.

Cobre:
* compute_acquisition_costs — soma e decomposição.
* compute_income_tax — PF (tabela progressiva), PJ, prejuízo.
* compute_profit_and_roi — fórmulas básicas e divisão por zero.
* solve_max_bid — sanidade: o lance que sai produz EXATAMENTE o ROI alvo
  quando re-calculamos o cenário; PF (1ª faixa e atravessando faixas);
  PJ; ROI alvo inalcançável → None.
"""

from __future__ import annotations

import math

import pytest

from app.agents.opportunity.pricing_math import (
    MaxBidParams,
    annualize_roi,
    compute_acquisition_costs,
    compute_income_tax,
    compute_profit_and_roi,
    solve_max_bid,
)


# =============================================================================
# compute_acquisition_costs
# =============================================================================
def test_acquisition_costs_decomposes_correctly() -> None:
    c = compute_acquisition_costs(
        bid=100_000,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        iptu_arrears=2_000,
        condo_arrears=3_000,
        renovation_cost=20_000,
        other_costs=5_000,
    )
    assert c.bid == 100_000
    assert c.auctioneer_fee == pytest.approx(5_000)
    assert c.itbi == pytest.approx(3_000)
    assert c.registration == pytest.approx(1_500)
    # Sem custos de carregamento explícitos → holding_costs = 0.
    assert c.holding_costs == 0.0
    assert c.total == pytest.approx(
        100_000 + 5_000 + 3_000 + 1_500 + 2_000 + 3_000 + 20_000 + 5_000
    )


def test_acquisition_costs_holding_adds_monthly_iptu_and_condo() -> None:
    """Carregamento: 12 meses × (IPTU 200 + Condo 500) = R$ 8.400 somados."""
    c = compute_acquisition_costs(
        bid=100_000,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        monthly_iptu=200,
        monthly_condo=500,
        holding_months=12,
    )
    assert c.holding_costs == pytest.approx(12 * (200 + 500))
    assert c.total == pytest.approx(100_000 + 5_000 + 3_000 + 1_500 + 8_400)


def test_acquisition_costs_holding_scales_with_months() -> None:
    """24 meses dobram o custo vs. 12 meses (linear)."""
    c12 = compute_acquisition_costs(
        bid=100_000,
        auctioneer_fee_pct=0,
        itbi_pct=0,
        registration_pct=0,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        monthly_iptu=300,
        monthly_condo=700,
        holding_months=12,
    )
    c24 = compute_acquisition_costs(
        bid=100_000,
        auctioneer_fee_pct=0,
        itbi_pct=0,
        registration_pct=0,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        monthly_iptu=300,
        monthly_condo=700,
        holding_months=24,
    )
    assert c24.holding_costs == pytest.approx(2 * c12.holding_costs)


def test_solve_max_bid_holding_costs_lower_max_bid() -> None:
    """Custo de carregamento entra como K — quanto maior, MENOR o lance máximo."""
    base = dict(
        sale_price=500_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        target_net_roi=0.30,
    )
    bid_no_holding = solve_max_bid(MaxBidParams(holding_costs=0, **base))  # type: ignore[arg-type]
    bid_with_holding = solve_max_bid(
        MaxBidParams(holding_costs=24_000, **base)  # type: ignore[arg-type]
    )
    assert bid_no_holding is not None and bid_with_holding is not None
    assert bid_with_holding < bid_no_holding


# =============================================================================
# compute_income_tax
# =============================================================================
def test_income_tax_pf_on_profit_only() -> None:
    assert compute_income_tax(
        buyer_type="PF",
        sale_price=500_000,
        gross_profit=100_000,
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
    ) == pytest.approx(15_000)


def test_income_tax_pf_zero_when_loss() -> None:
    """PF não paga IR sobre prejuízo."""
    assert compute_income_tax(
        buyer_type="PF",
        sale_price=500_000,
        gross_profit=-50_000,
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
    ) == 0.0


def test_income_tax_pj_on_sale_price_even_with_loss() -> None:
    """PJ Lucro Presumido paga sobre faturamento mesmo no prejuízo."""
    assert compute_income_tax(
        buyer_type="PJ",
        sale_price=500_000,
        gross_profit=-50_000,
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
    ) == pytest.approx(32_500)


def test_income_tax_pj_real_combines_income_and_revenue_parts() -> None:
    """Lucro Real lucrativo: IRPJ+CSLL 24% sobre GP + PIS/COFINS 9,25% sobre venda."""
    t = compute_income_tax(
        buyer_type="PJ",
        sale_price=500_000,
        gross_profit=100_000,
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        pj_regime="real",
    )
    # 0,24 × 100k + 0,0925 × 500k = 24k + 46.250 = 70.250
    assert t == pytest.approx(24_000 + 46_250)


def test_income_tax_pj_real_loss_zeroes_irpj_csll_but_keeps_pis_cofins() -> None:
    """Prejuízo no Lucro Real: IRPJ/CSLL = 0; PIS/COFINS ainda sobre venda."""
    t = compute_income_tax(
        buyer_type="PJ",
        sale_price=500_000,
        gross_profit=-50_000,
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        pj_regime="real",
    )
    # 0 + 0,0925 × 500k = 46.250
    assert t == pytest.approx(46_250)


def test_income_tax_pj_real_vs_presumido_higher_in_typical_deal() -> None:
    """Em deal lucrativo isolado, Real geralmente paga MAIS que Presumido —
    confirma que a heurística "Presumido é default" é defensável."""
    common = dict(
        buyer_type="PJ", sale_price=400_000, gross_profit=80_000,
        pf_brackets=((float("inf"), 0.15),), pj_rate=0.065,
    )
    presumido = compute_income_tax(**common, pj_regime="presumido")
    real = compute_income_tax(**common, pj_regime="real")
    assert real > presumido


# =============================================================================
# compute_profit_and_roi
# =============================================================================
def test_profit_and_roi_basic() -> None:
    pb = compute_profit_and_roi(
        sale_price=400_000,
        acquisition_cost_total=200_000,
        realtor_fee_pct=0.06,
        income_tax=10_000,
    )
    assert pb.realtor_fee == pytest.approx(24_000)
    # gross_profit = 400k - 200k - 24k = 176k
    assert pb.gross_profit == pytest.approx(176_000)
    # net_profit = 176k - 10k = 166k
    assert pb.net_profit == pytest.approx(166_000)
    assert pb.gross_roi_pct == pytest.approx(176_000 / 200_000)
    assert pb.net_roi_pct == pytest.approx(166_000 / 200_000)


def test_profit_and_roi_zero_acquisition_returns_zero_roi() -> None:
    pb = compute_profit_and_roi(
        sale_price=100_000,
        acquisition_cost_total=0.0,
        realtor_fee_pct=0.06,
        income_tax=0,
    )
    assert pb.gross_roi_pct == 0.0
    assert pb.net_roi_pct == 0.0
    assert pb.annualized_net_roi_pct == 0.0


# =============================================================================
# annualize_roi + integração com compute_profit_and_roi
# =============================================================================
def test_annualize_roi_passthrough_for_12_months() -> None:
    """Holding default = 12 meses → annualized == net_roi (sem efeito)."""
    assert annualize_roi(0.40, holding_months=12) == pytest.approx(0.40)


def test_annualize_roi_extends_short_horizon() -> None:
    """6 meses com 50% bruto → ~125% a.a. (boa oportunidade real)."""
    assert annualize_roi(0.50, holding_months=6) == pytest.approx(1.25)


def test_annualize_roi_compresses_long_horizon() -> None:
    """24 meses com 50% bruto → ~22,5% a.a. — revela que parecia melhor."""
    assert annualize_roi(0.50, holding_months=24) == pytest.approx(0.224745, rel=1e-3)
    # 60 meses com 50% bruto → ~8,4% a.a. (abaixo do CDI da maioria dos anos).
    assert annualize_roi(0.50, holding_months=60) == pytest.approx(0.084472, rel=1e-3)


def test_annualize_roi_handles_loss_safely() -> None:
    """Prejuízo extremo (-100% ou menos) não pode produzir NaN/Inf."""
    assert annualize_roi(-1.0, holding_months=12) == -1.0
    assert annualize_roi(-2.0, holding_months=24) == -1.0


def test_compute_profit_and_roi_threads_holding_to_annualized() -> None:
    pb = compute_profit_and_roi(
        sale_price=400_000,
        acquisition_cost_total=200_000,
        realtor_fee_pct=0.06,
        income_tax=10_000,
        holding_months=24,
    )
    # net_roi = 166k/200k = 0.83 (testado acima); annualized = sqrt(1.83) - 1.
    expected_annualized = (1 + pb.net_roi_pct) ** (12 / 24) - 1
    assert pb.annualized_net_roi_pct == pytest.approx(expected_annualized)
    assert pb.annualized_net_roi_pct < pb.net_roi_pct


# =============================================================================
# solve_max_bid — testes "round-trip"
# Estratégia: resolver o lance máximo e RECALCULAR o cenário com esse lance.
# O ROI líquido resultante DEVE coincidir com o target dentro de uma tolerância.
# =============================================================================
def _round_trip_check(p: MaxBidParams, *, tol: float = 1e-6) -> float:
    """Helper: resolve, recalcula, verifica que o ROI bate com o target."""
    bid = solve_max_bid(p)
    assert bid is not None, "max_bid deveria ser resolvível"
    assert bid > 0

    F = p.auctioneer_fee_pct + p.itbi_pct + p.registration_pct
    K = (
        p.iptu_arrears
        + p.condo_arrears
        + p.renovation_cost
        + p.other_costs
        + p.holding_costs
    )

    A = bid * (1 + F) + K
    R = p.sale_price * p.realtor_fee_pct
    GP = p.sale_price - A - R
    if p.buyer_type == "PJ":
        if p.pj_regime == "real":
            T = p.sale_price * p.pj_real_revenue_rate + max(0.0, GP) * p.pj_real_income_rate
        else:
            T = p.sale_price * p.pj_rate
    else:
        # Aplica a tabela PROGRESSIVA para validar o lance resolvido.
        gp_positive = max(0.0, GP)
        T = 0.0
        prev_limit = 0.0
        for limit, rate in p.pf_brackets:
            if gp_positive <= prev_limit:
                break
            taxable = min(gp_positive, limit) - prev_limit
            if taxable > 0:
                T += taxable * rate
            prev_limit = limit
    NP = GP - T
    roi = NP / A
    assert math.isclose(roi, p.target_net_roi, abs_tol=tol), (
        f"roi={roi} target={p.target_net_roi} diff={roi - p.target_net_roi}"
    )
    return bid


def test_solve_max_bid_pf_roundtrip_simple() -> None:
    p = MaxBidParams(
        sale_price=500_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        target_net_roi=0.40,
    )
    _round_trip_check(p)


def test_solve_max_bid_pf_with_fixed_costs() -> None:
    p = MaxBidParams(
        sale_price=500_000,
        iptu_arrears=2_000,
        condo_arrears=3_000,
        renovation_cost=30_000,
        other_costs=8_000,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        target_net_roi=0.30,
    )
    _round_trip_check(p)


def test_solve_max_bid_pj_roundtrip() -> None:
    p = MaxBidParams(
        sale_price=600_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=20_000,
        other_costs=5_000,
        auctioneer_fee_pct=0.0,  # Caixa
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PJ",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        target_net_roi=0.40,
    )
    _round_trip_check(p)


def test_solve_max_bid_pj_real_roundtrip_profitable() -> None:
    """Round-trip do solver no regime Lucro Real, hipótese GP ≥ 0."""
    p = MaxBidParams(
        sale_price=600_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=20_000,
        other_costs=5_000,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PJ",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        target_net_roi=0.30,
        pj_regime="real",
    )
    _round_trip_check(p)


def test_solve_max_bid_pj_real_lower_bid_than_presumido_when_profitable() -> None:
    """Deal lucrativo: PJ Real cobra mais imposto → lance máximo MENOR que Presumido."""
    base = dict(
        sale_price=600_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PJ",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        target_net_roi=0.30,
    )
    bid_pres = solve_max_bid(MaxBidParams(pj_regime="presumido", **base))  # type: ignore[arg-type]
    bid_real = solve_max_bid(MaxBidParams(pj_regime="real", **base))  # type: ignore[arg-type]
    assert bid_pres is not None and bid_real is not None
    assert bid_real < bid_pres


def test_solve_max_bid_returns_none_when_fixed_costs_exceed_revenue() -> None:
    """Custos fixos (reforma + dívidas) maiores que a receita líquida possível
    → não há lance positivo que feche a equação."""
    p = MaxBidParams(
        sale_price=200_000,
        iptu_arrears=80_000,
        condo_arrears=80_000,
        renovation_cost=80_000,
        other_costs=20_000,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        target_net_roi=0.40,
    )
    bid = solve_max_bid(p)
    assert bid is None or bid <= 0


def test_solve_max_bid_rises_with_higher_sale_price() -> None:
    """Sanidade: vendendo por mais, o lance máximo deve subir."""
    base = dict(
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
        target_net_roi=0.40,
    )
    a = solve_max_bid(MaxBidParams(sale_price=400_000, **base))  # type: ignore[arg-type]
    b = solve_max_bid(MaxBidParams(sale_price=600_000, **base))  # type: ignore[arg-type]
    assert a is not None and b is not None and b > a


def test_solve_max_bid_drops_with_higher_target_roi() -> None:
    """Sanidade: alvo de ROI maior → lance máximo menor."""
    base = dict(
        sale_price=500_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pf_brackets=((float("inf"), 0.15),),
        pj_rate=0.065,
    )
    a = solve_max_bid(MaxBidParams(target_net_roi=0.20, **base))  # type: ignore[arg-type]
    b = solve_max_bid(MaxBidParams(target_net_roi=0.40, **base))  # type: ignore[arg-type]
    assert a is not None and b is not None and a > b


# =============================================================================
# solve_max_bid com tabela PROGRESSIVA real
# =============================================================================
# Usamos as 4 faixas oficiais da Lei 13.259/2016 (espelham
# ``assumptions.IR_PF_BRACKETS``):
_REAL_PF_BRACKETS = (
    (5_000_000.0, 0.150),
    (10_000_000.0, 0.175),
    (30_000_000.0, 0.200),
    (float("inf"), 0.225),
)


def test_solve_max_bid_pf_progressive_roundtrip_first_bracket() -> None:
    """Imóvel típico de leilão (ganho < R$5MM) → 1ª faixa, 15% liso.
    O round-trip valida com a função genérica que aplica a tabela."""
    p = MaxBidParams(
        sale_price=500_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pf_brackets=_REAL_PF_BRACKETS,
        pj_rate=0.065,
        target_net_roi=0.40,
    )
    _round_trip_check(p)


def test_solve_max_bid_pf_progressive_crosses_second_bracket() -> None:
    """Imóvel de alto padrão: receita R$ 50MM, ganho atravessa a 2ª faixa.

    Com target ROI modesto (20%), o lance vencedor deixa GP > R$ 5MM —
    nesse caso a hipótese da 1ª faixa é INVÁLIDA (o GP não cai nela) e o
    solver deve escolher a solução da 2ª faixa. Validamos que o
    round-trip ainda fecha exatamente no target."""
    p = MaxBidParams(
        sale_price=50_000_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=200_000,
        other_costs=20_000,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pf_brackets=_REAL_PF_BRACKETS,
        pj_rate=0.065,
        target_net_roi=0.20,
    )
    bid = _round_trip_check(p)
    # Validação extra: o GP deve cair na 2ª faixa (R$5MM ≤ GP < R$10MM).
    F = p.auctioneer_fee_pct + p.itbi_pct + p.registration_pct
    A = bid * (1 + F) + (
        p.iptu_arrears + p.condo_arrears + p.renovation_cost + p.other_costs
    )
    GP = p.sale_price - A - p.sale_price * p.realtor_fee_pct
    assert 5_000_000 <= GP < 10_000_000


def test_solve_max_bid_pf_progressive_returns_higher_than_flat_22_5() -> None:
    """Tabela progressiva é mais GENEROSA que aplicar 22,5% liso em ganhos
    pequenos — então o lance máximo com progressiva deve ser MAIOR que
    com alíquota de topo cravada em 22,5%."""
    base = dict(
        sale_price=600_000,
        iptu_arrears=0,
        condo_arrears=0,
        renovation_cost=0,
        other_costs=0,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        realtor_fee_pct=0.06,
        buyer_type="PF",
        pj_rate=0.065,
        target_net_roi=0.30,
    )
    bid_progressive = solve_max_bid(
        MaxBidParams(pf_brackets=_REAL_PF_BRACKETS, **base)  # type: ignore[arg-type]
    )
    bid_flat_top = solve_max_bid(
        MaxBidParams(pf_brackets=((float("inf"), 0.225),), **base)  # type: ignore[arg-type]
    )
    assert bid_progressive is not None and bid_flat_top is not None
    assert bid_progressive > bid_flat_top
