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
        # ``property_type`` é necessário para que ``effective_renovation_area_m2``
        # saiba qual área usar (built vs total). Default = apartamento.
        "property_type": "apartamento",
        "area_total_m2": 60,
        "area_built_m2": 60,
        "occupancy_status": "desocupado",
        "has_liens_or_debts": False,
        "auctioneer_fee_pct": None,
        "auctioneer_name": None,
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


def test_run_analysis_exposes_expected_metrics_and_prob_loss() -> None:
    """E[ROI] ponderado 30/40/30 deve cair entre pessimista e otimista; prob_loss
    é a soma das probabilidades dos cenários com lucro negativo."""
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(),
    )
    assert result.expected_net_roi_pct is not None
    assert result.expected_annualized_net_roi_pct is not None
    assert result.prob_loss is not None
    # E[ROI] tem que ficar entre o pior e o melhor cenário.
    assert (
        result.pessimista.net_roi_pct
        <= result.expected_net_roi_pct
        <= result.otimista.net_roi_pct
    )
    # E[annualized] coincide com E[net] quando holding_months=12 (default).
    assert result.expected_annualized_net_roi_pct == pytest.approx(
        result.expected_net_roi_pct, abs=1e-6
    )
    # Como o realista é positivo neste cenário, prob_loss ≤ 0,30 (peso pess).
    assert 0.0 <= result.prob_loss <= 0.30


def test_run_analysis_prob_loss_caps_at_one_when_all_negative() -> None:
    """Lance proibitivamente alto → todos os cenários com prejuízo → prob_loss = 1."""
    inp = AnalysisInput(
        bid_amount=1_000_000,
        target_net_roi_pct=0.40,
        renovation_level="full",
    )
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(price_low=300_000, mid=350_000, high=400_000),
    )
    assert result.prob_loss == pytest.approx(1.0)
    assert result.expected_net_roi_pct is not None
    assert result.expected_net_roi_pct < 0


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
    """Reforma usa a área CONSTRUÍDA (não a total). Dobrando a built area,
    o custo de reforma deve dobrar."""
    inp = AnalysisInput(bid_amount=200_000, renovation_level="full")
    r60 = run_analysis(
        inp=inp,
        property_row=_property_row(area_built_m2=60),
        valuation=_valuation(),
    )
    r120 = run_analysis(
        inp=inp,
        property_row=_property_row(area_built_m2=120),
        valuation=_valuation(),
    )
    assert r120.realista.renovation_cost > r60.realista.renovation_cost
    # Custo escala linearmente com a área construída.
    assert r120.realista.renovation_cost == pytest.approx(
        r60.realista.renovation_cost * 2
    )


def test_run_analysis_renovation_uses_built_not_total_for_house() -> None:
    """Bug regressão: para casas, ``area_total_m2`` é o TERRENO. Reforma
    NÃO pode escalar com terreno — só com área construída."""
    inp = AnalysisInput(bid_amount=200_000, renovation_level="full")
    result = run_analysis(
        inp=inp,
        property_row=_property_row(
            property_type="casa",
            area_built_m2=148.0,
            area_total_m2=253.0,  # terreno
        ),
        valuation=_valuation(),
    )
    # 148 m² × R$ 1.500 (full) = R$ 222.000.
    # Se estivesse usando o terreno (253 × 1500 = 379.500), seria > 300k.
    assert result.realista.renovation_cost == pytest.approx(148.0 * 1500.0)


def test_run_analysis_terreno_has_zero_renovation_cost() -> None:
    """Terreno NÃO se reforma — independentemente do nível escolhido,
    custo é 0."""
    inp = AnalysisInput(bid_amount=200_000, renovation_level="full")
    result = run_analysis(
        inp=inp,
        property_row=_property_row(
            property_type="terreno",
            area_built_m2=0,
            area_total_m2=500.0,
        ),
        valuation=_valuation(),
    )
    assert result.realista.renovation_cost == 0.0


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


