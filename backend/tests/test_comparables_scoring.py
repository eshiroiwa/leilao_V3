"""Testes do módulo de scoring do AGENTE 2."""

from __future__ import annotations

import pytest

from app.agents.comparables.scoring import (
    RELIABILITY_THRESHOLD,
    haversine_m,
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
    }


def test_similarity_identical_is_max(target: dict) -> None:
    score = similarity_score(target, target)
    assert score > 0.95, score


def test_similarity_far_away_zeroes_distance_component(target: dict) -> None:
    """SP→RJ (~360 km): a componente de distância vira 0; o que sobra é o
    máximo possível das outras componentes (= 1 - peso_distância = 0.60).

    Nota: na prática, o pipeline filtra por raio ANTES de chamar
    similarity_score, então esse caso nunca chega aqui em produção.
    Este teste garante que a função é matematicamente bem-definida.
    """
    far = {**target, "latitude": -22.9068, "longitude": -43.1729}
    score = similarity_score(target, far)
    assert 0.59 < score <= 0.60, score


def test_similarity_different_type_drops(target: dict) -> None:
    diff = {**target, "property_type": "terreno"}
    score = similarity_score(target, diff)
    # tipo conta 0.05, ainda fica alto pelos outros fatores
    assert 0.85 < score < 0.96, score


def test_similarity_different_area(target: dict) -> None:
    big = {**target, "area_total_m2": 200.0}  # ~3x maior
    score = similarity_score(target, big)
    assert score < 0.75, score  # área é peso 0.30


def test_similarity_missing_geo_returns_partial(target: dict) -> None:
    no_geo = {**target, "latitude": None, "longitude": None}
    score = similarity_score(target, no_geo)
    # sem distância (peso 0.40), max teórico = 0.60
    assert 0.55 < score <= 0.60, score


def test_similarity_clamped() -> None:
    score = similarity_score({}, {})
    assert 0.0 <= score <= 1.0


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
