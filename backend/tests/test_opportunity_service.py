"""Testes do orquestrador do AGENTE 3 (sem Supabase real)."""

from __future__ import annotations

import pytest

from app.agents.opportunity.schemas import AnalysisInput
from app.agents.opportunity.service import run_analysis


def _property_row(**overrides):
    base = {
        "id": "prop-1",
        "city": "São Paulo",
        "state": "SP",
        "area_total_m2": 60,
        "occupancy_status": "desocupado",
        "has_liens_or_debts": False,
        "auctioneer_fee_pct": None,
        "iptu_arrears": None,
        "condo_arrears": None,
    }
    base.update(overrides)
    return base


def _valuation(price_low=350_000, mid=400_000, high=450_000, **overrides):
    base = {
        "id": "val-1",
        "price_lower_bound": price_low,
        "estimated_price": mid,
        "price_upper_bound": high,
        "confidence": "HIGH",
        "comparables_used": 12,
    }
    base.update(overrides)
    return base


# =============================================================================
# Cenários básicos
# =============================================================================
def test_run_analysis_produces_three_scenarios_with_growing_sale_prices() -> None:
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(),
    )
    assert result.pessimista.sale_price < result.realista.sale_price
    assert result.realista.sale_price < result.otimista.sale_price


def test_run_analysis_max_bid_yields_target_roi_when_recomputed() -> None:
    """Round-trip: recalcular o cenário com `max_bid_for_target` deve dar
    aproximadamente o ROI alvo."""
    inp = AnalysisInput(bid_amount=200_000, target_net_roi_pct=0.40)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(),
    )
    assert result.max_bid_for_target is not None

    # Re-roda com bid = max_bid e compara o ROI realista com o target.
    inp2 = AnalysisInput(
        bid_amount=result.max_bid_for_target,
        target_net_roi_pct=0.40,
    )
    result2 = run_analysis(
        inp=inp2,
        property_row=_property_row(),
        valuation=_valuation(),
    )
    assert abs(result2.realista.net_roi_pct - 0.40) < 1e-3


def test_run_analysis_pj_uses_sale_based_tax() -> None:
    inp_pf = AnalysisInput(bid_amount=200_000, buyer_type="PF")
    inp_pj = AnalysisInput(bid_amount=200_000, buyer_type="PJ")

    pf = run_analysis(inp=inp_pf, property_row=_property_row(), valuation=_valuation())
    pj = run_analysis(inp=inp_pj, property_row=_property_row(), valuation=_valuation())

    # Para o cenário realista PF (lucrativo), PJ paga sobre venda → mais imposto.
    assert pj.realista.income_tax > pf.realista.income_tax
    # Warning de estimativa PJ.
    assert any("estimativa" in w.lower() for w in pj.warnings)


def test_run_analysis_caixa_slug_zeroes_auctioneer_fee() -> None:
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(),
        auctioneer_slug="caixa",
    )
    assert result.realista.auctioneer_fee == 0.0


def test_run_analysis_uses_declared_auctioneer_fee_from_property() -> None:
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(auctioneer_fee_pct=0.04),
        valuation=_valuation(),
    )
    assert result.realista.auctioneer_fee == pytest.approx(200_000 * 0.04)


def test_run_analysis_renovation_scales_with_area() -> None:
    inp = AnalysisInput(bid_amount=200_000, renovation_level="full")
    r60 = run_analysis(
        inp=inp,
        property_row=_property_row(area_total_m2=60),
        valuation=_valuation(),
    )
    r120 = run_analysis(
        inp=inp,
        property_row=_property_row(area_total_m2=120),
        valuation=_valuation(),
    )
    assert r120.realista.renovation_cost > r60.realista.renovation_cost


def test_run_analysis_handles_missing_valuation() -> None:
    """Sem valuation, o serviço usa fallback baseado no lance e marca warnings."""
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=None,
    )
    # Deve produzir cenários sem explodir
    assert result.realista.sale_price > 0


def test_run_analysis_verdict_inviable_for_overpriced_bid() -> None:
    """Lance maior que o teto de mercado → ROI realista negativo → INVIAVEL."""
    inp = AnalysisInput(bid_amount=600_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(price_low=350_000, mid=400_000, high=450_000),
    )
    assert result.realista.net_roi_pct < 0
    assert result.verdict in {"INVIAVEL", "NEUTRO"}


def test_run_analysis_warns_about_low_confidence_valuation() -> None:
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(confidence="LOW", comparables_used=2),
    )
    assert any("confiança baixa" in w.lower() for w in result.warnings)


def test_run_analysis_property_arrears_flow_to_scenario_when_input_zero() -> None:
    """Se inputs IPTU/condo == 0, mas a property tem valor, usa o do banco."""
    inp = AnalysisInput(bid_amount=200_000, iptu_arrears=0, condo_arrears=0)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(iptu_arrears=2_500, condo_arrears=4_000),
        valuation=_valuation(),
    )
    assert result.realista.iptu_arrears == pytest.approx(2_500)
    assert result.realista.condo_arrears == pytest.approx(4_000)


def test_run_analysis_user_input_overrides_property_arrears() -> None:
    """Quando o usuário declara IPTU/condo no input, precede o do banco."""
    inp = AnalysisInput(bid_amount=200_000, iptu_arrears=999, condo_arrears=888)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(iptu_arrears=2_500, condo_arrears=4_000),
        valuation=_valuation(),
    )
    assert result.realista.iptu_arrears == 999
    assert result.realista.condo_arrears == 888


def test_run_analysis_sale_price_override_drives_realista() -> None:
    """Override de venda → realista bate o número, pess/oti = ±10%."""
    inp = AnalysisInput(bid_amount=200_000, sale_price_override=500_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(),  # CMA diz 350/400/450 — deve ser ignorada
    )
    assert result.realista.sale_price == pytest.approx(500_000)
    assert result.pessimista.sale_price == pytest.approx(450_000)
    assert result.otimista.sale_price == pytest.approx(550_000)


def test_run_analysis_sale_price_override_works_without_valuation() -> None:
    """Sem CMA, o override ainda gera 3 cenários consistentes."""
    inp = AnalysisInput(bid_amount=200_000, sale_price_override=500_000)
    result = run_analysis(
        inp=inp, property_row=_property_row(), valuation=None
    )
    assert result.realista.sale_price == pytest.approx(500_000)


def test_run_analysis_pct_overrides_apply() -> None:
    """Overrides de ITBI/registro/leiloeiro entram no cenário e no snapshot."""
    inp = AnalysisInput(
        bid_amount=200_000,
        itbi_pct_override=0.02,
        registration_pct_override=0.01,
        auctioneer_fee_pct_override=0.04,
    )
    result = run_analysis(
        inp=inp, property_row=_property_row(), valuation=_valuation()
    )
    assert result.realista.itbi == pytest.approx(200_000 * 0.02)
    assert result.realista.registration == pytest.approx(200_000 * 0.01)
    assert result.realista.auctioneer_fee == pytest.approx(200_000 * 0.04)
    # Snapshot reflete a fonte como "override".
    assert result.assumptions.itbi_source == "override"
    assert result.assumptions.auctioneer_fee_source == "override"
    assert result.assumptions.registration_pct == pytest.approx(0.01)


def test_run_analysis_assumptions_snapshot_records_sources() -> None:
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(city="CidadeInventada", state="XX"),
        valuation=_valuation(),
    )
    # cidade fora da tabela → itbi_source == "default"
    assert result.assumptions.itbi_source == "default"
    assert result.assumptions.auctioneer_fee_source == "default"
