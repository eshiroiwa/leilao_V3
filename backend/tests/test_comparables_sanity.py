"""Testes da função pura compare_with_fipezap (sanity check da CMA)."""

from __future__ import annotations

import pytest

from app.agents.comparables.pricing import Valuation
from app.agents.comparables.sanity import (
    DIVERGENCE_THRESHOLD,
    compare_with_fipezap,
)


def _valuation(ppm2: float | None = 10_000.0, confidence: str = "HIGH") -> Valuation:
    return Valuation(
        estimated_price=(ppm2 * 80.0) if ppm2 else None,
        price_lower_bound=None,
        price_upper_bound=None,
        ppm2_estimated=ppm2,
        confidence=confidence,  # type: ignore[arg-type]
        method="weighted_median_ppm2",
        comparables_used=10,
    )


def _city_row(ppm2: float, year: int = 2026, month: int = 1) -> dict:
    return {
        "city": "São Paulo", "state": "SP",
        "mean_ppm2_brl": ppm2, "asof_year": year, "asof_month": month,
    }


# =============================================================================
# Sem dados → sem mudança
# =============================================================================
def test_no_fipezap_row_returns_valuation_unchanged() -> None:
    v = _valuation(10_000)
    out = compare_with_fipezap(v, None)
    assert out.valuation is v
    assert out.warning is None
    assert out.fipezap_ppm2 is None
    assert out.divergence_pct is None


def test_no_cma_ppm2_returns_valuation_unchanged() -> None:
    """Valuation INSUFFICIENT (ppm2=None) → não há o que comparar."""
    v = _valuation(None, confidence="INSUFFICIENT")
    out = compare_with_fipezap(v, _city_row(8_000))
    assert out.valuation is v
    assert out.warning is None


# =============================================================================
# Dentro do threshold → endossa (não mexe)
# =============================================================================
def test_within_threshold_keeps_confidence_and_no_warning() -> None:
    """Divergência de 20% (< 30%) → valuation inalterada."""
    v = _valuation(10_000, confidence="HIGH")
    out = compare_with_fipezap(v, _city_row(8_000))
    assert out.valuation.confidence == "HIGH"
    assert out.warning is None
    assert out.divergence_pct == pytest.approx(0.25)


def test_zero_divergence_no_warning() -> None:
    v = _valuation(8_000, confidence="MEDIUM")
    out = compare_with_fipezap(v, _city_row(8_000))
    assert out.warning is None
    assert out.divergence_pct == 0.0
    assert out.valuation.confidence == "MEDIUM"


# =============================================================================
# Fora do threshold → endurece + warning
# =============================================================================
def test_above_threshold_downgrades_confidence_one_level() -> None:
    """ppm2 50% acima do FipeZAP → HIGH cai para MEDIUM."""
    v = _valuation(12_000, confidence="HIGH")
    out = compare_with_fipezap(v, _city_row(8_000))
    assert out.valuation.confidence == "MEDIUM"
    assert out.warning is not None
    assert "acima" in out.warning
    assert out.divergence_pct == pytest.approx(0.50)


def test_below_threshold_downgrades_with_below_label() -> None:
    """ppm2 50% abaixo do FipeZAP → MEDIUM cai para LOW; warning diz 'abaixo'."""
    v = _valuation(4_000, confidence="MEDIUM")
    out = compare_with_fipezap(v, _city_row(8_000))
    assert out.valuation.confidence == "LOW"
    assert out.warning is not None
    assert "abaixo" in out.warning


def test_downgrade_stops_at_insufficient() -> None:
    """Não dá pra cair abaixo de INSUFFICIENT."""
    v = _valuation(4_000, confidence="INSUFFICIENT")
    out = compare_with_fipezap(v, _city_row(8_000))
    assert out.valuation.confidence == "INSUFFICIENT"


def test_warning_includes_asof_when_available() -> None:
    v = _valuation(12_000, confidence="HIGH")
    out = compare_with_fipezap(v, _city_row(8_000, year=2026, month=3))
    assert out.warning is not None
    assert "2026-03" in out.warning


def test_threshold_is_configurable() -> None:
    """Threshold mais apertado (10%) faz disparar onde 30% não dispararia."""
    v = _valuation(11_000, confidence="HIGH")  # 37,5% acima de 8.000 → dispara em 30%
    # Com threshold 0.5 (50%), a mesma divergência NÃO dispara.
    out = compare_with_fipezap(v, _city_row(8_000), threshold=0.5)
    assert out.warning is None
    assert out.valuation.confidence == "HIGH"


def test_fipezap_zero_or_missing_is_ignored() -> None:
    """Valor inválido/None do FipeZAP é tratado como ausência de dado."""
    v = _valuation(10_000)
    assert compare_with_fipezap(v, _city_row(0)).warning is None
    assert (
        compare_with_fipezap(v, {"mean_ppm2_brl": None, "asof_year": 2026, "asof_month": 1}).warning
        is None
    )


def test_divergence_threshold_default_is_30_pct() -> None:
    """Sanity: a constante exposta vale 0.30 — usada na regra de negócio."""
    assert DIVERGENCE_THRESHOLD == pytest.approx(0.30)
