"""Nó OUTLIER — o imóvel é atípico para a vizinhança?

Calcula z-scores de área e preço comparando o imóvel-alvo com os listings
vizinhos. Marca como outlier quando |z| ≥ 2 (distribuição normal: ~95 %
das observações ficam dentro de ±2σ).

Decisão de design — *robust z-score*: usamos mediana e MAD (Median Absolute
Deviation) em vez de média e desvio padrão, porque o mercado imobiliário
costuma ter cauda pesada (1 mansão atípica distorce a média de um bairro
inteiro). MAD é resistente a outliers.

Se o número de vizinhos for < 10, marcamos confiança como insuficiente
(retornamos zscore mas ``is_outlier`` permanece falso) — não dá pra acusar
uma observação de ser outlier numa amostra rasa.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from app.agents.deep.schemas import OutlierResult

MIN_NEIGHBORS_FOR_FLAGGING = 10
"""Abaixo disso o z-score existe mas não vira flag de outlier."""

OUTLIER_THRESHOLD = 2.0
"""|z| ≥ 2 → outlier (≈ percentis 2,3 e 97,7 numa normal)."""


def _robust_zscore(value: float, samples: list[float]) -> float | None:
    """Z-score baseado em mediana + MAD * 1.4826.

    A constante 1.4826 normaliza MAD para que, sob distribuição normal, o
    z-score robusto seja consistente com o z-score clássico (mesma escala).
    """
    if not samples:
        return None
    med = median(samples)
    deviations = [abs(s - med) for s in samples]
    mad = median(deviations)
    if mad == 0:
        return None  # variância nula — não dá pra calcular z
    return (value - med) / (mad * 1.4826)


def compute_outlier(
    *,
    target_area_m2: float | None,
    target_price: float | None,
    neighbors: list[dict[str, Any]],
) -> OutlierResult:
    """Avalia o imóvel-alvo contra a distribuição dos vizinhos."""
    n = len(neighbors)
    can_flag = n >= MIN_NEIGHBORS_FOR_FLAGGING

    areas = [
        float(r["area_total_m2"])
        for r in neighbors
        if r.get("area_total_m2") not in (None, 0)
    ]
    prices = [
        float(r["listed_price"])
        for r in neighbors
        if r.get("listed_price") not in (None, 0)
    ]

    size_z = (
        _robust_zscore(target_area_m2, areas)
        if (target_area_m2 and areas)
        else None
    )
    price_z = (
        _robust_zscore(target_price, prices)
        if (target_price and prices)
        else None
    )

    is_outlier_size = bool(
        can_flag and size_z is not None and abs(size_z) >= OUTLIER_THRESHOLD
    )
    is_outlier_price = bool(
        can_flag and price_z is not None and abs(price_z) >= OUTLIER_THRESHOLD
    )

    evidence: dict[str, Any] = {
        "n_neighbors_total": n,
        "n_with_area": len(areas),
        "n_with_price": len(prices),
        "min_neighbors_for_flagging": MIN_NEIGHBORS_FOR_FLAGGING,
        "outlier_threshold": OUTLIER_THRESHOLD,
    }
    if areas:
        evidence["area_median"] = median(areas)
        evidence["area_min"] = min(areas)
        evidence["area_max"] = max(areas)
    if prices:
        evidence["price_median"] = median(prices)
        evidence["price_min"] = min(prices)
        evidence["price_max"] = max(prices)
    if target_area_m2 is not None:
        evidence["target_area_m2"] = target_area_m2
    if target_price is not None:
        evidence["target_price"] = target_price

    return OutlierResult(
        is_outlier_size=is_outlier_size,
        is_outlier_price=is_outlier_price,
        size_zscore=round(size_z, 2) if size_z is not None else None,
        price_zscore=round(price_z, 2) if price_z is not None else None,
        n_neighbors=n,
        evidence=evidence,
    )
