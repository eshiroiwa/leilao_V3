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


def test_pessimista_loss_downgrades_verdict_at_great_roi() -> None:
    """Pessimista no vermelho rebaixa em 1 nível DENTRO da faixa GREAT (40–50%).

    ROI 45% é "BOA_OPORTUNIDADE" base, mas o piso para essa faixa é
    "BOA_COM_RESSALVAS" — então o pessimista deficitário rebaixa.
    """
    d = classify_verdict(
        realista_net_roi_pct=0.45,
        pessimista_net_profit=-5_000,
        has_critical_warnings=False,
    )
    assert d.verdict == "BOA_COM_RESSALVAS"
    assert d.base_verdict == "BOA_OPORTUNIDADE"
    assert any("pessimista" in f.lower() for f in d.factors)


def test_critical_warnings_downgrade_at_great_roi() -> None:
    d = classify_verdict(
        realista_net_roi_pct=0.45,
        pessimista_net_profit=10_000,
        has_critical_warnings=True,
    )
    assert d.verdict == "BOA_COM_RESSALVAS"
    assert any("financeiro" in f.lower() or "crítico" in f.lower() for f in d.factors)


# =============================================================================
# Floor por ROI
# =============================================================================
def test_excellent_roi_is_intocable() -> None:
    """ROI ≥ 50% mantém BOA_OPORTUNIDADE mesmo com pessimista negativo +
    warnings críticos — retorno tão alto compensa as fricções."""
    d = classify_verdict(
        realista_net_roi_pct=0.55,
        pessimista_net_profit=-10_000,
        has_critical_warnings=True,
    )
    assert d.verdict == "BOA_OPORTUNIDADE"
    # Os fatores ainda aparecem na lista — só não rebaixam.
    assert len(d.factors) == 2


def test_excellent_roi_above_100_pct_stays_great() -> None:
    """Sanity: ROI 120% NUNCA pode virar BOA_COM_RESSALVAS por causa de warnings."""
    d = classify_verdict(
        realista_net_roi_pct=1.20,
        pessimista_net_profit=-50_000,
        has_critical_warnings=True,
    )
    assert d.verdict == "BOA_OPORTUNIDADE"


def test_great_roi_floor_is_boa_com_ressalvas() -> None:
    """ROI 40–50% pode cair até BOA_COM_RESSALVAS, mas não abaixo."""
    d = classify_verdict(
        realista_net_roi_pct=0.45,
        pessimista_net_profit=-10_000,
        has_critical_warnings=True,
    )
    assert d.verdict == "BOA_COM_RESSALVAS"
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


def test_has_critical_warnings_detects_liens() -> None:
    assert has_critical_warnings(
        ["Edital indica ônus/dívidas: confirme se serão sub-rogados no preço."]
    )


def test_occupied_property_is_NOT_critical() -> None:
    """Imóvel ocupado é o normal em leilões — não deve rebaixar o verdict."""
    occupied_warning = build_warnings(
        occupancy_status="ocupado",
        has_liens_or_debts=False,
        valuation_confidence="HIGH",
        n_comparables=10,
        buyer_type="PF",
        pessimista_net_profit=10_000,
        auctioneer_fee_source="edital",
        itbi_source="city_table",
    )
    # Existe um warning informativo na lista...
    assert any("ocupado" in w.lower() for w in occupied_warning)
    # ... mas ele NÃO é crítico.
    assert not has_critical_warnings(occupied_warning)


def test_occupied_alone_does_not_downgrade_great_roi() -> None:
    """ROI 50% + imóvel ocupado (sem outros riscos) → mantém BOA_OPORTUNIDADE."""
    occupied_warnings = build_warnings(
        occupancy_status="ocupado",
        has_liens_or_debts=False,
        valuation_confidence="HIGH",
        n_comparables=10,
        buyer_type="PF",
        pessimista_net_profit=10_000,
        auctioneer_fee_source="edital",
        itbi_source="city_table",
    )
    d = classify_verdict(
        realista_net_roi_pct=0.50,
        pessimista_net_profit=10_000,
        has_critical_warnings=has_critical_warnings(occupied_warnings),
    )
    assert d.verdict == "BOA_OPORTUNIDADE"
    assert d.factors == []


def test_has_critical_warnings_negative() -> None:
    assert not has_critical_warnings(
        ["Imóvel desocupado: aproveite!"]
    )
