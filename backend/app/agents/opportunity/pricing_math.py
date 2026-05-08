"""Núcleo matemático do AGENTE 3 — funções PURAS, sem I/O, sem efeitos.

Tudo aqui é determinístico e fácil de testar. A regra é: cada função recebe
TODOS os parâmetros que precisa (sem ler globals nem env). O service.py é
quem busca tabelas e injeta valores.

Convenção:
    * porcentagens: fração (0.40 = 40%).
    * valores monetários: float em BRL.

Para deixar transparente, mantemos estas variáveis de DOMÍNIO:

    bid                 = lance no leilão (custo principal de aquisição)
    sale_price          = preço de venda esperado
    acquisition_cost    = bid + leiloeiro + ITBI + registro + dívidas + reforma + outros
    selling_cost        = comissão de venda (corretor)
    gross_profit        = sale_price − acquisition_cost − selling_cost
    income_tax          = imposto sobre ganho de capital (PF) ou faturamento (PJ)
    net_profit          = gross_profit − income_tax
    gross_roi           = gross_profit / acquisition_cost
    net_roi             = net_profit   / acquisition_cost
"""

from __future__ import annotations

from dataclasses import dataclass


# =============================================================================
# 1. Custos
# =============================================================================
@dataclass(frozen=True, slots=True)
class AcquisitionCosts:
    """Decomposição do custo de aquisição (tudo que sai do bolso até a posse)."""

    bid: float
    auctioneer_fee: float
    itbi: float
    registration: float
    iptu_arrears: float
    condo_arrears: float
    renovation_cost: float
    other_costs: float

    @property
    def total(self) -> float:
        return (
            self.bid
            + self.auctioneer_fee
            + self.itbi
            + self.registration
            + self.iptu_arrears
            + self.condo_arrears
            + self.renovation_cost
            + self.other_costs
        )


def compute_acquisition_costs(
    *,
    bid: float,
    auctioneer_fee_pct: float,
    itbi_pct: float,
    registration_pct: float,
    iptu_arrears: float,
    condo_arrears: float,
    renovation_cost: float,
    other_costs: float,
) -> AcquisitionCosts:
    """Calcula a decomposição do custo de aquisição.

    Premissa: comissão do leiloeiro / ITBI / registro são percentuais sobre
    **o lance** (não sobre o valor de avaliação). Esta é a leitura de mercado
    mais comum em leilões judiciais e extrajudiciais brasileiros.

    Em alguns editais o registro é cobrado por tabela do TJ (não percentual);
    aceitamos uma alíquota linear como aproximação. O override deve ser
    feito em `service.py` quando soubermos calcular pela tabela exata.
    """
    return AcquisitionCosts(
        bid=bid,
        auctioneer_fee=bid * auctioneer_fee_pct,
        itbi=bid * itbi_pct,
        registration=bid * registration_pct,
        iptu_arrears=iptu_arrears,
        condo_arrears=condo_arrears,
        renovation_cost=renovation_cost,
        other_costs=other_costs,
    )


# =============================================================================
# 2. Imposto de Renda
# =============================================================================
def compute_income_tax(
    *,
    buyer_type: str,
    sale_price: float,
    gross_profit: float,
    pf_rate: float,
    pj_rate: float,
) -> float:
    """Imposto de renda estimado sobre a venda.

    * PF: alíquota sobre o ganho de capital (= ``pf_rate * max(gross_profit, 0)``).
    * PJ (Lucro Presumido — aproximação): alíquota sobre a receita de venda
      (= ``pj_rate * sale_price``). Mesmo no prejuízo a PJ paga sobre o
      faturamento — esse é o trade-off do regime presumido. O UI deve
      sinalizar como **estimativa** para que o usuário consulte o contador.
    """
    if buyer_type == "PJ":
        return max(0.0, sale_price) * pj_rate
    return max(0.0, gross_profit) * pf_rate


# =============================================================================
# 3. Lucro & ROI
# =============================================================================
@dataclass(frozen=True, slots=True)
class ProfitBreakdown:
    sale_price: float
    realtor_fee: float
    acquisition_cost_total: float
    gross_profit: float
    income_tax: float
    net_profit: float
    gross_roi_pct: float
    net_roi_pct: float


def compute_profit_and_roi(
    *,
    sale_price: float,
    acquisition_cost_total: float,
    realtor_fee_pct: float,
    income_tax: float,
) -> ProfitBreakdown:
    """Lucro bruto, líquido e ROIs."""
    realtor_fee = sale_price * realtor_fee_pct
    gross_profit = sale_price - acquisition_cost_total - realtor_fee
    net_profit = gross_profit - income_tax

    # ROIs sobre o capital realmente desembolsado.
    if acquisition_cost_total <= 0:
        gross_roi = 0.0
        net_roi = 0.0
    else:
        gross_roi = gross_profit / acquisition_cost_total
        net_roi = net_profit / acquisition_cost_total

    return ProfitBreakdown(
        sale_price=sale_price,
        realtor_fee=realtor_fee,
        acquisition_cost_total=acquisition_cost_total,
        gross_profit=gross_profit,
        income_tax=income_tax,
        net_profit=net_profit,
        gross_roi_pct=gross_roi,
        net_roi_pct=net_roi,
    )


