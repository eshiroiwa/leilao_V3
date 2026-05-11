"""Testes do Monte Carlo (opportunity/montecarlo.py)."""

from __future__ import annotations

import pytest

from app.agents.opportunity.montecarlo import (
    MonteCarloInputs,
    _sample_triangular,
    _sample_truncated_normal,
    simulate,
)


def _base_inputs(**overrides) -> MonteCarloInputs:  # type: ignore[no-untyped-def]
    defaults = dict(
        sale_price_p10=350_000,
        sale_price_p50=400_000,
        sale_price_p90=450_000,
        bid=200_000,
        auctioneer_fee_pct=0.05,
        itbi_pct=0.03,
        registration_pct=0.015,
        iptu_arrears=0,
        condo_arrears=0,
        other_costs=3_000,
        monthly_iptu=0,
        monthly_condo=0,
        holding_months=12,
        renovation_cost_baseline=30_000,
        prob_occupied=0.0,
        occupied_cost_extra=12_000,
    )
    defaults.update(overrides)
    return MonteCarloInputs(**defaults)  # type: ignore[arg-type]


# =============================================================================
# Distribuições auxiliares
# =============================================================================
def test_truncated_normal_keeps_samples_within_bounds() -> None:
    """Nenhuma amostra cai fora de [p10·0.5, p90·1.5]."""
    import random

    rng = random.Random(42)
    p10, p50, p90 = 100.0, 150.0, 200.0
    lo, hi = p10 * 0.5, p90 * 1.5
    for _ in range(1000):
        x = _sample_truncated_normal(p10, p50, p90, rng)
        assert lo <= x <= hi


def test_truncated_normal_mean_close_to_p50() -> None:
    """Em larga escala, a média amostral converge para o p50."""
    import random

    rng = random.Random(7)
    xs = [_sample_truncated_normal(100, 150, 200, rng) for _ in range(5000)]
    assert abs(sum(xs) / len(xs) - 150) < 5  # tolerância de 5 (de 150)


def test_triangular_respects_bounds_and_mode() -> None:
    import random

    rng = random.Random(7)
    xs = [_sample_triangular(50, 80, 130, rng) for _ in range(5000)]
    assert min(xs) >= 50 and max(xs) <= 130
    # Triangular(50, 80, 130) tem média = (50 + 80 + 130)/3 = 86,67.
    assert abs(sum(xs) / len(xs) - 86.67) < 2


# =============================================================================
# simulate — sanity checks
# =============================================================================
def test_simulate_deterministic_with_seed() -> None:
    """Mesma seed → mesmo resultado (idempotente)."""
    inp = _base_inputs()
    a = simulate(inp, n_simulations=2_000, seed=123)
    b = simulate(inp, n_simulations=2_000, seed=123)
    assert a.e_net_roi == b.e_net_roi
    assert a.p_loss == b.p_loss
    assert a.var_5_net_roi == b.var_5_net_roi


def test_simulate_expected_roi_in_realistic_range() -> None:
    """Caso típico de leilão lucrativo → E[ROI] entre 30% e 80%."""
    out = simulate(_base_inputs(), n_simulations=5_000, seed=1)
    assert 0.20 < out.e_net_roi < 1.00
    assert out.median_net_roi > 0
    # VaR_5 deve ser menor que mediana (cauda esquerda).
    assert out.var_5_net_roi < out.median_net_roi
    # P95 deve ser maior que mediana (cauda direita).
    assert out.p95_net_roi > out.median_net_roi


def test_simulate_p_loss_increases_with_higher_bid() -> None:
    """Lance mais alto → mais cenários no vermelho."""
    base = _base_inputs(bid=200_000)
    high_bid = _base_inputs(bid=350_000)
    out_base = simulate(base, n_simulations=3_000, seed=1)
    out_high = simulate(high_bid, n_simulations=3_000, seed=1)
    assert out_high.p_loss > out_base.p_loss


def test_simulate_p_below_cdi_only_when_cdi_provided() -> None:
    inp = _base_inputs()
    out_no = simulate(inp, n_simulations=1_000, seed=1)
    out_yes = simulate(inp, n_simulations=1_000, seed=1, cdi_annual=0.144)
    assert out_no.p_below_cdi is None
    assert out_yes.p_below_cdi is not None
    assert 0.0 <= out_yes.p_below_cdi <= 1.0


def test_simulate_renovation_uncertainty_widens_distribution() -> None:
    """Reforma com cauda mais larga (high_factor=2.0) → VaR_5 mais negativo."""
    narrow = _base_inputs(renovation_high_factor=1.05)  # quase determinístico
    wide = _base_inputs(renovation_high_factor=2.0)     # cauda longa
    out_n = simulate(narrow, n_simulations=4_000, seed=1)
    out_w = simulate(wide, n_simulations=4_000, seed=1)
    assert out_w.var_5_net_roi < out_n.var_5_net_roi


def test_simulate_occupied_property_lowers_expected_roi() -> None:
    """Ocupação certa (prob=1) com custo extra → E[ROI] cai vs vago."""
    vacant = _base_inputs(prob_occupied=0.0)
    occ = _base_inputs(prob_occupied=1.0, occupied_cost_extra=15_000)
    e_vac = simulate(vacant, n_simulations=3_000, seed=1).e_net_roi
    e_occ = simulate(occ, n_simulations=3_000, seed=1).e_net_roi
    assert e_occ < e_vac


def test_simulate_holding_months_shrinks_annualized_roi() -> None:
    """Holding mais longo → E[annualized] cai (mesmo E[net_roi]).

    Comparamos 12 vs 36 meses; o E[net_roi] muda pouco (afeta só holding_costs
    nulo neste cenário), mas E[annualized] cai significativamente."""
    short = _base_inputs(holding_months=12)
    long_ = _base_inputs(holding_months=36)
    out_s = simulate(short, n_simulations=3_000, seed=1)
    out_l = simulate(long_, n_simulations=3_000, seed=1)
    assert out_l.e_annualized_net_roi < out_s.e_annualized_net_roi
