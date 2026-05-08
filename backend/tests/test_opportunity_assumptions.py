"""Testes do módulo de assumptions do AGENTE 3."""

from __future__ import annotations

import pytest

from app.agents.opportunity import assumptions as A


# =============================================================================
# itbi_pct_for
# =============================================================================
def test_itbi_known_city_returns_table_value() -> None:
    pct, exact = A.itbi_pct_for("São Paulo", "SP")
    assert pct == 0.03
    assert exact is True


def test_itbi_handles_accents_and_case() -> None:
    pct1, _ = A.itbi_pct_for("são paulo", "SP")
    pct2, _ = A.itbi_pct_for("SAO PAULO", "SP")
    pct3, _ = A.itbi_pct_for("São Paulo", "sp")
    assert pct1 == pct2 == pct3 == 0.03


def test_itbi_unknown_city_falls_back_to_default() -> None:
    pct, exact = A.itbi_pct_for("CidadeInventada", "XX")
    assert pct == A.ITBI_DEFAULT
    assert exact is False


def test_itbi_no_state_uses_default() -> None:
    pct, exact = A.itbi_pct_for("São Paulo", None)
    assert pct == A.ITBI_DEFAULT
    assert exact is False


# =============================================================================
# auctioneer_fee_pct_for
# =============================================================================
def test_auctioneer_fee_uses_declared_when_available() -> None:
    assert A.auctioneer_fee_pct_for(declared_pct=0.04, auctioneer_slug=None) == 0.04


def test_auctioneer_fee_zero_for_caixa() -> None:
    assert A.auctioneer_fee_pct_for(declared_pct=None, auctioneer_slug="caixa") == 0.0
    assert (
        A.auctioneer_fee_pct_for(declared_pct=None, auctioneer_slug="caixa-leiloes")
        == 0.0
    )


def test_auctioneer_fee_default_for_unknown_slug() -> None:
    assert (
        A.auctioneer_fee_pct_for(declared_pct=None, auctioneer_slug="zukerman")
        == A.AUCTIONEER_FEE_PCT_DEFAULT
    )


def test_auctioneer_fee_declared_beats_caixa() -> None:
    """Se o edital declarou explicitamente, esse valor manda mesmo se for Caixa."""
    assert A.auctioneer_fee_pct_for(declared_pct=0.05, auctioneer_slug="caixa") == 0.05


# =============================================================================
# renovation_cost_for
# =============================================================================
def test_renovation_cost_zero_for_no_area() -> None:
    assert A.renovation_cost_for("moderate", None) == 0.0
    assert A.renovation_cost_for("moderate", 0) == 0.0


def test_renovation_cost_scales_with_area() -> None:
    assert A.renovation_cost_for("basic", 50) == pytest.approx(50 * 500)
    assert A.renovation_cost_for("premium", 100) == pytest.approx(100 * 2_500)


# =============================================================================
# other_costs_default_for
# =============================================================================
def test_other_costs_for_occupancy_levels() -> None:
    assert A.other_costs_default_for("desocupado") < A.other_costs_default_for(
        "ocupado"
    )
    assert (
        A.other_costs_default_for(None)
        == A.OTHER_COSTS_DEFAULT["unknown"]
    )
