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
# effective_renovation_area_m2
# =============================================================================
def test_renovation_area_apartment_prefers_built_over_total() -> None:
    """Apartamento: ``area_built_m2`` vence ``area_total_m2`` (matrícula)."""
    area, source = A.effective_renovation_area_m2(
        {
            "property_type": "apartamento",
            "area_built_m2": 65.0,
            "area_total_m2": 75.0,
        }
    )
    assert area == 65.0
    assert source == "area_built_m2"


def test_renovation_area_house_prefers_built_over_total() -> None:
    """Casa: ``area_total_m2`` é o TERRENO — não pode entrar no cálculo
    da reforma. Tem que usar ``area_built_m2``."""
    area, source = A.effective_renovation_area_m2(
        {
            "property_type": "casa",
            "area_built_m2": 148.0,
            "area_total_m2": 253.0,  # terreno
        }
    )
    assert area == 148.0
    assert source == "area_built_m2"


def test_renovation_area_falls_back_to_useful_then_total() -> None:
    """``area_useful_m2`` é o segundo melhor; ``area_total_m2`` é o
    último recurso (apenas pra apartamentos onde costuma ser confiável)."""
    only_useful, src1 = A.effective_renovation_area_m2(
        {"property_type": "apartamento", "area_useful_m2": 80.0}
    )
    assert only_useful == 80.0
    assert src1 == "area_useful_m2"

    only_total, src2 = A.effective_renovation_area_m2(
        {"property_type": "apartamento", "area_total_m2": 90.0}
    )
    assert only_total == 90.0
    assert src2 == "area_total_m2"


def test_renovation_area_terreno_returns_none() -> None:
    """Terreno NÃO se reforma — caller deve aplicar custo 0."""
    area, source = A.effective_renovation_area_m2(
        {"property_type": "terreno", "area_total_m2": 500.0}
    )
    assert area is None
    assert source == "no_construction"

    # Mesmo se vier ``area_built_m2`` populado por engano, ignora.
    area2, _ = A.effective_renovation_area_m2(
        {
            "property_type": "lote",
            "area_built_m2": 50.0,
            "area_total_m2": 500.0,
        }
    )
    assert area2 is None


def test_renovation_cost_zero_for_terreno_via_effective_area() -> None:
    """Pipeline ponta-a-ponta: terreno + nível ``full`` ainda dá 0."""
    area, _ = A.effective_renovation_area_m2(
        {"property_type": "terreno", "area_total_m2": 500.0}
    )
    assert A.renovation_cost_for("full", area) == 0.0


def test_renovation_area_case_insensitive_and_unknown_type() -> None:
    """Tipo é normalizado pra lower; tipo desconhecido cai no
    palpite conservador (não usa ``area_total_m2``)."""
    area, source = A.effective_renovation_area_m2(
        {"property_type": "APARTAMENTO", "area_built_m2": 60.0}
    )
    assert area == 60.0
    assert source == "area_built_m2"

    # Tipo desconhecido com só area_total_m2 → None (mais conservador
    # que arriscar terreno).
    area2, _ = A.effective_renovation_area_m2(
        {"property_type": "outro", "area_total_m2": 500.0}
    )
    assert area2 is None


# =============================================================================
# pf_income_tax_progressive — tabela Lei 13.259/2016
# =============================================================================
def test_pf_progressive_zero_for_loss_or_zero() -> None:
    """Prejuízo (ou GP=0) não paga IR PF."""
    assert A.pf_income_tax_progressive(0) == 0.0
    assert A.pf_income_tax_progressive(-100_000) == 0.0


def test_pf_progressive_first_bracket_15pct() -> None:
    """Ganho dentro da 1ª faixa (até R$5MM) → 15% liso."""
    # Caso típico de leilão judicial: ganho de R$100k → R$15k.
    assert A.pf_income_tax_progressive(100_000) == pytest.approx(15_000)
    # Borda da faixa (R$5MM) → 5MM × 15% = 750k.
    assert A.pf_income_tax_progressive(5_000_000) == pytest.approx(750_000)


def test_pf_progressive_second_bracket_17_5pct_partial() -> None:
    """Ganho de R$6MM → 5MM×15% + 1MM×17,5% = 750k + 175k = 925k.

    NÃO é 6MM × 17,5% (= 1,05M) — esse seria o erro do escalonado.
    A alíquota maior só incide sobre a PARCELA acima do teto anterior.
    """
    assert A.pf_income_tax_progressive(6_000_000) == pytest.approx(925_000)
    # Borda: R$10MM → 750k + 5MM × 17,5% = 750k + 875k = 1.625k.
    assert A.pf_income_tax_progressive(10_000_000) == pytest.approx(1_625_000)


def test_pf_progressive_third_bracket_20pct_partial() -> None:
    """Ganho de R$15MM → 750k + 875k + 5MM × 20% = 1.625k + 1.000k = 2.625k."""
    assert A.pf_income_tax_progressive(15_000_000) == pytest.approx(2_625_000)


def test_pf_progressive_top_bracket_22_5pct() -> None:
    """Ganho de R$40MM → 1.625k + 20MM×20% + 10MM×22,5% = 1.625k+4.000k+2.250k = 7.875k."""
    assert A.pf_income_tax_progressive(40_000_000) == pytest.approx(7_875_000)


def test_pf_progressive_effective_rate_grows_with_gp() -> None:
    """Alíquota efetiva é monotonicamente crescente em GP."""
    rates = [
        A.pf_income_tax_progressive(g) / g
        for g in (1_000_000, 6_000_000, 15_000_000, 40_000_000)
    ]
    assert rates == sorted(rates)
    # Sanidade: nunca passa de 22,5%, nunca cai abaixo de 15%.
    assert 0.15 <= rates[0] <= rates[-1] < 0.225


def test_pf_progressive_custom_brackets() -> None:
    """Função aceita brackets customizados — útil para simulação de cenários
    alternativos (ex.: regime futuro, isenção temporária)."""
    flat_20 = ((float("inf"), 0.20),)
    assert A.pf_income_tax_progressive(1_000_000, brackets=flat_20) == pytest.approx(
        200_000
    )
    # Brackets vazios = imposto 0 (degeneração defensiva).
    assert A.pf_income_tax_progressive(1_000_000, brackets=()) == 0.0


def test_pf_default_bracket_table_matches_law() -> None:
    """A tabela default expõe as 4 faixas da Lei 13.259/2016."""
    assert len(A.IR_PF_BRACKETS) == 4
    assert A.IR_PF_BRACKETS[0] == (5_000_000.0, 0.150)
    assert A.IR_PF_BRACKETS[1] == (10_000_000.0, 0.175)
    assert A.IR_PF_BRACKETS[2] == (30_000_000.0, 0.200)
    assert A.IR_PF_BRACKETS[3] == (float("inf"), 0.225)


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
