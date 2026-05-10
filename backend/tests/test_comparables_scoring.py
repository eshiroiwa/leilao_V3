"""Testes do módulo de scoring do AGENTE 2."""

from __future__ import annotations

import pytest

from app.agents.comparables.scoring import (
    RELIABILITY_THRESHOLD,
    area_outside_tolerance,
    condo_match_score,
    haversine_m,
    is_likely_target_self,
    normalize_condo_name,
    reliability_score,
    similarity_score,
)
from app.agents.comparables.type_config import _BY_TYPE


# =============================================================================
# haversine_m
# =============================================================================
def test_haversine_zero() -> None:
    assert haversine_m(-23.55, -46.63, -23.55, -46.63) == 0.0


def test_haversine_known_distance() -> None:
    # Praça da Sé (SP) → Av. Paulista, ~2.5 km
    d = haversine_m(-23.5505, -46.6333, -23.5614, -46.6562)
    assert 2200 < d < 2900, d


def test_haversine_symmetric() -> None:
    a = haversine_m(-23.5, -46.6, -22.9, -43.2)
    b = haversine_m(-22.9, -43.2, -23.5, -46.6)
    assert abs(a - b) < 1e-6


# =============================================================================
# similarity_score
# =============================================================================
@pytest.fixture
def target() -> dict:
    return {
        "latitude": -23.5505,
        "longitude": -46.6333,
        "area_total_m2": 70.0,
        "bedrooms": 2,
        "parking_spaces": 1,
        "property_type": "apartamento",
        "condo_name": "Edifício Park Crispim",
    }


def test_similarity_identical_is_max(target: dict) -> None:
    """Imóvel idêntico (mesmo prédio) tem similaridade ~1.0."""
    score = similarity_score(target, target)
    assert score > 0.95, score


def test_similarity_identical_without_condo_caps_at_seventy_five(target: dict) -> None:
    """Sem ``condo_name`` em ambos os lados, a dimensão "condo" zera —
    o teto vira ``1 - peso_condo = 0.75`` mesmo com distância zero.
    Isso é deliberado: ausência de condo_name == sem evidência."""
    no_condo = {k: v for k, v in target.items() if k != "condo_name"}
    score = similarity_score(no_condo, no_condo)
    assert 0.74 < score <= 0.76, score


def test_similarity_far_away_zeroes_distance_component(target: dict) -> None:
    """SP→RJ (~360 km): a componente de distância vira 0; o que sobra é o
    máximo possível das outras componentes (= 1 - peso_distância = 0.70
    quando há condo match)."""
    far = {**target, "latitude": -22.9068, "longitude": -43.1729}
    score = similarity_score(target, far)
    # 0.25 (area) + 0.25 (condo) + 0.10 (bedrooms) + 0.10 (parking) = 0.70
    assert 0.69 < score <= 0.71, score


def test_similarity_different_area(target: dict) -> None:
    big = {**target, "area_total_m2": 200.0}  # ~3x maior
    score = similarity_score(target, big)
    # Área agora é peso 0.25; ainda derruba bastante o score.
    assert score < 0.80, score


def test_similarity_missing_geo_returns_partial(target: dict) -> None:
    no_geo = {**target, "latitude": None, "longitude": None}
    score = similarity_score(target, no_geo)
    # Sem distância (peso 0.30), com condo match → max = 0.70.
    assert 0.69 < score <= 0.71, score


def test_similarity_clamped() -> None:
    score = similarity_score({}, {})
    assert 0.0 <= score <= 1.0


def test_similarity_same_condo_boosts_significantly(target: dict) -> None:
    """Mesmo prédio em distância similar deve pontuar mais que prédio
    diferente equivalente."""
    same_condo = {**target, "condo_name": "EDIFÍCIO PARK CRISPIM"}  # variações ok
    diff_condo = {**target, "condo_name": "Residencial Vila Nova"}
    s_same = similarity_score(target, same_condo)
    s_diff = similarity_score(target, diff_condo)
    # condo pesa 0.25, então diferença esperada é exatamente ~0.25.
    assert s_same - s_diff >= 0.20, (s_same, s_diff)


