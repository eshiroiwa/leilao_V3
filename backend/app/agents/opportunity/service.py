"""Orquestrador do AGENTE 3.

Responsabilidades:

1. **Carregar contexto**: property + última valuation (CMA) do Supabase.
2. **Resolver premissas**: ITBI por cidade, comissão do leiloeiro
   (declarada / Caixa / default), R$/m² da reforma escolhida.
3. **Calcular 3 cenários**: pessimista (``price_lower_bound``),
   realista (``estimated_price``), otimista (``price_upper_bound``).
4. **Resolver lance máximo** para o ROI alvo do usuário.
5. **Classificar parecer** com warnings.
6. **(Opcional) Persistir** a análise no Supabase.

Para a UI obter previews em tempo real, a função :func:`run_analysis`
roda **sem efeitos colaterais** — quem decide salvar é o endpoint
``POST .../save`` (ver ``api/routes/opportunity.py``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agents.opportunity import assumptions as A
from app.agents.opportunity.pricing_math import (
    MaxBidParams,
    compute_acquisition_costs,
    compute_income_tax,
    compute_profit_and_roi,
    solve_max_bid,
)
from app.agents.opportunity.schemas import (
    AnalysisInput,
    AnalysisResult,
    AssumptionsSnapshot,
    Scenario,
)
from app.agents.opportunity.verdict import (
    build_warnings,
    classify_verdict,
    has_critical_warnings,
)
from app.core.logging import get_logger
from app.services.supabase_service import SupabaseService

logger = get_logger(__name__)


# =============================================================================
# Helpers de extração da valuation
# =============================================================================
def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _scenario_prices_from_valuation(
    valuation: dict[str, Any] | None,
    *,
    property_area_m2: float | None,
) -> tuple[float, float, float] | None:
    """Extrai (pessimista, realista, otimista) da valuation.

    Os nomes das colunas espelham o schema real da tabela ``valuations``
    (ver ``backend/app/db/schema.sql``):

      * ``estimated_price``     – preço alvo (mediana ponderada).
      * ``price_lower_bound``   – limite inferior (p10 do pool de comparáveis).
      * ``price_upper_bound``   – limite superior (p90 do pool de comparáveis).
      * ``ppm2_estimated``      – R$/m² mediano (fallback × área).

    Estratégia de fallback:
      1. ``price_lower_bound`` / ``estimated_price`` / ``price_upper_bound``
         se os três existirem e estiverem em ordem.
      2. ``ppm2_estimated`` × área (±10%), como último recurso intermediário.
      3. ``estimated_price`` × ±10%, se nada mais estiver disponível.
    """
    if not valuation:
        return None

    low = _safe_float(valuation.get("price_lower_bound"))
    mid = _safe_float(valuation.get("estimated_price"))
    high = _safe_float(valuation.get("price_upper_bound"))
    if low and mid and high and low <= mid <= high:
        return low, mid, high

    if property_area_m2 and property_area_m2 > 0:
        ppm = _safe_float(valuation.get("ppm2_estimated"))
        if ppm:
            mid_v = ppm * property_area_m2
            return mid_v * 0.9, mid_v, mid_v * 1.1

    if mid:
        return mid * 0.9, mid, mid * 1.1

    return None


# =============================================================================
# Coração do cálculo (ESPELHADO no frontend `lib/opportunity-math.ts`)
# =============================================================================
def _build_scenario(
    *,
    label: str,
    sale_price: float,
    bid: float,
    auctioneer_fee_pct: float,
    itbi_pct: float,
    registration_pct: float,
    iptu_arrears: float,
    condo_arrears: float,
    renovation_cost: float,
    other_costs: float,
    realtor_fee_pct: float,
    buyer_type: str,
    pf_brackets: tuple[tuple[float, float], ...],
    pj_rate: float,
    holding_months: int = 12,
    monthly_iptu: float = 0.0,
    monthly_condo: float = 0.0,
) -> Scenario:
    costs = compute_acquisition_costs(
        bid=bid,
        auctioneer_fee_pct=auctioneer_fee_pct,
        itbi_pct=itbi_pct,
        registration_pct=registration_pct,
        iptu_arrears=iptu_arrears,
        condo_arrears=condo_arrears,
        renovation_cost=renovation_cost,
        other_costs=other_costs,
        monthly_iptu=monthly_iptu,
        monthly_condo=monthly_condo,
        holding_months=holding_months,
    )

    realtor_fee = sale_price * realtor_fee_pct
    gp_pre_tax = sale_price - costs.total - realtor_fee
    income_tax = compute_income_tax(
        buyer_type=buyer_type,
        sale_price=sale_price,
        gross_profit=gp_pre_tax,
        pf_brackets=pf_brackets,
        pj_rate=pj_rate,
    )
    pb = compute_profit_and_roi(
        sale_price=sale_price,
        acquisition_cost_total=costs.total,
        realtor_fee_pct=realtor_fee_pct,
        income_tax=income_tax,
        holding_months=holding_months,
    )

    return Scenario(
        label=label,  # type: ignore[arg-type]
        sale_price=round(sale_price, 2),
        bid=round(costs.bid, 2),
        auctioneer_fee=round(costs.auctioneer_fee, 2),
        itbi=round(costs.itbi, 2),
        registration=round(costs.registration, 2),
        iptu_arrears=round(costs.iptu_arrears, 2),
        condo_arrears=round(costs.condo_arrears, 2),
        renovation_cost=round(costs.renovation_cost, 2),
        other_costs=round(costs.other_costs, 2),
        holding_costs=round(costs.holding_costs, 2),
        total_acquisition_cost=round(costs.total, 2),
        realtor_fee=round(pb.realtor_fee, 2),
        gross_profit=round(pb.gross_profit, 2),
        income_tax=round(pb.income_tax, 2),
        net_profit=round(pb.net_profit, 2),
        gross_roi_pct=round(pb.gross_roi_pct, 6),
        net_roi_pct=round(pb.net_roi_pct, 6),
        annualized_net_roi_pct=round(pb.annualized_net_roi_pct, 6),
    )


# =============================================================================
# API pública: run_analysis (sem persistir) e analyse_and_save
# =============================================================================
def run_analysis(
    *,
    inp: AnalysisInput,
    property_row: dict[str, Any],
    valuation: dict[str, Any] | None,
    auctioneer_slug: str | None = None,
) -> AnalysisResult:
    """Roda os 3 cenários + lance máximo + parecer SEM tocar no banco.

    O service.py é chamado em dois momentos:
      * preview client-side falhou / não disponível → endpoint stateless;
      * para persistir → `analyse_and_save`.
    """
    # --- 1. Extrai dados do property ----------------------------------
    city = property_row.get("city")
    state = property_row.get("state")
    occupancy = property_row.get("occupancy_status")
    declared_fee = _safe_float(property_row.get("auctioneer_fee_pct"))
    # Regra de negócio (cobrança de comissão de leiloeiro):
    #
    #   1. ``auctioneer_id`` populado = portal próprio do leiloeiro
    #      (Zuk, Mega Leilões, Biasi, Sodré-Santoro). SEMPRE há comissão.
    #   2. ``auctioneer_name`` populado = leiloeiro pessoa-física assina
    #      o edital (caso típico em lotes Caixa: "Leiloeiro(a): FULANO").
    #      Há comissão.
    #   3. ``auctioneer_slug`` (passado pelo caller, ex.: dry-run) é só
    #      um atalho para resolver pelo slug sem buscar o id.
    #   4. Nada disso = venda direta sem intermediário (lotes Caixa em
    #      "Compra Direta"/"Venda Online"). NÃO há comissão (0%).
    auctioneer_name = (property_row.get("auctioneer_name") or "").strip()
    has_auctioneer = (
        bool(property_row.get("auctioneer_id"))
        or bool((auctioneer_slug or "").strip())
        or bool(auctioneer_name)
    )

    # --- 2. Resolve as alíquotas --------------------------------------
    itbi_pct, itbi_in_table = A.itbi_pct_for(city, state)
    if inp.itbi_pct_override is not None:
        itbi_pct = inp.itbi_pct_override
        itbi_source = "override"
    else:
        itbi_source = "city_table" if itbi_in_table else "default"

    registration_pct = (
        inp.registration_pct_override
        if inp.registration_pct_override is not None
        else A.REGISTRATION_PCT_DEFAULT
    )

    if inp.auctioneer_fee_pct_override is not None:
        auctioneer_fee_pct = inp.auctioneer_fee_pct_override
        auctioneer_fee_source = "override"
    else:
        auctioneer_fee_pct = A.auctioneer_fee_pct_for(
            declared_pct=declared_fee,
            has_auctioneer=has_auctioneer,
            auctioneer_slug=auctioneer_slug,
        )
        # Ordem dos casos importa — espelha a prioridade da função:
        # 1) edital tem precedência absoluta (0% explícito também conta);
        # 2) sem leiloeiro nominal → no_auctioneer (= 0%);
        # 3) leiloeiro Caixa via slug → caixa_zero (= 0%);
        # 4) leiloeiro tradicional sem declaração → default (= 5%).
        if declared_fee is not None and declared_fee >= 0:
            auctioneer_fee_source = "edital"
        elif not has_auctioneer:
            auctioneer_fee_source = "no_auctioneer"
        elif auctioneer_fee_pct == A.AUCTIONEER_FEE_PCT_CAIXA:
            auctioneer_fee_source = "caixa_zero"
        else:
            auctioneer_fee_source = "default"

    # Reforma incide sobre a PARTE CONSTRUÍDA (não sobre terreno). Para
    # apartamentos/casas/sobrados a área correta é ``area_built_m2`` e
    # NÃO ``area_total_m2`` (que em casas é o terreno). Para terrenos o
    # custo de reforma é zero por definição. Ver
    # ``A.effective_renovation_area_m2`` para a política completa.
    renovation_area_m2, _ren_area_source = A.effective_renovation_area_m2(
        property_row
    )
    renovation_cost = A.renovation_cost_for(
        inp.renovation_level, renovation_area_m2
    )

    # Para a PRECIFICAÇÃO ainda usamos a área "de mercado" do imóvel:
    # geralmente igual à da reforma para apartamentos/casas, mas para
    # terreno é a área total (m² de terreno × R$/m² de terreno).
    area_m2 = _safe_float(property_row.get("area_total_m2")) or _safe_float(
        property_row.get("area_built_m2")
    )

    # --- 3. Custos fixos extra ----------------------------------------
    # Os campos ``iptu_arrears``, ``condo_arrears`` e ``other_costs`` chegam
    # SEMPRE preenchidos no ``AnalysisInput`` (default 0 no schema). O frontend
    # já calcula o default sugerido (``otherCostsDefaultFor``) e o envia como
    # valor literal — então aqui só preservamos. Antes usávamos ``or`` para
    # cair em fallbacks, mas isso descartava o ``0`` explícito do usuário e
    # voltava o default (bug reportado: "outros custos = 0 → vira 8000").
    iptu_arrears = float(inp.iptu_arrears)
    condo_arrears = float(inp.condo_arrears)
    other_costs = float(inp.other_costs)

    # --- 4. Cenários (3 preços de venda) ------------------------------
    if inp.sale_price_override is not None and inp.sale_price_override > 0:
        # Usuário forneceu o preço alvo explícito → cenários ±10%.
        real_p = float(inp.sale_price_override)
        pess_p = real_p * 0.9
        oti_p = real_p * 1.1
    else:
        prices = _scenario_prices_from_valuation(
            valuation, property_area_m2=area_m2
        )
        if prices is None:
            # Sem valuation nem override: degrade graciosamente —
            # usa o lance × 1.2 como estimativa, ±10% pra variação.
            bid_for_proxy = inp.bid_amount or 0.0
            proxy = max(bid_for_proxy * 1.2, 1.0)
            prices = (proxy * 0.9, proxy, proxy * 1.1)
        pess_p, real_p, oti_p = prices

    common_kwargs = dict(
        bid=inp.bid_amount,
        auctioneer_fee_pct=auctioneer_fee_pct,
        itbi_pct=itbi_pct,
        registration_pct=registration_pct,
        iptu_arrears=iptu_arrears,
        condo_arrears=condo_arrears,
        renovation_cost=renovation_cost,
        other_costs=other_costs,
        realtor_fee_pct=A.REALTOR_FEE_PCT,
        buyer_type=inp.buyer_type,
        pf_brackets=A.IR_PF_BRACKETS,
        pj_rate=A.IR_PJ_PCT,
        holding_months=inp.holding_months,
        monthly_iptu=float(inp.monthly_iptu),
        monthly_condo=float(inp.monthly_condo),
    )

    pessimista = _build_scenario(label="pessimista", sale_price=pess_p, **common_kwargs)
    realista = _build_scenario(label="realista", sale_price=real_p, **common_kwargs)
    otimista = _build_scenario(label="otimista", sale_price=oti_p, **common_kwargs)

    # --- 5. Lance máximo (sobre cenário REALISTA) ---------------------
    holding_costs = float(inp.holding_months) * (
        float(inp.monthly_iptu) + float(inp.monthly_condo)
    )
    max_bid = solve_max_bid(
        MaxBidParams(
            sale_price=real_p,
            iptu_arrears=iptu_arrears,
            condo_arrears=condo_arrears,
            renovation_cost=renovation_cost,
            other_costs=other_costs,
            auctioneer_fee_pct=auctioneer_fee_pct,
            itbi_pct=itbi_pct,
            registration_pct=registration_pct,
            realtor_fee_pct=A.REALTOR_FEE_PCT,
            buyer_type=inp.buyer_type,
            pf_brackets=A.IR_PF_BRACKETS,
            pj_rate=A.IR_PJ_PCT,
            target_net_roi=inp.target_net_roi_pct,
            holding_costs=holding_costs,
        )
    )
    if max_bid is not None:
        max_bid = round(max_bid, 2)

    # --- 6. Warnings + parecer ---------------------------------------
    warnings = build_warnings(
        occupancy_status=occupancy,
        has_liens_or_debts=bool(property_row.get("has_liens_or_debts")),
        valuation_confidence=(valuation or {}).get("confidence"),
        n_comparables=(valuation or {}).get("comparables_used"),
        buyer_type=inp.buyer_type,
        pessimista_net_profit=pessimista.net_profit,
        auctioneer_fee_source=auctioneer_fee_source,
        itbi_source=itbi_source,
        renovation_level=inp.renovation_level,
        renovation_cost=renovation_cost,
        renovation_area_source=_ren_area_source,
    )

    decision = classify_verdict(
        roi_for_verdict_pct=realista.annualized_net_roi_pct,
        pessimista_net_profit=pessimista.net_profit,
        has_critical_warnings=has_critical_warnings(warnings),
    )

    # --- 7. Snapshot das premissas ------------------------------------
    snap = AssumptionsSnapshot(
        itbi_pct=itbi_pct,
        itbi_source=itbi_source,  # type: ignore[arg-type]
        registration_pct=registration_pct,
        auctioneer_fee_pct=auctioneer_fee_pct,
        auctioneer_fee_source=auctioneer_fee_source,  # type: ignore[arg-type]
        realtor_fee_pct=A.REALTOR_FEE_PCT,
        income_tax_pct=A.IR_PJ_PCT if inp.buyer_type == "PJ" else A.IR_PF_PCT,
        income_tax_basis="sale_price" if inp.buyer_type == "PJ" else "gross_profit",
        renovation_per_m2=A.RENOVATION_PER_M2[inp.renovation_level],
    )

    # --- 8. Métricas probabilísticas (combinação ponderada dos cenários) ---
    p_pess = A.SCENARIO_PROB_PESSIMISTA
    p_real = A.SCENARIO_PROB_REALISTA
    p_oti = A.SCENARIO_PROB_OTIMISTA
    expected_net_roi = (
        p_pess * pessimista.net_roi_pct
        + p_real * realista.net_roi_pct
        + p_oti * otimista.net_roi_pct
    )
    expected_annualized = (
        p_pess * pessimista.annualized_net_roi_pct
        + p_real * realista.annualized_net_roi_pct
        + p_oti * otimista.annualized_net_roi_pct
    )
    prob_loss = sum(
        p
        for p, sc in (
            (p_pess, pessimista),
            (p_real, realista),
            (p_oti, otimista),
        )
        if sc.net_profit < 0
    )

    return AnalysisResult(
        input=inp,
        pessimista=pessimista,
        realista=realista,
        otimista=otimista,
        expected_net_roi_pct=round(expected_net_roi, 6),
        expected_annualized_net_roi_pct=round(expected_annualized, 6),
        prob_loss=round(prob_loss, 4),
        max_bid_for_target=max_bid,
        verdict=decision.verdict,
        verdict_base=decision.base_verdict,
        verdict_factors=decision.factors,
        warnings=warnings,
        assumptions=snap,
    )


def analyse_and_save(
    *,
    supabase: SupabaseService,
    property_id: str,
    inp: AnalysisInput,
) -> tuple[AnalysisResult, dict[str, Any]]:
    """Orquestração completa: carrega → calcula → persiste.

    Retorna ``(resultado, row_persistida)``. A row contém o ``id`` do
    Supabase que o frontend usa para deep-link.

    O servidor SEMPRE recalcula (mesmo se o frontend mandar um result
    pré-calculado): server-side é fonte de verdade.
    """
    prop = supabase.get_property_by_id(property_id)
    if not prop:
        raise ValueError(f"property_id={property_id} não encontrado")

    valuation = supabase.get_latest_valuation_for_property(property_id)

    auctioneer_slug = None
    auctioneer_id = prop.get("auctioneer_id")
    if auctioneer_id:
        # Não buscamos auctioneer aqui para evitar uma query extra;
        # o slug não-Caixa não muda o resultado. Caso queira o desconto
        # da Caixa via slug, popule property_row.auctioneer_slug.
        auctioneer_slug = prop.get("auctioneer_slug")

    result = run_analysis(
        inp=inp,
        property_row=prop,
        valuation=valuation,
        auctioneer_slug=auctioneer_slug,
    )

    payload = {
        "property_id": property_id,
        "valuation_id": valuation.get("id") if valuation else None,
        "buyer_type": inp.buyer_type,
        "target_net_roi_pct": inp.target_net_roi_pct,
        "renovation_level": inp.renovation_level,
        "bid_amount": inp.bid_amount,
        "other_costs": inp.other_costs,
        "iptu_arrears": inp.iptu_arrears,
        "condo_arrears": inp.condo_arrears,
        "scenarios": {
            "pessimista": result.pessimista.model_dump(),
            "realista": result.realista.model_dump(),
            "otimista": result.otimista.model_dump(),
        },
        "max_bid_for_target": result.max_bid_for_target,
        "verdict": result.verdict,
        "warnings": result.warnings,
        "assumptions": result.assumptions.model_dump(),
        # Overrides do formulário — necessários para reproduzir a análise
        # no frontend (clicar num item antigo do histórico).
        "input_overrides": {
            "itbi_pct_override": inp.itbi_pct_override,
            "registration_pct_override": inp.registration_pct_override,
            "auctioneer_fee_pct_override": inp.auctioneer_fee_pct_override,
            "sale_price_override": inp.sale_price_override,
        },
    }

    row = supabase.insert_opportunity_analysis(payload)
    logger.info(
        "opportunity.persisted",
        analysis_id=row.get("id"),
        property_id=property_id,
        verdict=result.verdict,
        max_bid=result.max_bid_for_target,
        elapsed_at=datetime.now(timezone.utc).isoformat(),
    )
    return result, row
