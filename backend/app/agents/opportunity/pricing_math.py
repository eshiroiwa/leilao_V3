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

# Reexportado de ``assumptions`` para manter ``pricing_math`` puro e auto-contido.
# Brackets: tupla de ``(teto_da_faixa_BRL, alíquota)`` ordenada por teto crescente.
PFBracket = tuple[float, float]


# =============================================================================
# 1. Custos
# =============================================================================
@dataclass(frozen=True, slots=True)
class AcquisitionCosts:
    """Decomposição do custo de aquisição (tudo que sai do bolso até a venda).

    Inclui o "custo de carregamento" (``holding_costs``) que acumula
    IPTU + condomínio MENSAIS multiplicados pelos meses de holding.
    Em deals com holding longo isso pode comer 5-10% da margem.
    """

    bid: float
    auctioneer_fee: float
    itbi: float
    registration: float
    iptu_arrears: float
    condo_arrears: float
    renovation_cost: float
    other_costs: float
    holding_costs: float = 0.0

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
            + self.holding_costs
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
    monthly_iptu: float = 0.0,
    monthly_condo: float = 0.0,
    holding_months: int = 12,
) -> AcquisitionCosts:
    """Calcula a decomposição do custo de aquisição.

    Premissa: comissão do leiloeiro / ITBI / registro são percentuais sobre
    **o lance** (não sobre o valor de avaliação). Esta é a leitura de mercado
    mais comum em leilões judiciais e extrajudiciais brasileiros.

    Em alguns editais o registro é cobrado por tabela do TJ (não percentual);
    aceitamos uma alíquota linear como aproximação. O override deve ser
    feito em `service.py` quando soubermos calcular pela tabela exata.

    ``monthly_iptu`` e ``monthly_condo`` são as parcelas mensais CORRENTES
    (não as em atraso); multiplicadas por ``holding_months`` resultam no
    custo de carregamento. Defaults zerados preservam o comportamento
    histórico para callers que ainda não preenchem esses campos.
    """
    holding_costs = max(0, holding_months) * (
        max(0.0, monthly_iptu) + max(0.0, monthly_condo)
    )
    return AcquisitionCosts(
        bid=bid,
        auctioneer_fee=bid * auctioneer_fee_pct,
        itbi=bid * itbi_pct,
        registration=bid * registration_pct,
        iptu_arrears=iptu_arrears,
        condo_arrears=condo_arrears,
        renovation_cost=renovation_cost,
        other_costs=other_costs,
        holding_costs=holding_costs,
    )


# =============================================================================
# 2. Imposto de Renda
# =============================================================================
def compute_income_tax(
    *,
    buyer_type: str,
    sale_price: float,
    gross_profit: float,
    pf_brackets: tuple[PFBracket, ...],
    pj_rate: float,
) -> float:
    """Imposto de renda estimado sobre a venda.

    * PF: ganho de capital com tabela PROGRESSIVA (Lei 13.259/2016).
      ``pf_brackets`` é uma tupla ordenada de ``(teto_da_faixa, alíquota)``
      e cada faixa contribui apenas com a PARCELA do ganho dentro dela.
      Prejuízo (gross_profit ≤ 0) não paga IR.
    * PJ (Lucro Presumido — aproximação): alíquota sobre a receita de venda
      (= ``pj_rate * sale_price``). Mesmo no prejuízo a PJ paga sobre o
      faturamento — esse é o trade-off do regime presumido. O UI deve
      sinalizar como **estimativa** para que o usuário consulte o contador.
    """
    if buyer_type == "PJ":
        return max(0.0, sale_price) * pj_rate
    gp = max(0.0, gross_profit)
    if gp <= 0 or not pf_brackets:
        return 0.0
    tax = 0.0
    prev_limit = 0.0
    for limit, rate in pf_brackets:
        if gp <= prev_limit:
            break
        taxable_in_bracket = min(gp, limit) - prev_limit
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev_limit = limit
    return tax


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
    annualized_net_roi_pct: float


def annualize_roi(net_roi_pct: float, holding_months: int) -> float:
    """Converte um ROI bruto (ganho/capital ao final de ``holding_months``)
    em ROI ANUALIZADO equivalente: ``(1 + roi)^(12/holding) − 1``.

    Para ``holding_months = 12`` devolve o próprio ``net_roi_pct`` (sem efeito).
    Para holding mais longo, o annualized é MENOR — captura corretamente
    a erosão temporal de retornos (50% bruto em 24 meses ≈ 22,5% a.a.).
    Para holding mais curto, é MAIOR (15% bruto em 6 meses ≈ 32,25% a.a.).

    Domínio: para evitar ``(1+roi)`` < 0 em prejuízos extremos, clampamos
    o fator base em ``1e-9`` antes da exponenciação. Resultado para
    prejuízo total se aproxima de -100% anualizado.
    """
    if holding_months <= 0:
        return net_roi_pct
    base = 1.0 + net_roi_pct
    if base <= 1e-9:
        return -1.0
    return base ** (12.0 / holding_months) - 1.0