# =============================================================================
# condo_match_score / normalize_condo_name
# =============================================================================
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Edifício Park Crispim", "park crispim"),
        ("EDIF. PARK CRISPIM", "park crispim"),
        ("Residencial Vila Verde", "vila verde"),
        ("Cond. Cristal das Águas", "cristal das aguas"),
        ("Conjunto João Pessoa", "joao pessoa"),
        (None, ""),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_condo_name(raw: str | None, expected: str) -> None:
    assert normalize_condo_name(raw) == expected


def test_condo_match_exact() -> None:
    assert condo_match_score("Edifício Park Crispim", "EDIF PARK CRISPIM") == 1.0


def test_condo_match_with_extra_tokens() -> None:
    """Nome estendido com 'Apto X' deve casar com nome curto, desde que
    todos os tokens da menor estejam contidos na maior."""
    assert (
        condo_match_score("Park Crispim", "Edifício Park Crispim Apto 12") == 1.0
    )


def test_condo_match_single_token_no_match() -> None:
    """1 token comum não é suficiente — evita falso positivo em nomes
    genéricos ('Park', 'Solar', 'Jardim')."""
    assert condo_match_score("Park Crispim", "Park dos Pinheiros") == 0.0


def test_condo_match_different_names() -> None:
    assert condo_match_score("Edifício Vila Verde", "Edifício Park Crispim") == 0.0


def test_condo_match_one_side_empty() -> None:
    assert condo_match_score(None, "Edifício X") == 0.0
    assert condo_match_score("Edifício X", None) == 0.0
    assert condo_match_score("", "") == 0.0


# =============================================================================
# reliability_score
# =============================================================================
def _baseline_listing() -> dict:
    return {
        "street": "Rua das Flores",
        "geocoding_confidence": "HIGH",
        "area_total_m2": 70.0,
        "bedrooms": 2,
        "bathrooms": 1,
        "photos_count": 8,
        "listed_price": 500_000.00,
        "advertiser_type": "imobiliaria",
    }


def test_reliability_full_signals_is_high() -> None:
    score = reliability_score(_baseline_listing())
    assert score >= 0.90, score


def test_reliability_rejected_geo_drops_below_threshold() -> None:
    listing = _baseline_listing() | {"geocoding_confidence": "REJECTED"}
    assert reliability_score(listing) < RELIABILITY_THRESHOLD


def test_reliability_no_address_drops() -> None:
    listing = _baseline_listing() | {"street": "", "geocoding_confidence": "POSTAL_CODE"}
    score = reliability_score(listing)
    # perde 0.25 (street) + 0.20 (geo HIGH→POSTAL_CODE)
    assert 0.40 < score < 0.55, score


def test_reliability_minimal_listing_below_threshold() -> None:
    minimal = {"listed_price": 100_000.00}
    assert reliability_score(minimal) < RELIABILITY_THRESHOLD


def test_reliability_clamped() -> None:
    weird = _baseline_listing() | {"advertiser_type": "carinha-da-esquina"}
    assert 0.0 <= reliability_score(weird) <= 1.0


def test_reliability_postal_code_cap() -> None:
    """POSTAL_CODE indica geo só ao nível de CEP — útil, mas nunca pode
    ser tão confiável quanto HIGH/MEDIUM."""
    listing = _baseline_listing() | {"geocoding_confidence": "POSTAL_CODE"}
    score = reliability_score(listing)
    assert score <= 0.55, score  # cap aplicado


# =============================================================================
# is_likely_target_self
#
# Cenário canônico: o anúncio do PRÓPRIO IMÓVEL DO LEILÃO num portal
# de mercado (chavesnamao etc.). Bate em: distância < 50m + área
# idêntica + preço == minimum_bid_first/second/appraisal.
# =============================================================================
def _self_target() -> dict:
    return {
        "latitude": -20.5586,
        "longitude": -48.5687,
        "area_total_m2": 200.0,
        "area_built_m2": 145.0,
        "property_type": "casa",
        "minimum_bid_first": 350_000.0,
        "minimum_bid_second": 280_000.0,
        "appraisal_value": 500_000.0,
    }


