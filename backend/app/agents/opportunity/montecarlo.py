"""Monte Carlo de ROI: substitui os 3 cenários discretos por amostragem.

Ao invés de ponderar pessimista/realista/otimista por 30/40/30 (heurística
configurável em ``assumptions.SCENARIO_PROB_*``), simulamos N trajetórias
amostrando as fontes de incerteza:

  * **Preço de venda**: truncated normal centrada em P50, σ = (P90 − P10)/3.
    Reflete a banda da CMA — distribuição mais ampla quando a confiança é
    baixa (porque P90−P10 cresce).
  * **Custo de reforma**: triangular (low=baseline×0.7, mode=baseline,
    high=baseline×1.4). Reformas estouram orçamento mais frequentemente do
    que terminam abaixo — daí a cauda longa à direita.
  * **Ocupação**: Bernoulli com probabilidade ``prob_occupied`` (default
    do status declarado pelo edital); em caso afirmativo, adiciona
    ``occupied_cost_extra`` (custas judiciais/oficial de justiça).

NÃO modelamos tempo de venda nesta versão — ele afeta o ROI anualizado
(via ``holding_months``) e depende do mercado/cidade. Vai entrar na Fase 4
quando integrarmos a base FipeZAP de tendência mensal.

Função pura e determinística dado um ``seed`` — testável em unidade.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

from app.agents.opportunity.pricing_math import (
    PFBracket,
    annualize_roi,
    compute_income_tax,
)


# Quantidade default — calibrada para baixa variância no E[ROI] e P[loss]
# (~10k roda em ~50ms em Python puro, sem numpy).
DEFAULT_N_SIMULATIONS: int = 10_000


@dataclass(frozen=True, slots=True)
class MonteCarloInputs:
    """Conjunto fechado de parâmetros para uma simulação."""

    # Preço de venda — banda da CMA
    sale_price_p10: float
    sale_price_p50: float
    sale_price_p90: float

    # Aquisição (fixos por simulação — não amostramos no MVP)
    bid: float
    auctioneer_fee_pct: float
    itbi_pct: float
    registration_pct: float
    iptu_arrears: float
    condo_arrears: float
    other_costs: float
    monthly_iptu: float
    monthly_condo: float
    holding_months: int

    # Reforma — triangular em torno do baseline
    renovation_cost_baseline: float
    renovation_low_factor: float = 0.7
    renovation_high_factor: float = 1.4

    # Ocupação — Bernoulli
    prob_occupied: float = 0.0
    occupied_cost_extra: float = 0.0

    # Venda + imposto
    realtor_fee_pct: float = 0.06
    buyer_type: str = "PF"
    pf_brackets: tuple[PFBracket, ...] = ((float("inf"), 0.15),)
    pj_rate: float = 0.065
    pj_regime: str = "presumido"
    pj_real_income_rate: float = 0.24
    pj_real_revenue_rate: float = 0.0925


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    """Saída agregada da simulação."""

    n_simulations: int
    e_net_roi: float
    e_annualized_net_roi: float
    p_loss: float                # P[net_roi < 0]
    p_below_cdi: float | None    # P[annualized_roi < cdi] (None se cdi=None)
    var_5_net_roi: float         # 5º percentil do ROI líquido (cauda esquerda)
    p95_net_roi: float           # 95º percentil
    median_net_roi: float


def _sample_truncated_normal(
    p10: float, p50: float, p90: float, rng: random.Random
) -> float:
    """Amostra uma normal truncada calibrada pela banda (P10, P50, P90).

    σ é derivado pela aproximação `(P90 − P10) / (2·1.2816)` — o intervalo
    P10–P90 contém ~80% da massa em uma normal. Truncamos em
    [P10·0.5, P90·1.5] para evitar caudas extremas que não fazem sentido
    em preço de imóvel (mercado tem piso e teto físicos).
    """
    # (P90−P10)/2.5631 ≈ σ (z_90 − z_10) = 2 × 1.2816
    sd = max((p90 - p10) / 2.5631, 1.0)
    lo = p10 * 0.5
    hi = p90 * 1.5
    for _ in range(100):
        x = rng.gauss(p50, sd)
        if lo <= x <= hi:
            return x
    # Fallback degenerado — devolve o p50 (não trava o pipeline).
    return p50


def _sample_triangular(low: float, mode: float, high: float, rng: random.Random) -> float:
    """Triangular(a, c, b) — fórmula clássica via inversão da CDF."""
    if high <= low:
        return mode
    u = rng.random()
    f = (mode - low) / (high - low)
    if u < f:
        return low + math.sqrt(u * (high - low) * (mode - low))
    return high - math.sqrt((1.0 - u) * (high - low) * (high - mode))


def simulate(
    inputs: MonteCarloInputs,
    *,
    n_simulations: int = DEFAULT_N_SIMULATIONS,
    cdi_annual: float | None = None,
    seed: int | None = None,
) -> MonteCarloResult:
    """Roda ``n_simulations`` trajetórias e devolve estatísticas agregadas.

    Determinístico quando ``seed`` é dado — útil para testes/reprodutibilidade.
    """
    rng = random.Random(seed)

    F = inputs.auctioneer_fee_pct + inputs.itbi_pct + inputs.registration_pct
    fixed_K_base = (
        inputs.iptu_arrears
        + inputs.condo_arrears
        + inputs.other_costs
        + inputs.holding_months * (inputs.monthly_iptu + inputs.monthly_condo)
    )

    net_rois: list[float] = []
    annualized_rois: list[float] = []
    losses = 0
    below_cdi = 0

    for _ in range(n_simulations):
        sale_price = _sample_truncated_normal(
            inputs.sale_price_p10, inputs.sale_price_p50, inputs.sale_price_p90, rng
        )
        renovation_cost = _sample_triangular(
            inputs.renovation_cost_baseline * inputs.renovation_low_factor,
            inputs.renovation_cost_baseline,
            inputs.renovation_cost_baseline * inputs.renovation_high_factor,
            rng,
        )
        extra_occupied = (
            inputs.occupied_cost_extra
            if rng.random() < inputs.prob_occupied
            else 0.0
        )

        K = fixed_K_base + renovation_cost + extra_occupied
        acquisition = inputs.bid * (1.0 + F) + K
        realtor_fee = sale_price * inputs.realtor_fee_pct
        gp_pre_tax = sale_price - acquisition - realtor_fee
        income_tax = compute_income_tax(
            buyer_type=inputs.buyer_type,
            sale_price=sale_price,
            gross_profit=gp_pre_tax,
            pf_brackets=inputs.pf_brackets,
            pj_rate=inputs.pj_rate,
            pj_regime=inputs.pj_regime,
            pj_real_income_rate=inputs.pj_real_income_rate,
            pj_real_revenue_rate=inputs.pj_real_revenue_rate,
        )
        net_profit = gp_pre_tax - income_tax
        net_roi = net_profit / acquisition if acquisition > 0 else 0.0
        annualized = annualize_roi(net_roi, inputs.holding_months)

        net_rois.append(net_roi)
        annualized_rois.append(annualized)
        if net_profit < 0:
            losses += 1
        if cdi_annual is not None and annualized < cdi_annual:
            below_cdi += 1

    sorted_rois = sorted(net_rois)
    median = statistics.median(sorted_rois)
    var_5 = sorted_rois[int(n_simulations * 0.05)]
    p95 = sorted_rois[int(n_simulations * 0.95)]
    e_net = statistics.fmean(net_rois)
    e_annual = statistics.fmean(annualized_rois)

    return MonteCarloResult(
        n_simulations=n_simulations,
        e_net_roi=e_net,
        e_annualized_net_roi=e_annual,
        p_loss=losses / n_simulations,
        p_below_cdi=(below_cdi / n_simulations) if cdi_annual is not None else None,
        var_5_net_roi=var_5,
        p95_net_roi=p95,
        median_net_roi=median,
    )


__all__ = [
    "DEFAULT_N_SIMULATIONS",
    "MonteCarloInputs",
    "MonteCarloResult",
    "simulate",
]
