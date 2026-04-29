"""Estimação de preço a partir de comparáveis.

Princípio: usar **R$/m² ponderado pela similaridade**, com mediana (robusta
a outliers) e intervalo P10–P90 ponderado. Múltiplos métodos podiam ser
implementados (média geométrica, regressão), mas para amostras pequenas
(5–15 comparáveis) a mediana ponderada é a opção mais defensável.

Funções puras, sem I/O.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Literal

Confidence = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]


@dataclass(frozen=True)
class Comparable:
    """Item já filtrado e pronto para entrar no cálculo.

    ``ppm2`` = preço por m² do anúncio. Calcular ANTES de chamar pricing
    (caller é responsável por descartar comparáveis sem ``listed_price``
    ou ``area_total_m2``).
    """

    listing_id: str
    ppm2: float
    weight: float  # tipicamente similarity × reliability


@dataclass(frozen=True)
class Valuation:
    """Resultado de uma estimação."""

    estimated_price: float | None
    price_lower_bound: float | None
    price_upper_bound: float | None
    ppm2_estimated: float | None
    confidence: Confidence
    method: str
    comparables_used: int


# ---------------------------------------------------------------------------
# Quantis ponderados (sem numpy/scipy — mantemos a stack leve).
# ---------------------------------------------------------------------------
def weighted_quantile(
    values: Iterable[float],
    weights: Iterable[float],
    q: float,
) -> float:
    """Quantil ponderado com convenção "centro do peso".

    Cada amostra ``(v_i, w_i)`` ocupa um intervalo de comprimento ``w_i`` na
    CDF cumulativa, e seu valor é representativo no CENTRO desse intervalo.
    Interpolamos linearmente entre centros consecutivos.

    Essa convenção tem duas propriedades importantes para nós:
      * para pesos uniformes, recupera EXATAMENTE a mediana clássica
        (median([1,2,3,4,5]) = 3.0);
      * pesos zero/negativos são silenciosamente ignorados.

    ``q`` ∈ [0, 1]. Lista vazia levanta ``ValueError``.
    """
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q deve estar em [0,1], recebido {q}")

    pairs = sorted(
        ((float(v), float(w)) for v, w in zip(values, weights) if w and w > 0),
        key=lambda x: x[0],
    )
    if not pairs:
        raise ValueError("Sem valores com peso positivo para calcular quantil.")

    total_w = sum(w for _, w in pairs)
    target = q * total_w

    # Posição "central" de cada amostra na CDF acumulada.
    centers: list[tuple[float, float]] = []
    running = 0.0
    for v, w in pairs:
        centers.append((running + w / 2.0, v))
        running += w

    # Antes do primeiro centro: devolve o primeiro valor.
    if target <= centers[0][0]:
        return centers[0][1]
    # Depois do último centro: devolve o último valor.
    if target >= centers[-1][0]:
        return centers[-1][1]
    # Interpolação linear entre centros consecutivos.
    for i in range(1, len(centers)):
        pos, val = centers[i]
        if pos >= target:
            prev_pos, prev_val = centers[i - 1]
            frac = (target - prev_pos) / (pos - prev_pos)
            return prev_val + frac * (val - prev_val)
    return centers[-1][1]  # unreachable, mas mypy gosta


def weighted_median(values: Iterable[float], weights: Iterable[float]) -> float:
    return weighted_quantile(values, weights, 0.5)


# ---------------------------------------------------------------------------
# Trim de outliers por IQR ponderado.
# ---------------------------------------------------------------------------
def trim_outliers(comps: list[Comparable], k: float = 1.5) -> list[Comparable]:
    """Remove comparáveis fora de [Q1 − k·IQR, Q3 + k·IQR] (Tukey).

    Robusto a amostras pequenas: se < 4 itens, devolve a lista original.
    """
    if len(comps) < 4:
        return comps
    ppm2 = [c.ppm2 for c in comps]
    weights = [c.weight for c in comps]
    q1 = weighted_quantile(ppm2, weights, 0.25)
    q3 = weighted_quantile(ppm2, weights, 0.75)
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    kept = [c for c in comps if lo <= c.ppm2 <= hi]
    # Garante mínimo: se tivesse 4 e cortou demais, devolve original.
    return kept if len(kept) >= 3 else comps


# ---------------------------------------------------------------------------
# Coeficiente de variação (CV) — usado para classificar confidence.
# ---------------------------------------------------------------------------
def coefficient_of_variation(values: Iterable[float]) -> float:
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return 0.0
    mean = statistics.fmean(vals)
    if mean <= 0:
        return float("inf")
    sd = statistics.pstdev(vals)
    return sd / mean


# ---------------------------------------------------------------------------
# Mapeamento confidence (acompanha cma_min_comparables_*).
# ---------------------------------------------------------------------------
def classify_confidence(
    n_comparables: int,
    cv: float,
    *,
    min_acceptable: int = 3,
    min_confident: int = 5,
) -> Confidence:
    """Classifica em HIGH / MEDIUM / LOW / INSUFFICIENT.

    Regras (sintonizáveis):
      ≥ 8 comparáveis e CV < 0.20  → HIGH
      ≥ min_confident e CV < 0.30  → MEDIUM
      ≥ min_acceptable             → LOW
      caso contrário               → INSUFFICIENT
    """
    if n_comparables < min_acceptable:
        return "INSUFFICIENT"
    if n_comparables >= 8 and cv < 0.20:
        return "HIGH"
    if n_comparables >= min_confident and cv < 0.30:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Função principal: estima o preço a partir de comparáveis e área-alvo.
# ---------------------------------------------------------------------------
def estimate_price(
    target_area_m2: float | None,
    comparables: list[Comparable],
    *,
    min_acceptable: int = 3,
    min_confident: int = 5,
    trim: bool = True,
) -> Valuation:
    """Devolve uma ``Valuation`` (preço central + intervalo + confidence).

    Se houver < ``min_acceptable`` comparáveis ou área-alvo inválida,
    devolve ``confidence=INSUFFICIENT`` com preços ``None``.
    """
    n0 = len(comparables)

    if not target_area_m2 or target_area_m2 <= 0:
        return Valuation(
            estimated_price=None,
            price_lower_bound=None,
            price_upper_bound=None,
            ppm2_estimated=None,
            confidence="INSUFFICIENT",
            method="weighted_median_ppm2",
            comparables_used=n0,
        )

    if n0 < min_acceptable:
        return Valuation(
            estimated_price=None,
            price_lower_bound=None,
            price_upper_bound=None,
            ppm2_estimated=None,
            confidence="INSUFFICIENT",
            method="weighted_median_ppm2",
            comparables_used=n0,
        )

    comps = trim_outliers(comparables) if trim else list(comparables)
    ppm2_values = [c.ppm2 for c in comps]
    weights = [c.weight for c in comps]

    ppm2_est = weighted_median(ppm2_values, weights)
    p10 = weighted_quantile(ppm2_values, weights, 0.10)
    p90 = weighted_quantile(ppm2_values, weights, 0.90)

    cv = coefficient_of_variation(ppm2_values)
    confidence = classify_confidence(
        len(comps),
        cv,
        min_acceptable=min_acceptable,
        min_confident=min_confident,
    )

    return Valuation(
        estimated_price=round(ppm2_est * target_area_m2, 2),
        price_lower_bound=round(p10 * target_area_m2, 2),
        price_upper_bound=round(p90 * target_area_m2, 2),
        ppm2_estimated=round(ppm2_est, 2),
        confidence=confidence,
        method="weighted_median_ppm2",
        comparables_used=len(comps),
    )


__all__ = [
    "Comparable",
    "Valuation",
    "weighted_quantile",
    "weighted_median",
    "trim_outliers",
    "coefficient_of_variation",
    "classify_confidence",
    "estimate_price",
]