def compute_profit_and_roi(
    *,
    sale_price: float,
    acquisition_cost_total: float,
    realtor_fee_pct: float,
    income_tax: float,
    holding_months: int = 12,
) -> ProfitBreakdown:
    """Lucro bruto, líquido e ROIs (incluindo anualizado).

    ``holding_months`` controla a anualização do net_roi. Default 12 deixa
    o ``annualized_net_roi_pct`` idêntico ao ``net_roi_pct``.
    """
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

    annualized = annualize_roi(net_roi, holding_months)

    return ProfitBreakdown(
        sale_price=sale_price,
        realtor_fee=realtor_fee,
        acquisition_cost_total=acquisition_cost_total,
        gross_profit=gross_profit,
        income_tax=income_tax,
        net_profit=net_profit,
        gross_roi_pct=gross_roi,
        net_roi_pct=net_roi,
        annualized_net_roi_pct=annualized,
    )


# =============================================================================
# 4. Lance máximo para atingir um ROI alvo
# =============================================================================
@dataclass(frozen=True, slots=True)
class MaxBidParams:
    """Parâmetros que dependem APENAS do lance, ou são fixos.

    O serviço chama este helper depois de já ter resolvido as alíquotas
    aplicáveis (via tabela ITBI / Caixa / etc.).

    ``pf_brackets`` substitui o antigo ``pf_rate`` único — agora a tabela
    PROGRESSIVA do IR sobre ganho de capital (Lei 13.259/2016) é usada
    diretamente no solver.

    ``holding_costs`` entra como mais um custo fixo (somado em K). Default
    0 mantém retrocompatibilidade com callers que ainda não preenchem.
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
    pf_brackets: tuple[PFBracket, ...]
    pj_rate: float
    target_net_roi: float
    holding_costs: float = 0.0


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
          - PF: tabela PROGRESSIVA (Lei 13.259/2016). Dentro de uma faixa
            ``i`` de teto ``L_i`` e alíquota ``pf_i``, com contribuição
            acumulada das faixas anteriores ``c_i``, vale
            ``T(GP) = c_i + pf_i · (GP − L_{i-1})`` se ``L_{i-1} ≤ GP < L_i``.
            Para ``GP ≤ 0`` ⇒ ``T = 0``.
          - PJ: ``T = pj_rate · S``                       (constante!)
      * ``NP = GP − T``                                   (lucro líquido)

    Queremos: ``NP / A = target``  ⇒  ``GP − T = target · A``.

    -------------------------------------------------------------------------
    PJ (T constante):
        S − B(1+F) − K − R − T  =  target · ( B(1+F) + K )
        ⇒ B(1+F) · (1 + target)  =  S − R − T − K · (1 + target)
        ⇒ B = ( S − R − T − K(1+target) ) / ( (1+F)(1+target) )

    -------------------------------------------------------------------------
    PF — uma faixa de cada vez. Dentro da faixa ``i`` (válida quando
    ``L_{i-1} ≤ GP < L_i``):
        GP · (1 − pf_i) + pf_i·L_{i-1} − c_i  =  target · A
        ⇒ B(1+F) · ((1−pf_i) + target)  =
              (S−R)(1−pf_i) − K·((1−pf_i)+target) + pf_i·L_{i-1} − c_i
        ⇒ B = numerador / ( (1+F) · ((1−pf_i)+target) )

    Iteramos pelas faixas, resolvemos cada uma, validamos que o ``GP``
    resultante de fato cai na faixa, e devolvemos o MAIOR ``B`` válido —
    o maior lance é sempre o da menor alíquota efetiva, porque com lance
    maior o lucro encolhe e o ganho tende a entrar em faixas inferiores.
    Ainda há a Hipótese GP < 0 (prejuízo aceito, T = 0).

    Retorna ``None`` se nenhuma faixa produz lance positivo válido.
    """
    F = p.auctioneer_fee_pct + p.itbi_pct + p.registration_pct
    K = (
        p.iptu_arrears
        + p.condo_arrears
        + p.renovation_cost
        + p.other_costs
        + p.holding_costs
    )
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

    # ------------------------ PF (tabela progressiva) ----------------------
    candidates: list[float] = []

    prev_limit = 0.0
    cumulative_tax = 0.0  # T acumulado nas faixas inferiores até prev_limit
    for limit, pf_i in p.pf_brackets:
        factor = (1.0 - pf_i) + p.target_net_roi
        if factor > 0:
            denom = one_plus_F * factor
            if denom > 0:
                numer = (
                    (p.sale_price - R) * (1.0 - pf_i)
                    - K * factor
                    + pf_i * prev_limit
                    - cumulative_tax
                )
                bid_i = numer / denom
                # Validar: GP resultante deve cair na faixa atual.
                A_i = bid_i * one_plus_F + K
                GP_i = p.sale_price - A_i - R
                if bid_i > 0 and prev_limit <= GP_i < limit:
                    candidates.append(bid_i)
        # Atualiza para a próxima faixa: acumula imposto da faixa cheia.
        if limit == float("inf"):
            break
        cumulative_tax += (limit - prev_limit) * pf_i
        prev_limit = limit

    # Hipótese final: GP < 0 → T = 0 (prejuízo, mas o usuário aceita).
    numer = p.sale_price - R - K * one_plus_target
    denom = one_plus_F * one_plus_target
    if denom > 0:
        bid_neg = numer / denom
        A_neg = bid_neg * one_plus_F + K
        GP_neg = p.sale_price - A_neg - R
        if bid_neg > 0 and GP_neg < 0:
            candidates.append(bid_neg)

    if not candidates:
        return None
    # MAIOR lance válido — corresponde à menor alíquota efetiva possível
    # dado o cenário (ganho de capital cai na primeira faixa que comporta).
    return max(candidates)