def test_run_analysis_explicit_zero_in_input_is_preserved() -> None:
    """Regressão do bug "outros custos = 0 vira 8000 default": quando o
    usuário declara EXPLICITAMENTE ``0`` em IPTU/condo/outros, o cálculo
    deve respeitar o ``0`` e não substituir pelo valor da property nem
    pelo default por ocupação."""
    inp = AnalysisInput(
        bid_amount=200_000,
        iptu_arrears=0,
        condo_arrears=0,
        other_costs=0,
    )
    result = run_analysis(
        inp=inp,
        # Property row preenchida com valores não-zero — antes do fix esses
        # iam "vazar" pro cenário porque ``or`` descartava o ``0``.
        property_row=_property_row(
            iptu_arrears=2_500,
            condo_arrears=4_000,
            occupancy_status="ocupado",  # default seria 15.000
        ),
        valuation=_valuation(),
    )
    assert result.realista.iptu_arrears == 0
    assert result.realista.condo_arrears == 0
    assert result.realista.other_costs == 0


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
    """Cidade fora da tabela ITBI → ``default``; com leiloeiro nominal e sem
    declaração no edital → ``default`` (5%)."""
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(
            city="CidadeInventada",
            state="XX",
            auctioneer_id="zuk-leilao-uuid",
        ),
        valuation=_valuation(),
    )
    assert result.assumptions.itbi_source == "default"
    assert result.assumptions.auctioneer_fee_source == "default"


# =============================================================================
# Comissão do leiloeiro: presença/ausência de leiloeiro nominal
# =============================================================================
def test_run_analysis_no_auctioneer_yields_zero_fee() -> None:
    """Regra: lote SEM leiloeiro nominal (típico em ``venda-imoveis.caixa.gov.br``
    sem leiloeiro designado) → comissão 0%, ``source == 'no_auctioneer'`` e
    NENHUM warning sobre default 5%."""
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(),
        valuation=_valuation(),
    )
    assert result.realista.auctioneer_fee == 0.0
    assert result.assumptions.auctioneer_fee_source == "no_auctioneer"
    assert result.assumptions.auctioneer_fee_pct == 0.0
    assert not any(
        "comissão do leiloeiro (5%)" in w.lower() for w in result.warnings
    )


def test_run_analysis_with_auctioneer_uses_5pct_default() -> None:
    """Lote COM leiloeiro nominal e sem fee declarado → comissão 5% (default
    histórico do mercado), ``source == 'default'``."""
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(auctioneer_id="zuk-leilao-uuid"),
        valuation=_valuation(),
    )
    assert result.realista.auctioneer_fee == pytest.approx(200_000 * 0.05)
    assert result.assumptions.auctioneer_fee_source == "default"


def test_run_analysis_caixa_lot_with_leiloeiro_name_charges_commission() -> None:
    """Lote Caixa SEM ``auctioneer_id`` (portais próprios não nos cobrem)
    mas COM ``auctioneer_name`` extraído do edital ("Leiloeiro(a): FULANO")
    → 5% (regra do mercado: nome do leiloeiro presente significa comissão)."""
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(
            auctioneer_id=None,
            auctioneer_name="ANDERSON LOPES DE PAULA",
        ),
        valuation=_valuation(),
    )
    assert result.realista.auctioneer_fee == pytest.approx(200_000 * 0.05)
    assert result.assumptions.auctioneer_fee_source == "default"


def test_run_analysis_caixa_lot_with_blank_auctioneer_name_is_treated_as_no_auctioneer() -> None:
    """``auctioneer_name`` em branco (string vazia, só whitespace) NÃO
    deve ser tratado como leiloeiro presente."""
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(
            auctioneer_id=None,
            auctioneer_name="   ",
        ),
        valuation=_valuation(),
    )
    assert result.realista.auctioneer_fee == 0.0
    assert result.assumptions.auctioneer_fee_source == "no_auctioneer"


def test_run_analysis_declared_zero_fee_is_respected_even_without_auctioneer() -> None:
    """Edital com 0% explícito tem prioridade sobre tudo — inclusive sobre
    a heurística de ``no_auctioneer``."""
    inp = AnalysisInput(bid_amount=200_000)
    result = run_analysis(
        inp=inp,
        property_row=_property_row(auctioneer_fee_pct=0.0),
        valuation=_valuation(),
    )
    assert result.realista.auctioneer_fee == 0.0
    assert result.assumptions.auctioneer_fee_source == "edital"