# =============================================================================
# 4. Lance máximo para atingir um ROI alvo
# =============================================================================
@dataclass(frozen=True, slots=True)
class MaxBidParams:
    """Parâmetros que dependem APENAS do lance, ou são fixos.

    O serviço chama este helper depois de já ter resolvido as alíquotas
    aplicáveis (via tabela ITBI / Caixa / etc.).
    """

    sale_price: float
    iptu_arrears: float
    condo_arrears: float
    renovation_cost: float
    other_costs: float
    auctioneer_fee_pct: float
    itbi_pct: float
    registration_pct: float
    realtor_fee_pct: float
    buyer_type: str
    pf_rate: float
    pj_rate: float
    target_net_roi: float


def solve_max_bid(p: MaxBidParams) -> float | None:
    """Resolve algebricamente o maior lance ``B`` tal que ``net_roi == target``.

    Definindo:
      * ``F = aucPct + itbiPct + regPct``  (fatores que escalam com o lance)
      * ``K = iptuArrears + condoArrears + renovCost + otherCosts`` (custos fixos)
      * ``A = B(1 + F) + K``                              (custo aquisição)
      * ``S`` = sale_price (constante)
      * ``R = S · realtorPct``                            (corretagem)
      * ``GP = S − A − R``                                (lucro bruto)
      * ``T``  = imposto:
          - PF: ``T = pf_rate · max(GP, 0)``
          - PJ: ``T = pj_rate · S``                       (constante!)
      * ``NP = GP − T``                                   (lucro líquido)

    Queremos: ``NP / A = target``  ⇒  ``NP = target · A``  ⇒  ``GP − T = target · A``.

    -------------------------------------------------------------------------
    PJ (T constante):
        S − B(1+F) − K − R − T  =  target · ( B(1+F) + K )
        ⇒ B(1+F) · (1 + target)  =  S − R − T − K · (1 + target)
        ⇒ B = ( S − R − T − K(1+target) ) / ( (1+F)(1+target) )

    -------------------------------------------------------------------------
    PF (T = pf · GP, assumindo GP ≥ 0):
        GP · (1 − pf) = target · A
        ⇒ ( S − B(1+F) − K − R ) · (1 − pf)  =  target · ( B(1+F) + K )
        ⇒ B(1+F) · ( (1−pf) + target )  =  (S − R)(1−pf) − K · ( (1−pf) + target )
        ⇒ B = ( (S−R)(1−pf) − K·((1−pf)+target) ) / ( (1+F) · ((1−pf)+target) )

    Se ``GP`` resultar negativo, o caso PF colapsa para ``T = 0`` (não há
    imposto sobre prejuízo). Resolvemos as duas hipóteses e validamos qual
    delas é consistente.

    Retorna ``None`` se o lance for ≤ 0 (alvo inalcançável mesmo com
    lance simbólico — geralmente ROI alvo + custos fixos > preço de venda).
    """
    F = p.auctioneer_fee_pct + p.itbi_pct + p.registration_pct
    K = p.iptu_arrears + p.condo_arrears + p.renovation_cost + p.other_costs
    R = p.sale_price * p.realtor_fee_pct

    one_plus_F = 1.0 + F
    if one_plus_F <= 0:
        return None

    one_plus_target = 1.0 + p.target_net_roi

    # ------------------------ PJ -------------------------------------------
    if p.buyer_type == "PJ":
        T = p.sale_price * p.pj_rate
        numer = p.sale_price - R - T - K * one_plus_target
        denom = one_plus_F * one_plus_target
        if denom <= 0:
            return None
        bid = numer / denom
        return bid if bid > 0 else None

    # ------------------------ PF -------------------------------------------
    pf = p.pf_rate

    # Hipótese 1: GP ≥ 0  →  T = pf * GP
    factor = (1.0 - pf) + p.target_net_roi
    if factor > 0:
        numer = (p.sale_price - R) * (1.0 - pf) - K * factor
        denom = one_plus_F * factor
        if denom > 0:
            bid_h1 = numer / denom
            # Validar: GP resultante deve ser ≥ 0
            A_h1 = bid_h1 * one_plus_F + K
            GP_h1 = p.sale_price - A_h1 - R
            if bid_h1 > 0 and GP_h1 >= 0:
                return bid_h1

    # Hipótese 2: GP < 0  →  T = 0  (prejuízo, mas o usuário aceita)
    # Nesse caso: GP = target · A  ⇒  S − B(1+F) − K − R = target · ( B(1+F) + K )
    numer = p.sale_price - R - K * one_plus_target
    denom = one_plus_F * one_plus_target
    if denom > 0:
        bid_h2 = numer / denom
        A_h2 = bid_h2 * one_plus_F + K
        GP_h2 = p.sale_price - A_h2 - R
        if bid_h2 > 0 and GP_h2 < 0:
            return bid_h2

    return None
