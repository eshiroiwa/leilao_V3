"""Nós NEIGHBORHOOD STATS + FLIPPING + LIQUIDITY.

Estatísticas descritivas do bairro a partir dos listings vizinhos. Tudo
puro, sem rede — não há motivo para gastar Firecrawl/LLM aqui quando os
listings já estão no DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any

from app.agents.deep.schemas import (
    FlippingResult,
    LiquidityResult,
)

MIN_LISTINGS_FOR_STATS = 10
"""Abaixo disso, não calculamos p90 (amostra rasa demais)."""

LIQUIDITY_VERY_LOW_THRESHOLD = 5
LIQUIDITY_HIGH_THRESHOLD = 30


def _percentile(values: list[float], p: float) -> float | None:
    """Percentil simples (linear interpolation) — sem importar numpy."""
    if not values:
        return None
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def compute_flipping_potential(
    *,
    neighbors: list[dict[str, Any]],
    target_price: float | None,
) -> FlippingResult:
    """Há "teto" no bairro que justifique reformar para vender mais caro?

    O score 1-5 reflete o **upside** entre o preço-alvo do imóvel e o
    p90 do bairro:

    * 5 → upside ≥ 80 %  (bom material para flipping)
    * 4 → upside 50-80 %
    * 3 → upside 25-50 %
    * 2 → upside 10-25 %
    * 1 → upside < 10 %  (provavelmente não vale a reforma pesada)

    Sem `target_price` ou amostra rasa → score = ``None`` (indeterminado).
    """
    prices = [
        float(r["listed_price"])
        for r in neighbors
        if r.get("listed_price") not in (None, 0)
    ]
    ppm2 = [
        float(r["listed_price"]) / float(r["area_total_m2"])
        for r in neighbors
        if r.get("listed_price")
        and r.get("area_total_m2")
        and float(r["area_total_m2"]) > 0
    ]

    if len(prices) < MIN_LISTINGS_FOR_STATS:
        return FlippingResult(
            evidence={
                "n_listings": len(prices),
                "min_for_stats": MIN_LISTINGS_FOR_STATS,
                "reason": "amostra_rasa",
            }
        )

    p_max = max(prices)
    p_p90 = _percentile(prices, 0.9)
    ppm2_p90 = _percentile(ppm2, 0.9) if ppm2 else None

    score: int | None = None
    upside: float | None = None
    if target_price and target_price > 0 and p_p90:
        upside = (p_p90 / target_price) - 1.0
        if upside >= 0.80:
            score = 5
        elif upside >= 0.50:
            score = 4
        elif upside >= 0.25:
            score = 3
        elif upside >= 0.10:
            score = 2
        else:
            score = 1

    return FlippingResult(
        neighborhood_price_max=round(p_max, 2),
        neighborhood_price_p90=round(p_p90, 2) if p_p90 else None,
        neighborhood_ppm2_p90=round(ppm2_p90, 2) if ppm2_p90 else None,
        score=score,
        evidence={
            "n_listings": len(prices),
            "price_median": round(median(prices), 2),
            "price_p90": round(p_p90, 2) if p_p90 else None,
            "price_max": round(p_max, 2),
            "upside_vs_p90": round(upside, 4) if upside is not None else None,
            "target_price": target_price,
        },
    )


def compute_liquidity(
    *,
    neighbors: list[dict[str, Any]],
    city_population: int | None,
) -> LiquidityResult:
    """Score 1-5 de liquidez baseado em volume de oferta + recência + população.

    Sinais:

    * Quantos anúncios ativos no bairro (volume de oferta).
    * "Days on market" médio (proxy: ``now - scraped_at`` — fraco, mas é
      o que temos sem cobrar campo extra dos portais).
    * População da cidade (proxy de demanda).

    O score é um *soft heuristic* — confiabilidade é declarada como MEDIUM
    quando só temos volume (sem população), e HIGH quando temos os dois.
    Confidence LOW quando a amostra é rasa.
    """
    n_listings = len(neighbors)

    now = datetime.now(timezone.utc)
    ages_days: list[float] = []
    for r in neighbors:
        scraped = r.get("scraped_at") or r.get("created_at")
        if not scraped:
            continue
        try:
            dt = datetime.fromisoformat(str(scraped).replace("Z", "+00:00"))
            ages_days.append(max(0.0, (now - dt).total_seconds() / 86_400.0))
        except (ValueError, TypeError):
            continue
    age_median_days = median(ages_days) if ages_days else None

    if n_listings < MIN_LISTINGS_FOR_STATS:
        score = 1 if n_listings == 0 else 2
        return LiquidityResult(
            score=score,
            confidence="LOW",
            evidence={
                "n_listings": n_listings,
                "reason": "amostra_rasa",
                "min_for_stats": MIN_LISTINGS_FOR_STATS,
            },
        )

    # Score base por volume.
    if n_listings >= LIQUIDITY_HIGH_THRESHOLD:
        score = 5
    elif n_listings >= LIQUIDITY_HIGH_THRESHOLD * 2 / 3:
        score = 4
    elif n_listings >= LIQUIDITY_HIGH_THRESHOLD / 3:
        score = 3
    elif n_listings >= LIQUIDITY_VERY_LOW_THRESHOLD:
        score = 2
    else:
        score = 1

    # Ajuste por população — cidades < 50k têm liquidez intrínseca menor.
    if city_population is not None and city_population < 50_000:
        score = max(1, score - 1)

    confidence = "HIGH" if city_population is not None else "MEDIUM"

    return LiquidityResult(
        score=score,
        confidence=confidence,
        evidence={
            "n_listings": n_listings,
            "city_population": city_population,
            "listing_age_median_days": (
                round(age_median_days, 1) if age_median_days is not None else None
            ),
        },
    )
