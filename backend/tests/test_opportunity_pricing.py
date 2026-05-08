"""Testes do AGENTE 3 — núcleo matemático.

Cobre:
* compute_acquisition_costs — soma e decomposição.
* compute_income_tax — PF, PJ, prejuízo.
* compute_profit_and_roi — fórmulas básicas e divisão por zero.
* solve_max_bid — sanidade: o lance que sai produz EXATAMENTE o ROI alvo
  quando re-calculamos o cenário; PF/PJ; ROI alvo inalcançável → None.
"""

from __future__ import annotations

import math

import pytest

from app.agents.opportunity.pricing_math import (
    MaxBidParams,
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
    assert c.total == pytest.approx(
        100_000 + 5_000 + 3_000 + 1_500 + 2_000 + 3_000 + 20_000 + 5_000
    )


# =============================================================================
# compute_income_tax
# =============================================================================
def test_income_tax_pf_on_profit_only() -> None:
    assert compute_income_tax(
        buyer_type="PF",
        sale_price=500_000,
        gross_profit=100_000,
        pf_rate=0.15,
        pj_rate=0.065,
    ) == pytest.approx(15_000)


def test_income_tax_pf_zero_when_loss() -> None:
    """PF não paga IR sobre prejuízo."""
    assert compute_income_tax(
        buyer_type="PF",
        sale_price=500_000,
        gross_profit=-50_000,
        pf_rate=0.15,
        pj_rate=0.065,
    ) == 0.0


def test_income_tax_pj_on_sale_price_even_with_loss() -> None:
    """PJ Lucro Presumido paga sobre faturamento mesmo no prejuízo."""
    assert compute_income_tax(
        buyer_type="PJ",
        sale_price=500_000,
        gross_profit=-50_000,
        pf_rate=0.15,
        pj_rate=0.065,
    ) == pytest.approx(32_500)


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
    K = p.iptu_arrears + p.condo_arrears + p.renovation_cost + p.other_costs

    A = bid * (1 + F) + K
    R = p.sale_price * p.realtor_fee_pct
    GP = p.sale_price - A - R
    if p.buyer_type == "PJ":
        T = p.sale_price * p.pj_rate
    else:
        T = max(0.0, GP) * p.pf_rate
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
        pf_rate=0.15,
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
        pf_rate=0.15,
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
        pf_rate=0.15,
        pj_rate=0.065,
        target_net_roi=0.40,
    )
    _round_trip_check(p)


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
        pf_rate=0.15,
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
        pf_rate=0.15,
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
        pf_rate=0.15,
        pj_rate=0.065,
    )
    a = solve_max_bid(MaxBidParams(target_net_roi=0.20, **base))  # type: ignore[arg-type]
    b = solve_max_bid(MaxBidParams(target_net_roi=0.40, **base))  # type: ignore[arg-type]
    assert a is not None and b is not None and a > b