def test_is_self_when_distance_area_and_price_match_first_bid() -> None:
    target = _self_target()
    comp = {
        "latitude": target["latitude"] + 0.0001,  # ~11m
        "longitude": target["longitude"] + 0.0001,
        "area_total_m2": 200.0,
        "area_built_m2": 145.0,
        "property_type": "casa",
        "listed_price": 350_500.0,  # ~0.14% do bid_first
    }
    assert is_likely_target_self(target, comp) is True


def test_is_self_matches_appraisal_value_too() -> None:
    target = _self_target()
    comp = {
        "latitude": target["latitude"],
        "longitude": target["longitude"],
        "area_total_m2": 200.0,
        "area_built_m2": 145.0,
        "property_type": "casa",
        "listed_price": 500_000.0,  # bate com appraisal_value exato
    }
    assert is_likely_target_self(target, comp) is True


def test_not_self_when_far_away() -> None:
    target = _self_target()
    comp = {
        "latitude": target["latitude"] + 0.005,  # ~550m
        "longitude": target["longitude"],
        "area_total_m2": 200.0,
        "area_built_m2": 145.0,
        "property_type": "casa",
        "listed_price": 350_000.0,
    }
    assert is_likely_target_self(target, comp) is False


def test_not_self_when_area_diverges() -> None:
    target = _self_target()
    comp = {
        "latitude": target["latitude"],
        "longitude": target["longitude"],
        "area_total_m2": 250.0,  # +25% — fora dos 2%
        "area_built_m2": 180.0,
        "property_type": "casa",
        "listed_price": 350_000.0,
    }
    assert is_likely_target_self(target, comp) is False


def test_not_self_when_price_diverges_from_all_refs() -> None:
    target = _self_target()
    comp = {
        "latitude": target["latitude"],
        "longitude": target["longitude"],
        "area_total_m2": 200.0,
        "area_built_m2": 145.0,
        "property_type": "casa",
        "listed_price": 800_000.0,  # nem bid_1, nem bid_2, nem appraisal
    }
    assert is_likely_target_self(target, comp) is False


def test_not_self_without_geo_data() -> None:
    """Sem latitude/longitude não dá pra afirmar self — conservador."""
    target = _self_target()
    comp = {
        "latitude": None,
        "longitude": None,
        "area_total_m2": 200.0,
        "area_built_m2": 145.0,
        "property_type": "casa",
        "listed_price": 350_000.0,
    }
    assert is_likely_target_self(target, comp) is False


# =============================================================================
# area_outside_tolerance
#
# Hard filter de área: rejeita comparáveis muito maiores/menores que
# o alvo segundo a TypeConfig. Apartamento ±35%, casa ±50%, ...
# =============================================================================
def test_apt_50pct_bigger_is_rejected_strict() -> None:
    """Apartamento alvo 70m² × comp 105m² (=+50%) > 35% → rejeita."""
    target = {"property_type": "apartamento", "area_built_m2": 70.0}
    comp = {"area_built_m2": 105.0}
    reason = area_outside_tolerance(target, comp)
    assert reason is not None
    assert "area_outside_tolerance" in reason


def test_apt_50pct_bigger_passes_relaxed() -> None:
    """Mesmo caso com ``relaxed=True`` (±55%): 50% < 55% → passa."""
    target = {"property_type": "apartamento", "area_built_m2": 70.0}
    comp = {"area_built_m2": 105.0}
    assert area_outside_tolerance(target, comp, relaxed=True) is None


def test_house_uses_built_not_total_for_filter() -> None:
    """Casa de 250m² de TERRENO + 145m² CONSTRUÍDOS vs comp 220m² de
    terreno + 140m² construídos.

    Se o filtro usasse ``area_total_m2``, a diferença seria
    |220-250|/250=12% (passa). Mas o que importa é construído:
    |140-145|/145=3% (também passa). O ponto deste teste é
    GARANTIR que o ``area_field='auto'`` resolveu para built (E5)."""
    target = {
        "property_type": "casa",
        "area_total_m2": 250.0,
        "area_built_m2": 145.0,
    }
    comp = {"area_total_m2": 220.0, "area_built_m2": 140.0}
    assert area_outside_tolerance(target, comp) is None


