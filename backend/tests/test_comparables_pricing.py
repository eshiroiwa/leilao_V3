"""Testes do módulo de pricing do AGENTE 2."""

from __future__ import annotations

import pytest

from app.agents.comparables.pricing import (
    Comparable,
    classify_confidence,
    coefficient_of_variation,
    estimate_price,
    trim_outliers,
    weighted_median,
    weighted_quantile,
)


# =============================================================================
# weighted_quantile / weighted_median
# =============================================================================
def test_weighted_median_uniform() -> None:
    # Pesos iguais → mediana clássica
    assert weighted_median([1, 2, 3, 4, 5], [1, 1, 1, 1, 1]) == 3.0


def test_weighted_median_skewed() -> None:
    # Peso enorme em um valor → mediana puxa para ele
    m = weighted_median([1, 2, 3, 100], [1, 1, 1, 100])
    assert m > 50, m


def test_weighted_quantile_extremes() -> None:
    vals = [10, 20, 30, 40, 50]
    w = [1] * 5
    assert weighted_quantile(vals, w, 0.0) == 10.0
    assert weighted_quantile(vals, w, 1.0) == 50.0


def test_weighted_quantile_ignores_zero_weights() -> None:
    m = weighted_median([1, 999, 3, 999, 5], [1, 0, 1, 0, 1])
    assert m == 3.0


def test_weighted_quantile_invalid_q() -> None:
    with pytest.raises(ValueError):
        weighted_quantile([1, 2], [1, 1], 1.5)


def test_weighted_quantile_empty_raises() -> None:
    with pytest.raises(ValueError):
        weighted_quantile([], [], 0.5)


# =============================================================================
# trim_outliers
# =============================================================================
def test_trim_outliers_removes_extremes() -> None:
    base = [Comparable(f"id-{i}", ppm2=10000.0, weight=1.0) for i in range(8)]
    base.append(Comparable("OUTLIER", ppm2=999_999.0, weight=1.0))
    kept = trim_outliers(base)
    assert all(c.listing_id != "OUTLIER" for c in kept)
    assert len(kept) == 8


def test_trim_outliers_keeps_when_few() -> None:
    base = [Comparable(f"id-{i}", ppm2=10000.0, weight=1.0) for i in range(3)]
    assert trim_outliers(base) == base


# =============================================================================
# coefficient_of_variation / classify_confidence
# =============================================================================
def test_cv_low_for_uniform() -> None:
    assert coefficient_of_variation([100, 100, 100, 100]) == 0.0


def test_cv_high_for_disperse() -> None:
    cv = coefficient_of_variation([100, 200, 50, 300, 80])
    assert cv > 0.5, cv


@pytest.mark.parametrize(
    ("n", "cv", "expected"),
    [
        (10, 0.10, "HIGH"),
        (8, 0.19, "HIGH"),
        (8, 0.25, "MEDIUM"),
        (5, 0.20, "MEDIUM"),
        (5, 0.40, "LOW"),
        (3, 0.10, "LOW"),
        (2, 0.10, "INSUFFICIENT"),
        (0, 0.0, "INSUFFICIENT"),
    ],
)
def test_classify_confidence(n: int, cv: float, expected: str) -> None:
    assert classify_confidence(n, cv) == expected


# =============================================================================
# estimate_price (cenários completos)
# =============================================================================
def _make_comps(ppm2_list: list[float], weight: float = 1.0) -> list[Comparable]:
    return [
        Comparable(f"id-{i}", ppm2=p, weight=weight)
        for i, p in enumerate(ppm2_list)
    ]


def test_estimate_price_high_confidence() -> None:
    # 10 comparáveis muito uniformes → HIGH
    comps = _make_comps([10_000, 10_100, 9_900, 10_050, 9_950,
                          10_200, 9_800, 10_150, 9_850, 10_050])
    val = estimate_price(target_area_m2=70.0, comparables=comps)
    assert val.confidence == "HIGH"
    assert val.estimated_price is not None
    assert 690_000 <= val.estimated_price <= 715_000


def test_estimate_price_medium_confidence() -> None:
    # 5 comparáveis, dispersão moderada
    comps = _make_comps([8_000, 9_500, 11_000, 10_000, 10_500])
    val = estimate_price(target_area_m2=80.0, comparables=comps)
    assert val.confidence == "MEDIUM"
    assert val.price_lower_bound is not None
    assert val.price_upper_bound is not None
    assert val.price_lower_bound < val.estimated_price < val.price_upper_bound  # type: ignore[operator]


def test_estimate_price_low_confidence() -> None:
    # 3 comparáveis → LOW
    comps = _make_comps([8_000, 12_000, 10_000])
    val = estimate_price(target_area_m2=50.0, comparables=comps)
    assert val.confidence == "LOW"
    assert val.estimated_price is not None


def test_estimate_price_insufficient() -> None:
    comps = _make_comps([10_000, 10_500])  # 2 < min_acceptable=3
    val = estimate_price(target_area_m2=70.0, comparables=comps)
    assert val.confidence == "INSUFFICIENT"
    assert val.estimated_price is None
    assert val.price_lower_bound is None
    assert val.price_upper_bound is None


def test_estimate_price_no_target_area() -> None:
    comps = _make_comps([10_000] * 10)
    val = estimate_price(target_area_m2=None, comparables=comps)
    assert val.confidence == "INSUFFICIENT"
    assert val.estimated_price is None


def test_estimate_price_weights_skew_estimate() -> None:
    """Comparável com peso muito maior 'puxa' a mediana."""
    comps = [
        Comparable("a", ppm2=8_000.0, weight=0.3),
        Comparable("b", ppm2=8_000.0, weight=0.3),
        Comparable("c", ppm2=8_000.0, weight=0.3),
        Comparable("d", ppm2=12_000.0, weight=10.0),  # peso enorme
    ]
    val = estimate_price(target_area_m2=100.0, comparables=comps, trim=False)
    assert val.estimated_price is not None
    assert val.estimated_price >= 1_100_000  # puxado pelo peso 10x


def test_estimate_price_interval_contains_estimate() -> None:
    comps = _make_comps([7_000, 8_000, 9_000, 10_000, 11_000, 12_000, 13_000])
    val = estimate_price(target_area_m2=100.0, comparables=comps)
    assert val.price_lower_bound is not None
    assert val.price_upper_bound is not None
    assert val.estimated_price is not None
    assert val.price_lower_bound <= val.estimated_price <= val.price_upper_bound
