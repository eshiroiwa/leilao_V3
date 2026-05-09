"""Testes do módulo de pricing do AGENTE 2."""

from __future__ import annotations

import pytest

from app.agents.comparables.pricing import (
    Comparable,
    classify_confidence,
    coefficient_of_variation,
    detect_bimodal_ppm2,
    effective_target_area_m2,
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


# =============================================================================
# Modo "same building" (Entrega 3)
# =============================================================================
def _comp(idx: int, ppm2: float, weight: float = 1.0, *, same_building: bool = False) -> Comparable:
    return Comparable(
        listing_id=f"id-{idx}", ppm2=ppm2, weight=weight, same_building=same_building
    )


def test_same_building_mode_uses_only_same_building_comps() -> None:
    """3+ comparáveis do mesmo prédio acionam o modo dedicado: a mediana
    ignora completamente os comparáveis de outros prédios (mesmo que
    tenham peso alto). Isso evita que prédios premium puxem o preço."""
    same = [
        _comp(0, 6_000, weight=1.0, same_building=True),
        _comp(1, 6_200, weight=1.0, same_building=True),
        _comp(2, 5_800, weight=1.0, same_building=True),
    ]
    other = [
        _comp(3, 12_000, weight=1.0, same_building=False),  # outro prédio premium
        _comp(4, 11_500, weight=1.0, same_building=False),
    ]
    val = estimate_price(target_area_m2=80.0, comparables=same + other)
    assert val.method == "same_building_median_ppm2"
    assert val.comparables_used == 3
    # Mediana dos 3 do mesmo prédio = 6.000.
    assert val.ppm2_estimated is not None
    assert 5_900 <= val.ppm2_estimated <= 6_100, val.ppm2_estimated
    # Estimated price = 6.000 × 80 = 480.000 (não os 12k × 80 = 960k).
    assert val.estimated_price is not None
    assert 470_000 <= val.estimated_price <= 490_000, val.estimated_price


def test_same_building_mode_high_confidence_when_5_plus() -> None:
    same = [_comp(i, 6_000 + i * 50, same_building=True) for i in range(5)]
    val = estimate_price(target_area_m2=80.0, comparables=same)
    assert val.confidence == "HIGH"


def test_same_building_mode_medium_confidence_with_3_4() -> None:
    same = [_comp(i, 6_000 + i * 50, same_building=True) for i in range(3)]
    val = estimate_price(target_area_m2=80.0, comparables=same)
    assert val.confidence == "MEDIUM"


def test_same_building_mode_skipped_when_only_2_match() -> None:
    """Apenas 2 comparáveis do mesmo prédio NÃO ativa o modo — cai no
    pricing tradicional usando todos os comparáveis."""
    same = [_comp(i, 6_000, same_building=True) for i in range(2)]
    other = [_comp(i + 10, 12_000, same_building=False) for i in range(3)]
    val = estimate_price(target_area_m2=80.0, comparables=same + other)
    assert val.method == "weighted_median_ppm2"
    # Pega os 5 → mediana puxa pra cima dos 12k (não dos 6k).
    assert val.estimated_price is not None
    assert val.estimated_price > 600_000


# =============================================================================
# Trim adaptativo para apartamentos (Entrega 4)
# =============================================================================
def test_apartamento_trim_more_aggressive_than_default() -> None:
    """Para apartamento, o trim usa k=1.0 (em vez de 1.5), que corta
    melhor outliers de prédios premium misturados."""
    # 8 a 6k–7k + 2 outliers em 12k (prédio premium).
    base = [_comp(i, 6_500 + i * 100) for i in range(8)]
    outliers = [_comp(8, 12_000), _comp(9, 12_500)]
    comps = base + outliers

    val_default = estimate_price(
        target_area_m2=80.0, comparables=comps, property_type="casa"
    )
    val_apto = estimate_price(
        target_area_m2=80.0, comparables=comps, property_type="apartamento"
    )
    # Os outliers entram (em parte) no cálculo da mediana padrão (k=1.5);
    # com k=1.0 (apartamento), o trim derruba mais os 12k.
    assert val_apto.ppm2_estimated is not None
    assert val_default.ppm2_estimated is not None
    assert val_apto.comparables_used <= val_default.comparables_used


# =============================================================================
# Detecção de bimodalidade (Entrega 4)
# =============================================================================
def test_detect_bimodal_two_clear_clusters() -> None:
    """Cluster baixo (~6k) e cluster alto (~12k) com gap >100% → bimodal."""
    comps = [
        _comp(0, 6_000),
        _comp(1, 6_200),
        _comp(2, 6_500),
        _comp(3, 12_000),
        _comp(4, 12_300),
    ]
    assert detect_bimodal_ppm2(comps, gap_pct=0.30, min_each_side=2) is True


def test_detect_bimodal_one_cluster_returns_false() -> None:
    """Distribuição contínua (sem gap claro) → não é bimodal."""
    comps = [_comp(i, 6_000 + i * 200) for i in range(10)]
    assert detect_bimodal_ppm2(comps, gap_pct=0.30, min_each_side=2) is False


def test_detect_bimodal_small_sample_returns_false() -> None:
    """Amostras pequenas não dão evidência suficiente."""
    comps = [_comp(0, 6_000), _comp(1, 12_000)]
    assert detect_bimodal_ppm2(comps, gap_pct=0.30, min_each_side=2) is False


# =============================================================================
# effective_target_area_m2 — escolha do campo de área coerente com o tipo
# =============================================================================
def test_effective_area_apartamento_prefers_built_over_total() -> None:
    """Bug do Crispim/Pindamonhangaba: matrícula traz total=87.96 mas a área
    de mercado é a built=44.01. Não pode multiplicar ppm2 (de mercado) pela
    área da matrícula."""
    target = {
        "property_type": "apartamento",
        "area_total_m2": 87.96,
        "area_built_m2": 44.01,
    }
    area, source = effective_target_area_m2(target)
    assert area == 44.01
    assert source == "area_built_m2"


def test_effective_area_apartamento_falls_back_to_useful() -> None:
    target = {
        "property_type": "apartamento",
        "area_total_m2": 90.0,
        "area_useful_m2": 50.0,
    }
    area, source = effective_target_area_m2(target)
    assert area == 50.0
    assert source == "area_useful_m2"


def test_effective_area_apartamento_uses_total_when_only_field() -> None:
    target = {"property_type": "apartamento", "area_total_m2": 60.0}
    area, source = effective_target_area_m2(target)
    assert area == 60.0
    assert source == "area_total_m2"


def test_effective_area_casa_prefers_built() -> None:
    """Em casas, area_total pode incluir terreno; built é mais comparável
    com o que portais anunciam."""
    target = {
        "property_type": "casa",
        "area_total_m2": 250.0,
        "area_built_m2": 120.0,
    }
    area, source = effective_target_area_m2(target)
    assert area == 120.0
    assert source == "area_built_m2"


def test_effective_area_terreno_uses_total() -> None:
    """Para terrenos a área de mercado É a área total (não há "construída")."""
    target = {
        "property_type": "terreno",
        "area_total_m2": 500.0,
        "area_built_m2": 0,
    }
    area, source = effective_target_area_m2(target)
    assert area == 500.0
    assert source == "area_total_m2"


def test_effective_area_unknown_type_falls_back_to_total() -> None:
    target = {"property_type": None, "area_total_m2": 70.0, "area_built_m2": 40.0}
    area, source = effective_target_area_m2(target)
    assert area == 70.0
    assert source == "area_total_m2"


def test_effective_area_returns_none_when_no_valid_field() -> None:
    target = {"property_type": "apartamento", "area_total_m2": 0, "area_built_m2": None}
    area, source = effective_target_area_m2(target)
    assert area is None
    assert source is None


def test_effective_area_handles_none_target() -> None:
    assert effective_target_area_m2(None) == (None, None)
    assert effective_target_area_m2({}) == (None, None)


def test_effective_area_ignores_invalid_string_values() -> None:
    """area_built_m2 vier como string lixo → cai pro próximo campo válido."""
    target = {
        "property_type": "apartamento",
        "area_built_m2": "n/a",
        "area_useful_m2": 45.0,
        "area_total_m2": 90.0,
    }
    area, source = effective_target_area_m2(target)
    assert area == 45.0
    assert source == "area_useful_m2"


def test_effective_area_property_type_case_insensitive() -> None:
    target = {
        "property_type": "APARTAMENTO",
        "area_total_m2": 80.0,
        "area_built_m2": 40.0,
    }
    area, source = effective_target_area_m2(target)
    assert area == 40.0
    assert source == "area_built_m2"
