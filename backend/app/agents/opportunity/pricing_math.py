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
# 0. Financiamento / parcelamento — Price + judicial
# =============================================================================
@dataclass(frozen=True, slots=True)
class FinancingTerms:
    """Métricas calculadas do financiamento/parcelamento para um cenário.

    ``mode = "cash"`` → entry = bid, pmt = 0, balance_at_sale = 0, sem juros.
    """

    mode: str
    entry: float
    financed_amount: float
    pmt: float
    rate_monthly_pct: float
    loan_months: int
    holding_payments: float
    balance_at_sale: float
    interest_paid_holding: float


def _monthly_from_annual(annual_pct: float) -> float:
    """Equivalente mensal de uma taxa anual nominal: (1 + i_a)^(1/12) − 1."""
    if annual_pct <= 0:
        return 0.0
    return (1.0 + annual_pct) ** (1.0 / 12.0) - 1.0


def _price_pmt(financed: float, rate_monthly: float, n: int) -> float:
    """Parcela Price (PMT) — amortização constante de juros + principal."""
    if financed <= 0 or n <= 0:
        return 0.0
    if rate_monthly <= 0:
        return financed / n
    return financed * rate_monthly / (1.0 - (1.0 + rate_monthly) ** (-n))


def _price_balance(
    financed: float, rate_monthly: float, pmt: float, periods_paid: int
) -> float:
    """Saldo devedor de um Price após ``periods_paid`` parcelas pagas."""
    if periods_paid <= 0:
        return financed
    if rate_monthly <= 0:
        return max(0.0, financed - pmt * periods_paid)
    factor = (1.0 + rate_monthly) ** periods_paid
    return max(
        0.0,
        financed * factor - pmt * (factor - 1.0) / rate_monthly,
    )


