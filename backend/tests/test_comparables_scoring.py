"""Testes do módulo de scoring do AGENTE 2."""

from __future__ import annotations

import pytest

from app.agents.comparables.scoring import (
    RELIABILITY_THRESHOLD,
    condo_match_score,
    haversine_m,
    normalize_condo_name,
    reliability_score,
    similarity_score,
)


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
