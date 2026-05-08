"""Testes dos nós PUROS do AGENTE 4 (sem rede, sem LLM).

Esses testes garantem que a parte mais sensível do agente — as decisões
estatísticas — é determinística e robusta.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
        result = compute_liquidity(neighbors=[], city_population=None)
        assert result.score == 1
        assert result.confidence == "LOW"

    def test_30_listings_with_population_high_confidence(self) -> None:
        neighbors = [_listing(area=80, price=400_000) for _ in range(35)]
        result = compute_liquidity(neighbors=neighbors, city_population=500_000)
        assert result.score == 5
        assert result.confidence == "HIGH"

    def test_small_city_penalizes_score(self) -> None:
        """Cidade < 50k habitantes baixa o score em 1."""
        neighbors = [_listing(area=80, price=400_000) for _ in range(35)]
        big = compute_liquidity(neighbors=neighbors, city_population=500_000)
        small = compute_liquidity(neighbors=neighbors, city_population=10_000)
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
