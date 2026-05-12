"""Testes dos nós PUROS do AGENTE 4 (sem rede, sem LLM).

Esses testes garantem que a parte mais sensível do agente — as decisões
estatísticas — é determinística e robusta.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from unittest.mock import MagicMock

from app.agents.deep.nodes.neighborhood_class import classify_neighborhood
from app.agents.deep.nodes.neighborhood_stats import (
    compute_flipping_potential,
    compute_liquidity,
)
from app.agents.deep.nodes.outlier import compute_outlier
from app.agents.deep.nodes.price_trend import compute_price_trend


# =============================================================================
# Helpers
# =============================================================================
def _listing(*, area: float, price: float, days_ago: int = 30) -> dict:
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "area_total_m2": area,
        "listed_price": price,
        "scraped_at": when,
    }


# =============================================================================
# Outlier
# =============================================================================
class TestOutlier:
    def test_below_min_neighbors_never_flags(self) -> None:
        """Com menos de 10 vizinhos, NUNCA marca como outlier."""
        neighbors = [_listing(area=80, price=400_000) for _ in range(5)]
        result = compute_outlier(
            target_area_m2=200,  # 2,5× a mediana
            target_price=1_000_000,
            neighbors=neighbors,
        )
        assert result.is_outlier_size is False
        assert result.is_outlier_price is False
        assert result.n_neighbors == 5

    def test_huge_size_flagged_as_outlier(self) -> None:
        # Mediana de 80 m², MAD pequeno → 300 m² é claramente outlier.
        neighbors = [_listing(area=80 + i, price=400_000) for i in range(15)]
        result = compute_outlier(
            target_area_m2=300,
            target_price=400_000,
            neighbors=neighbors,
        )
        assert result.is_outlier_size is True
        assert result.size_zscore is not None and result.size_zscore > 2.0

    def test_typical_size_not_flagged(self) -> None:
        neighbors = [_listing(area=80 + i, price=400_000 + i * 1000) for i in range(15)]
        result = compute_outlier(
            target_area_m2=85,  # bem dentro da distribuição
            target_price=405_000,
            neighbors=neighbors,
        )
        assert result.is_outlier_size is False
        assert result.is_outlier_price is False

    def test_uses_robust_zscore_resistant_to_outliers(self) -> None:
        # 14 áreas em torno de 80 m², 1 mansão de 1000 m²: o robust z-score
        # NÃO deve ser distorcido pela mansão. Um imóvel de 90 m² deve
        # continuar "normal".
        neighbors = [_listing(area=80, price=400_000) for _ in range(14)]
        neighbors.append(_listing(area=1_000, price=10_000_000))
        result = compute_outlier(
            target_area_m2=90,
            target_price=405_000,
            neighbors=neighbors,
        )
        assert result.is_outlier_size is False


# =============================================================================
# Flipping
# =============================================================================
class TestFlipping:
    def test_low_sample_returns_none_score(self) -> None:
        neighbors = [_listing(area=80, price=400_000) for _ in range(5)]
        result = compute_flipping_potential(
            neighbors=neighbors,
            target_price=400_000,
        )
        assert result.score is None
        assert result.evidence["reason"] == "amostra_rasa"

    def test_high_upside_yields_score_5(self) -> None:
        # P90 ≈ 1_000_000; target 500_000 → upside 100% → 5.
        prices = [500_000 + i * 50_000 for i in range(15)]
        neighbors = [_listing(area=80, price=p) for p in prices]
        result = compute_flipping_potential(
            neighbors=neighbors,
            target_price=500_000,
        )
        assert result.score == 5
        assert result.neighborhood_price_max == max(prices)

    def test_no_upside_yields_score_1(self) -> None:
        # P90 < target → upside negativo → 1.
        prices = [500_000 + i * 1_000 for i in range(15)]
        neighbors = [_listing(area=80, price=p) for p in prices]
        result = compute_flipping_potential(
            neighbors=neighbors,
            target_price=600_000,  # já está acima do p90
        )
        assert result.score == 1


# =============================================================================
# Liquidity
# =============================================================================
class TestLiquidity:
    def test_zero_neighbors_score_1_low_confidence(self) -> None:
        result = compute_liquidity(
            neighbors=[], city_population=None, radius_m=2_000,
        )
        assert result.score == 1
        assert result.confidence == "LOW"
        # 0 listings em ~12.57 km² → 0.0
        assert result.listings_per_km2 == 0.0

    def test_30_listings_with_population_high_confidence(self) -> None:
        neighbors = [_listing(area=80, price=400_000) for _ in range(35)]
        result = compute_liquidity(
            neighbors=neighbors, city_population=500_000, radius_m=2_000,
        )
        assert result.score == 5
        assert result.confidence == "HIGH"
        # 35 / (π · 2²) ≈ 2.78
        assert result.listings_per_km2 is not None
        assert 2.5 < result.listings_per_km2 < 3.0

    def test_small_city_penalizes_score(self) -> None:
        """Cidade < 50k habitantes baixa o score em 1."""
        neighbors = [_listing(area=80, price=400_000) for _ in range(35)]
        big = compute_liquidity(
            neighbors=neighbors, city_population=500_000, radius_m=2_000,
        )
        small = compute_liquidity(
            neighbors=neighbors, city_population=10_000, radius_m=2_000,
        )
        assert big.score == 5
        assert small.score == 4


# =============================================================================
# Price trend
# =============================================================================
class TestPriceTrend:
    def test_short_window_low_confidence(self) -> None:
        # Todos scrapeados nos últimos 30 dias — janela curta.
        neighbors = [
            _listing(area=80, price=400_000, days_ago=15) for _ in range(30)
        ]
        result = compute_price_trend(neighbors)
        assert result.confidence == "LOW"
        assert result.trend_pct_12m is None

    def test_appreciation_detected(self) -> None:
        # Listings antigos (300 dias) baratos; recentes (30 dias) caros.
        old = [_listing(area=80, price=400_000, days_ago=300) for _ in range(10)]
        new = [_listing(area=80, price=500_000, days_ago=30) for _ in range(10)]
        result = compute_price_trend(old + new)
        assert result.confidence == "MEDIUM"
        # +25% em 270 dias ≈ +33% anualizado.
        assert result.trend_pct_12m is not None
        assert result.trend_pct_12m > 25

    def test_buckets_unbalanced_low_confidence(self) -> None:
        # 18 listings recentes, 2 antigos — bucket desbalanceado.
        old = [_listing(area=80, price=400_000, days_ago=300) for _ in range(2)]
        new = [_listing(area=80, price=500_000, days_ago=30) for _ in range(18)]
        result = compute_price_trend(old + new)
        assert result.confidence == "LOW"


# =============================================================================
# Neighborhood class + competing neighborhoods
# =============================================================================
def _listing_with_bairro(
    *,
    bairro: str,
    area: float,
    price: float,
    lat: float = -23.5,
    lng: float = -46.6,
) -> dict:
    return {
        "neighborhood": bairro,
        "area_total_m2": area,
        "listed_price": price,
        "latitude": lat,
        "longitude": lng,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


class TestClassifyNeighborhood:
    def _make_supabase(self, listings: list[dict]) -> MagicMock:
        s = MagicMock()
        s.find_listings_near.return_value = listings
        return s

    def test_returns_low_when_no_target_neighborhood(self) -> None:
        result = classify_neighborhood(
            neighborhood=None, lat=-23.5, lng=-46.6,
            supabase=self._make_supabase([]), city_ppm2_brl=10_000,
        )
        assert result.tier is None
        assert result.confidence == "LOW"

    def test_returns_low_when_target_has_few_listings(self) -> None:
        """Bairro-alvo com <5 listings → tier=None, sem classificação."""
        listings = [
            _listing_with_bairro(bairro="Jardins", area=80, price=1_000_000),
            _listing_with_bairro(bairro="Jardins", area=80, price=1_000_000),
        ]
        result = classify_neighborhood(
            neighborhood="Jardins", lat=-23.5, lng=-46.6,
            supabase=self._make_supabase(listings),
            city_ppm2_brl=10_000,
        )
        assert result.tier is None
        assert result.target_ppm2_median is None
        assert result.confidence == "LOW"

    def test_premium_neighborhood_returns_tier_a(self) -> None:
        """ratio > 1.3 → tier A (premium)."""
        # Bairro-alvo: 12 listings (≥ 2×MIN) com ppm² = 20.000 → confidence HIGH.
        premium = [
            _listing_with_bairro(bairro="Jardins", area=80, price=1_600_000)
            for _ in range(12)
        ]
        # Bairro concorrente próximo no ppm² (15.000 vs 20.000).
        comp = [
            _listing_with_bairro(
                bairro="Itaim", area=80, price=1_200_000,
                lat=-23.51, lng=-46.61,
            )
            for _ in range(6)
        ]
        # FipeZAP cidade = 10.000 R$/m² → ratio = 2.0 → tier A.
        result = classify_neighborhood(
            neighborhood="Jardins", lat=-23.5, lng=-46.6,
            supabase=self._make_supabase(premium + comp),
            city_ppm2_brl=10_000,
        )
        assert result.tier == "A"
        assert result.tier_label == "premium"
        assert result.target_ppm2_median == 20_000
        assert result.ratio is not None and result.ratio > 1.3
        # 1 concorrente válido (Itaim, com 6 listings).
        assert len(result.competing_neighborhoods) == 1
        assert result.competing_neighborhoods[0].name == "Itaim"
        assert result.confidence == "HIGH"  # FipeZAP + amostra robusta

    def test_popular_neighborhood_returns_tier_d(self) -> None:
        """ratio < 0.7 → tier D (popular)."""
        target = [
            _listing_with_bairro(bairro="Cohab", area=80, price=400_000)
            for _ in range(6)
        ]
        # ppm² = 5.000, cidade FipeZAP = 10.000 → ratio = 0.5 → D.
        result = classify_neighborhood(
            neighborhood="Cohab", lat=-23.5, lng=-46.6,
            supabase=self._make_supabase(target),
            city_ppm2_brl=10_000,
        )
        assert result.tier == "D"
        assert result.tier_label == "popular"

    def test_top_3_competitors_ordered_by_ppm2_proximity(self) -> None:
        """Concorrentes ordenados pela proximidade do ppm² do bairro-alvo."""
        target = [
            _listing_with_bairro(bairro="Centro", area=80, price=800_000)
            for _ in range(6)
        ]
        # ppm² alvo = 10.000. Concorrentes:
        # A: 11.000 (perto); B: 8.000 (mais longe); C: 9.500 (perto);
        # D: 20.000 (muito longe — não deve entrar no top 3).
        peers = (
            [_listing_with_bairro(bairro="A", area=80, price=880_000) for _ in range(6)]
            + [_listing_with_bairro(bairro="B", area=80, price=640_000) for _ in range(6)]
            + [_listing_with_bairro(bairro="C", area=80, price=760_000) for _ in range(6)]
            + [_listing_with_bairro(bairro="D", area=80, price=1_600_000) for _ in range(6)]
        )
        result = classify_neighborhood(
            neighborhood="Centro", lat=-23.5, lng=-46.6,
            supabase=self._make_supabase(target + peers),
            city_ppm2_brl=10_000,
        )
        names = [c.name for c in result.competing_neighborhoods]
        assert len(names) == 3
        # A (ppm²=11k, |Δ|=1k) e C (9.5k, |Δ|=500) ficam à frente de B (8k, |Δ|=2k).
        assert names[0] in {"A", "C"}
        assert "D" not in names  # ppm² 20k está muito longe do alvo 10k

    def test_falls_back_to_global_median_when_fipezap_absent(self) -> None:
        """Sem FipeZAP, usa mediana global dos listings como referência."""
        target = [
            _listing_with_bairro(bairro="X", area=80, price=800_000)
            for _ in range(6)
        ]
        result = classify_neighborhood(
            neighborhood="X", lat=-23.5, lng=-46.6,
            supabase=self._make_supabase(target),
            city_ppm2_brl=None,
        )
        # Com fallback ratio = 1.0 (mediana = alvo) → tier B.
        assert result.tier == "B"
        assert result.confidence == "MEDIUM"
        assert result.evidence["city_ppm2_source"] == "fallback_global"
