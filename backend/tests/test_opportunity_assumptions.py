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
    """``declared_pct`` do edital tem prioridade absoluta — não importa se
    há leiloeiro ou se é Caixa."""
    assert (
        A.auctioneer_fee_pct_for(
            declared_pct=0.04,
            has_auctioneer=True,
            auctioneer_slug=None,
        )
        == 0.04
    )


def test_auctioneer_fee_declared_zero_is_respected() -> None:
    """Se o edital diz 0% explicitamente, devolvemos 0 — não 5% default."""
    assert (
        A.auctioneer_fee_pct_for(
            declared_pct=0.0,
            has_auctioneer=True,
            auctioneer_slug="zuk",
        )
        == 0.0
    )


def test_auctioneer_fee_zero_when_no_auctioneer_present() -> None:
    """Regra principal: imóvel SEM leiloeiro nominal (ex.: venda direta
    Caixa sem leiloeiro designado) → 0% de comissão."""
    assert (
        A.auctioneer_fee_pct_for(
            declared_pct=None,
            has_auctioneer=False,
        )
        == 0.0
    )
    assert A.AUCTIONEER_FEE_PCT_NO_AUCTIONEER == 0.0


def test_auctioneer_fee_zero_for_caixa_slug() -> None:
    """Caixa via slug (ainda quando ``has_auctioneer=True``) é 0%."""
    assert (
        A.auctioneer_fee_pct_for(
            declared_pct=None,
            has_auctioneer=True,
            auctioneer_slug="caixa",
        )
        == 0.0
    )
    assert (
        A.auctioneer_fee_pct_for(
            declared_pct=None,
            has_auctioneer=True,
            auctioneer_slug="caixa-leiloes",
        )
        == 0.0
    )


def test_auctioneer_fee_default_for_known_auctioneer_without_declaration() -> None:
    """Leiloeiro tradicional (Zuk/Mega/etc.) sem declaração → 5% default."""
    assert (
        A.auctioneer_fee_pct_for(
            declared_pct=None,
            has_auctioneer=True,
            auctioneer_slug="zuk",
        )
        == A.AUCTIONEER_FEE_PCT_DEFAULT
    )


def test_auctioneer_fee_declared_beats_caixa_and_no_auctioneer() -> None:
    """Edital tem prioridade absoluta sobre tudo: ``has_auctioneer``,
    ``slug``, e até comportamento default."""
    assert (
        A.auctioneer_fee_pct_for(
            declared_pct=0.05,
            has_auctioneer=False,  # mesmo sem leiloeiro, edital manda
        )
        == 0.05
    )
    assert (
        A.auctioneer_fee_pct_for(
            declared_pct=0.05,
            has_auctioneer=True,
            auctioneer_slug="caixa",  # sluct caixa NÃO sobrepõe edital
        )
        == 0.05
    )


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