def test_house_built_area_diff_rejects_even_if_total_close() -> None:
    """Casa alvo 145m² construídos × comp com 250m² construídos
    (=+72%, > 50% strict). Rejeita pelo construído mesmo que terreno
    seja parecido (que é exatamente o bug que a P0.3 corrige)."""
    target = {
        "property_type": "casa",
        "area_total_m2": 250.0,
        "area_built_m2": 145.0,
    }
    comp = {"area_total_m2": 240.0, "area_built_m2": 250.0}
    reason = area_outside_tolerance(target, comp)
    assert reason is not None


def test_terreno_filter_uses_total_field() -> None:
    """Terreno alvo 1000m² × comp 1100m² → diff 10%, passa.
    Comp 2000m² → diff 100%, rejeita strict (área_hard_max=50%)."""
    target = {"property_type": "terreno", "area_total_m2": 1000.0}
    assert area_outside_tolerance(target, {"area_total_m2": 1100.0}) is None
    reason = area_outside_tolerance(target, {"area_total_m2": 2000.0})
    assert reason is not None


def test_no_filter_when_areas_missing() -> None:
    """Filtro silenciosamente passa se faltar área de qualquer dos lados
    — o filtro de "sem preço/área" do score cobre o caso totalmente
    vazio."""
    target = {"property_type": "casa", "area_built_m2": 145.0}
    assert area_outside_tolerance(target, {}) is None
    assert (
        area_outside_tolerance({"property_type": "casa"}, {"area_built_m2": 145.0})
        is None
    )


# =============================================================================
# similarity_score: invariantes do P0.3 (area_field correto por tipo)
# =============================================================================
def test_similarity_house_uses_built_not_total() -> None:
    """Casa alvo 145m² construídos × terreno 250m² no banco. Comp
    com mesma metragem construída (140m²) mas terreno totalmente
    diferente (1000m²) deve pontuar ALTO no eixo área — o terreno
    é irrelevante pra preço de casa de rua."""
    target = {
        "property_type": "casa",
        "latitude": -23.5,
        "longitude": -46.6,
        "area_total_m2": 250.0,
        "area_built_m2": 145.0,
    }
    comp_same_built = {
        "property_type": "casa",
        "latitude": -23.5,
        "longitude": -46.6,
        "area_total_m2": 1000.0,  # terreno bem maior
        "area_built_m2": 140.0,  # mas construção parecida
    }
    comp_diff_built = {
        "property_type": "casa",
        "latitude": -23.5,
        "longitude": -46.6,
        "area_total_m2": 240.0,  # terreno parecido
        "area_built_m2": 50.0,  # mas construção bem menor
    }
    s_same = similarity_score(target, comp_same_built)
    s_diff = similarity_score(target, comp_diff_built)
    assert s_same > s_diff, (s_same, s_diff)


def test_similarity_uses_explicit_config() -> None:
    """Passar ``config`` explicitamente sobrescreve o auto-detect.
    Útil para A/B em produção sem mudar o property_type."""
    # Mesma área em "total" e "built" para isolar o efeito do sigma.
    target = {
        "property_type": "apartamento",
        "latitude": -23.5,
        "longitude": -46.6,
        "area_total_m2": 70.0,
        "area_built_m2": 70.0,
    }
    comp = {
        "latitude": -23.5,
        "longitude": -46.6,
        "area_total_m2": 80.0,
        "area_built_m2": 80.0,
    }
    sigma_apt = similarity_score(target, comp)
    sigma_rural = similarity_score(target, comp, config=_BY_TYPE["rural"])
    # Sigma maior (rural=0.50 vs apartamento=0.15) → score de área MAIOR
    # para a mesma diferença → similarity total >= apt.
    assert sigma_rural >= sigma_apt
