"""Testes da heurística de parecer e warnings."""

from __future__ import annotations

from app.agents.opportunity.verdict import (
    build_warnings,
    classify_verdict,
    has_critical_warnings,
)


# =============================================================================
# classify_verdict
# =============================================================================
def test_classify_great_when_high_roi() -> None:
    d = classify_verdict(
        realista_net_roi_pct=0.50,
        pessimista_net_profit=10_000,
        has_critical_warnings=False,
    )
    assert d.verdict == "BOA_OPORTUNIDADE"
    assert d.base_verdict == "BOA_OPORTUNIDADE"
    assert d.factors == []


def test_classify_neutral_when_low_roi() -> None:
    d = classify_verdict(
        realista_net_roi_pct=0.10,
        pessimista_net_profit=1_000,
        has_critical_warnings=False,
    )
    assert d.verdict == "NEUTRO"


def test_classify_inviable_when_loss() -> None:
    d = classify_verdict(
        realista_net_roi_pct=0.01,
        pessimista_net_profit=-10_000,
        has_critical_warnings=False,
    )
    assert d.verdict == "INVIAVEL"


def test_pessimista_loss_downgrades_verdict() -> None:
    """Pessimista no vermelho rebaixa em 1 nível."""
    d = classify_verdict(
        realista_net_roi_pct=0.50,
        pessimista_net_profit=-5_000,
        has_critical_warnings=False,
    )
    assert d.verdict == "BOA_COM_RESSALVAS"
    assert d.base_verdict == "BOA_OPORTUNIDADE"
    assert any("pessimista" in f.lower() for f in d.factors)


def test_critical_warnings_downgrade() -> None:
    d = classify_verdict(
        realista_net_roi_pct=0.50,
        pessimista_net_profit=10_000,
        has_critical_warnings=True,
    )
    assert d.verdict == "BOA_COM_RESSALVAS"
    assert any("crítico" in f.lower() for f in d.factors)


# =============================================================================
# Floor por ROI — a regra que evita "ROI 50% mas verdict NEUTRO"
# =============================================================================
def test_high_roi_never_falls_below_boa_com_ressalvas() -> None:
    """Mesmo com pessimista negativo + warnings críticos, ROI ≥40% não cai
    abaixo de BOA_COM_RESSALVAS."""
    d = classify_verdict(
        realista_net_roi_pct=0.50,
        pessimista_net_profit=-10_000,
        has_critical_warnings=True,
    )
    assert d.verdict == "BOA_COM_RESSALVAS"
    # Mas o usuário PRECISA enxergar os 2 fatores na lista — transparência.
    assert len(d.factors) == 2


def test_medium_roi_floor_is_neutral() -> None:
    """ROI 25% (BOA_COM_RESSALVAS base) com 2 downgrades não vira INVIAVEL —
    o piso é NEUTRO."""
    d = classify_verdict(
        realista_net_roi_pct=0.25,
        pessimista_net_profit=-10_000,
        has_critical_warnings=True,
    )
    assert d.verdict == "NEUTRO"
    assert len(d.factors) == 2


def test_low_roi_can_still_become_inviable() -> None:
    """ROI baixo + downgrades pode chegar em INVIAVEL — sem piso protetor."""
    d = classify_verdict(
        realista_net_roi_pct=0.06,
        pessimista_net_profit=-10_000,
        has_critical_warnings=True,
    )
    assert d.verdict == "INVIAVEL"


# =============================================================================
# build_warnings
# =============================================================================
def test_build_warnings_for_occupied_property() -> None:
    ws = build_warnings(
        occupancy_status="ocupado",
        has_liens_or_debts=False,
        valuation_confidence="HIGH",
        n_comparables=10,
        buyer_type="PF",
        pessimista_net_profit=1_000,
        auctioneer_fee_source="edital",
        itbi_source="city_table",
    )
    assert any("ocupado" in w.lower() for w in ws)


def test_build_warnings_for_pj_estimativa() -> None:
    ws = build_warnings(
        occupancy_status="desocupado",
        has_liens_or_debts=False,
        valuation_confidence="HIGH",
        n_comparables=10,
        buyer_type="PJ",
        pessimista_net_profit=1_000,
        auctioneer_fee_source="edital",
        itbi_source="city_table",
    )
    assert any("estimativa" in w.lower() for w in ws)


def test_build_warnings_for_low_confidence_valuation() -> None:
    ws = build_warnings(
        occupancy_status="desocupado",
        has_liens_or_debts=False,
        valuation_confidence="LOW",
        n_comparables=2,
        buyer_type="PF",
        pessimista_net_profit=1_000,
        auctioneer_fee_source="edital",
        itbi_source="city_table",
    )
    assert any("confiança baixa" in w.lower() for w in ws)
    assert any("comparáveis" in w.lower() for w in ws)


def test_build_warnings_for_default_assumptions() -> None:
    ws = build_warnings(
        occupancy_status="desocupado",
        has_liens_or_debts=False,
        valuation_confidence="HIGH",
        n_comparables=10,
        buyer_type="PF",
        pessimista_net_profit=1_000,
        auctioneer_fee_source="default",
        itbi_source="default",
    )
    assert any("leiloeiro" in w.lower() for w in ws)
    assert any("itbi" in w.lower() for w in ws)


# =============================================================================
# has_critical_warnings
# =============================================================================
def test_has_critical_warnings_detects_low_confidence() -> None:
    assert has_critical_warnings(
        ["Avaliação de mercado com confiança baixa — refazer CMA antes de decidir."]
    )


def test_has_critical_warnings_negative() -> None:
    assert not has_critical_warnings(
        ["Imóvel desocupado: aproveite!"]
    )