def compute_financing_terms(
    *,
    bid: float,
    holding_months: int,
    payment_mode: str = "cash",
    down_payment_pct: float | None = None,
    loan_months: int | None = None,
    loan_rate_annual_pct: float | None = None,
    installments_count: int | None = None,
    installments_index: str | None = None,
    ipca_annual: float | None = None,
    selic_annual: float | None = None,
    default_loan_rate_annual: float = 0.115,
) -> FinancingTerms:
    """Resolve as métricas de pagamento para um cenário.

    - ``cash``: entrada = bid, parcela 0, sem saldo.
    - ``financed_bank``: amortização Price; defaults: entrada 30%, prazo 240 m,
      taxa fornecida pelo caller ou ``default_loan_rate_annual``.
    - ``installments_judicial``: parcelas mensais; correção pelo índice
      escolhido (IPCA/SELIC/nenhum). Default: entrada 25%, 30 parcelas, IPCA.

    Em todos os modos parcelados, ``holding_payments`` cobre apenas as
    parcelas pagas dentro do horizonte de revenda; o saldo remanescente
    abate da receita líquida no momento da venda.
    """
    if bid <= 0:
        return FinancingTerms(
            mode="cash",
            entry=0.0,
            financed_amount=0.0,
            pmt=0.0,
            rate_monthly_pct=0.0,
            loan_months=0,
            holding_payments=0.0,
            balance_at_sale=0.0,
            interest_paid_holding=0.0,
        )

    if payment_mode == "cash":
        return FinancingTerms(
            mode="cash",
            entry=bid,
            financed_amount=0.0,
            pmt=0.0,
            rate_monthly_pct=0.0,
            loan_months=0,
            holding_payments=0.0,
            balance_at_sale=0.0,
            interest_paid_holding=0.0,
        )

    if payment_mode == "financed_bank":
        dp = down_payment_pct if down_payment_pct is not None else 0.30
        n = loan_months if loan_months is not None else 240
        rate_annual = (
            loan_rate_annual_pct
            if loan_rate_annual_pct is not None
            else default_loan_rate_annual
        )
        rate_monthly = _monthly_from_annual(rate_annual)
        entry = bid * dp
        financed = bid - entry
        pmt = _price_pmt(financed, rate_monthly, n)
        periods_paid = max(0, min(holding_months, n))
        holding_payments = pmt * periods_paid
        balance = _price_balance(financed, rate_monthly, pmt, periods_paid)
        # Juros pagos = total pago − amortização do principal.
        interest = max(0.0, holding_payments - (financed - balance))
        return FinancingTerms(
            mode="financed_bank",
            entry=entry,
            financed_amount=financed,
            pmt=pmt,
            rate_monthly_pct=rate_monthly,
            loan_months=n,
            holding_payments=holding_payments,
            balance_at_sale=balance,
            interest_paid_holding=interest,
        )

    if payment_mode == "installments_judicial":
        dp = down_payment_pct if down_payment_pct is not None else 0.25
        n = installments_count if installments_count is not None else 30
        idx = installments_index or "ipca"
        if idx == "selic":
            annual = selic_annual if selic_annual is not None else 0.105
        elif idx == "ipca":
            annual = ipca_annual if ipca_annual is not None else 0.045
        else:
            annual = 0.0
        rate_monthly = _monthly_from_annual(annual)
        entry = bid * dp
        financed = bid - entry
        # No judicial a parcela base é nominal (sem juros); a correção atua
        # como reajuste mensal aproximado. Usamos a fórmula Price para
        # convergir comportamento: com rate=0 cai em parcela linear.
        pmt = _price_pmt(financed, rate_monthly, n)
        periods_paid = max(0, min(holding_months, n))
        holding_payments = pmt * periods_paid
        balance = _price_balance(financed, rate_monthly, pmt, periods_paid)
        interest = max(0.0, holding_payments - (financed - balance))
        return FinancingTerms(
            mode="installments_judicial",
            entry=entry,
            financed_amount=financed,
            pmt=pmt,
            rate_monthly_pct=rate_monthly,
            loan_months=n,
            holding_payments=holding_payments,
            balance_at_sale=balance,
            interest_paid_holding=interest,
        )

    # Modo desconhecido → fallback à vista.
    return compute_financing_terms(
        bid=bid, holding_months=holding_months, payment_mode="cash",
    )


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
    pj_regime: str = "presumido",
    pj_real_income_rate: float = 0.24,
    pj_real_revenue_rate: float = 0.0925,
) -> float:
    """Imposto de renda estimado sobre a venda.

    * PF: ganho de capital com tabela PROGRESSIVA (Lei 13.259/2016).
      ``pf_brackets`` é uma tupla ordenada de ``(teto_da_faixa, alíquota)``
      e cada faixa contribui apenas com a PARCELA do ganho dentro dela.
      Prejuízo (gross_profit ≤ 0) não paga IR.
    * PJ Lucro Presumido (``pj_regime="presumido"``, default): alíquota
      única sobre a receita de venda (= ``pj_rate * sale_price``). Mesmo
      no prejuízo a PJ paga sobre o faturamento — trade-off do regime.
    * PJ Lucro Real (``pj_regime="real"``): IRPJ+CSLL (``pj_real_income_rate``)
      sobre o LUCRO (max(GP, 0)) + PIS/COFINS (``pj_real_revenue_rate``) sobre
      a RECEITA (sem crédito — conservador). No prejuízo, IRPJ/CSLL=0 mas
      PIS/COFINS ainda incidem sobre a venda.

    Em todos os casos o UI deve sinalizar como **estimativa** para que o
    usuário consulte o contador.
    """
    if buyer_type == "PJ":
        if pj_regime == "real":
            income_part = max(0.0, gross_profit) * pj_real_income_rate
            revenue_part = max(0.0, sale_price) * pj_real_revenue_rate
            return income_part + revenue_part
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
    financing: FinancingTerms | None = None,
) -> ProfitBreakdown:
    """Lucro bruto, líquido e ROIs (incluindo anualizado).

    ``holding_months`` controla a anualização do net_roi. Default 12 deixa
    o ``annualized_net_roi_pct`` idêntico ao ``net_roi_pct``.

    Quando ``financing`` é fornecido e o modo NÃO é ``cash``:
    - ``acquisition_cost_total`` é interpretado como o agregado dos custos
      acessórios (auctioneer + ITBI + registration + dívidas + reforma +
      outros + holding) — SEM o valor cheio do lance, que já é representado
      por ``entry + holding_payments + balance_at_sale``.
    - **Capital alocado** (denominador do ROI) = entrada + parcelas pagas
      no holding + acquisition_cost_total.
    - **Receita líquida** = sale_price − realtor_fee − balance_at_sale.
    - **Lucro bruto** = receita_líquida − capital_alocado (juros e custos
      acessórios já estão dentro).
    """
    realtor_fee = sale_price * realtor_fee_pct

    if financing is None or financing.mode == "cash":
        # Comportamento histórico — capital = custo total + bid integral
        # (já somado em acquisition_cost_total).
        capital_alocado = acquisition_cost_total
        gross_profit = sale_price - acquisition_cost_total - realtor_fee
        net_revenue = sale_price - realtor_fee
    else:
        capital_alocado = (
            financing.entry + financing.holding_payments + acquisition_cost_total
        )
        net_revenue = sale_price - realtor_fee - financing.balance_at_sale
        gross_profit = net_revenue - capital_alocado

    net_profit = gross_profit - income_tax

    if capital_alocado <= 0:
        gross_roi = 0.0
        net_roi = 0.0
    else:
        gross_roi = gross_profit / capital_alocado
        net_roi = net_profit / capital_alocado

    annualized = annualize_roi(net_roi, holding_months)

    return ProfitBreakdown(
        sale_price=sale_price,
        realtor_fee=realtor_fee,
        acquisition_cost_total=capital_alocado,
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
    pj_regime: str = "presumido"
    pj_real_income_rate: float = 0.24
    pj_real_revenue_rate: float = 0.0925


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
        if p.pj_regime == "real":
            # Lucro Real — duas hipóteses dependendo do sinal de GP:
            # H1: GP ≥ 0 → T = pj_rev · S + pj_inc · GP
            # H2: GP < 0 → T = pj_rev · S (IRPJ/CSLL zerados)
            pj_rev = p.pj_real_revenue_rate
            pj_inc = p.pj_real_income_rate
            candidates: list[float] = []

            # Hipótese 1 (GP ≥ 0):
            #   GP·(1−pj_inc) − pj_rev·S = target · A
            #   ⇒ B(1+F)·((1−pj_inc) + target) = (S−R)(1−pj_inc) − K·((1−pj_inc)+target) − pj_rev·S
            factor = (1.0 - pj_inc) + p.target_net_roi
            if factor > 0:
                denom_h1 = one_plus_F * factor
                if denom_h1 > 0:
                    numer_h1 = (
                        (p.sale_price - R) * (1.0 - pj_inc)
                        - K * factor
                        - pj_rev * p.sale_price
                    )
                    bid_h1 = numer_h1 / denom_h1
                    A_h1 = bid_h1 * one_plus_F + K
                    GP_h1 = p.sale_price - A_h1 - R
                    if bid_h1 > 0 and GP_h1 >= 0:
                        candidates.append(bid_h1)

            # Hipótese 2 (GP < 0):
            #   GP = target · A → S − B(1+F) − K − R = target · (B(1+F) + K)
            #   PIS/COFINS reduzem o "S efetivo" disponível: S' = S(1 − pj_rev)
            denom_h2 = one_plus_F * one_plus_target
            if denom_h2 > 0:
                numer_h2 = (
                    p.sale_price * (1.0 - pj_rev) - R - K * one_plus_target
                )
                bid_h2 = numer_h2 / denom_h2
                A_h2 = bid_h2 * one_plus_F + K
                GP_h2 = p.sale_price - A_h2 - R
                if bid_h2 > 0 and GP_h2 < 0:
                    candidates.append(bid_h2)

            return max(candidates) if candidates else None

        # Presumido (default): T constante = pj_rate · S
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


# =============================================================================
# 5. Lance máximo NUMÉRICO — para modos com financiamento/parcelamento
# =============================================================================
@dataclass(frozen=True, slots=True)
class MaxBidNumericParams:
    """Parâmetros para a busca numérica do lance máximo quando o lance entra
    de forma não-linear no cálculo (financiamento Price, parcelamento com
    índice de correção).

    Estende ``MaxBidParams`` com os campos de payment_mode + parâmetros do
    financiamento. Quando ``payment_mode = "cash"`` o caller deve preferir
    ``solve_max_bid`` (algébrico) por performance.
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
    holding_costs: float
    holding_months: int
    pj_regime: str = "presumido"
    pj_real_income_rate: float = 0.24
    pj_real_revenue_rate: float = 0.0925
    payment_mode: str = "cash"
    down_payment_pct: float | None = None
    loan_months: int | None = None
    loan_rate_annual_pct: float | None = None
    installments_count: int | None = None
    installments_index: str | None = None
    ipca_annual: float | None = None
    selic_annual: float | None = None
    default_loan_rate_annual: float = 0.115


def _net_roi_at_bid(p: MaxBidNumericParams, bid: float) -> float:
    """Calcula o net_roi resultante de um lance específico — usado pelo
    solver numérico. Reproduz a stack inteira de cálculo (custos → IR →
    profit_and_roi com financing)."""
    if bid <= 0:
        return -1.0
    fin = compute_financing_terms(
        bid=bid,
        holding_months=p.holding_months,
        payment_mode=p.payment_mode,
        down_payment_pct=p.down_payment_pct,
        loan_months=p.loan_months,
        loan_rate_annual_pct=p.loan_rate_annual_pct,
        installments_count=p.installments_count,
        installments_index=p.installments_index,
        ipca_annual=p.ipca_annual,
        selic_annual=p.selic_annual,
        default_loan_rate_annual=p.default_loan_rate_annual,
    )

    accessory_costs = (
        bid * p.auctioneer_fee_pct
        + bid * p.itbi_pct
        + bid * p.registration_pct
        + p.iptu_arrears
        + p.condo_arrears
        + p.renovation_cost
        + p.other_costs
        + p.holding_costs
    )
    # No modo cash, o custo total inclui o bid integral. Nos modos parcelados,
    # o "acquisition" recebido por compute_profit_and_roi é apenas o agregado
    # acessório — o bid é representado por entry/holding_payments/balance.
    acq_total = (
        bid + accessory_costs
        if fin.mode == "cash"
        else accessory_costs
    )

    realtor_fee = p.sale_price * p.realtor_fee_pct
    if fin.mode == "cash":
        gross_profit = p.sale_price - acq_total - realtor_fee
    else:
        net_revenue = p.sale_price - realtor_fee - fin.balance_at_sale
        capital = fin.entry + fin.holding_payments + acq_total
        gross_profit = net_revenue - capital

    tax = compute_income_tax(
        buyer_type=p.buyer_type,
        sale_price=p.sale_price,
        gross_profit=gross_profit,
        pf_brackets=p.pf_brackets,
        pj_rate=p.pj_rate,
        pj_regime=p.pj_regime,
        pj_real_income_rate=p.pj_real_income_rate,
        pj_real_revenue_rate=p.pj_real_revenue_rate,
    )

    breakdown = compute_profit_and_roi(
        sale_price=p.sale_price,
        acquisition_cost_total=acq_total,
        realtor_fee_pct=p.realtor_fee_pct,
        income_tax=tax,
        holding_months=p.holding_months,
        financing=fin,
    )
    return breakdown.net_roi_pct


def solve_max_bid_numeric(
    p: MaxBidNumericParams, *, max_iter: int = 80, tol_brl: float = 1.0
) -> float | None:
    """Busca binária pelo maior lance que atinge ``target_net_roi``.

    A função ``bid → net_roi(bid)`` é monotonicamente decrescente em todos
    os modos suportados (mais lance ⇒ mais capital ⇒ menos ROI). Procuramos
    o ``bid*`` tal que ``net_roi(bid*) = target``.

    Limites: lance mínimo R$ 1, lance máximo = sale_price (acima disso já é
    prejuízo certo). Retorna ``None`` se nem com lance mínimo o target é
    alcançado (mercado fora de ROI no preço de venda dado).
    """
    if p.sale_price <= 0:
        return None
    lo = 1.0
    hi = p.sale_price * 1.5  # margem para casos onde o target é negativo

    roi_lo = _net_roi_at_bid(p, lo)
    if roi_lo < p.target_net_roi:
        # Mesmo no lance mínimo o ROI já é menor que o target.
        return None
    roi_hi = _net_roi_at_bid(p, hi)
    if roi_hi >= p.target_net_roi:
        # Mesmo no teto alto o target é atendido — retorna o teto.
        return hi

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        roi_mid = _net_roi_at_bid(p, mid)
        if roi_mid >= p.target_net_roi:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol_brl:
            break
    return lo
