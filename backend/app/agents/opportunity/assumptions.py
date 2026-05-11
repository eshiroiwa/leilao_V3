"""Premissas (alíquotas, defaults e tabelas) do AGENTE 3.

Tudo o que é "assumption do mercado/legislação" mora aqui em UM ÚNICO arquivo.
Quando você quiser ajustar — ex.: adicionar uma cidade, reduzir alíquota de
ITBI, mudar o R$/m² da reforma básica — o blast radius é só este módulo.

NÃO faça `import *` daqui em outros módulos: importe nominalmente para que
ferramentas de busca (`Grep`) mostrem onde cada constante é usada.

Auditoria: o `service.py` snapshota as premissas usadas em cada análise no
campo `assumptions` (jsonb) — assim, mesmo que esta tabela mude no futuro,
análises antigas continuam reproduzíveis.
"""

from __future__ import annotations

import unicodedata
from typing import Final, Literal

# =============================================================================
# Tipos auxiliares
# =============================================================================
BuyerType = Literal["PF", "PJ"]
PJRegime = Literal["presumido", "real"]
RenovationLevel = Literal["none", "basic", "moderate", "full", "premium"]
OccupancyKey = Literal["vacant", "occupied", "unknown"]
VerdictType = Literal[
    "BOA_OPORTUNIDADE",
    "BOA_COM_RESSALVAS",
    "NEUTRO",
    "INVIAVEL",
    "INDETERMINADO",
]


# =============================================================================
# 1. Custos PROPORCIONAIS ao lance
# =============================================================================

# ITBI por (cidade_normalizada, UF). Valores aproximados/observados —
# refine conforme necessário. Cobre as cidades mais comuns em leilão.
ITBI_BY_CITY: Final[dict[tuple[str, str], float]] = {
    ("sao paulo", "SP"): 0.03,
    ("rio de janeiro", "RJ"): 0.03,
    ("brasilia", "DF"): 0.03,
    ("belo horizonte", "MG"): 0.03,
    ("salvador", "BA"): 0.03,
    ("fortaleza", "CE"): 0.03,
    ("curitiba", "PR"): 0.027,
    ("porto alegre", "RS"): 0.03,
    ("recife", "PE"): 0.03,
    ("campinas", "SP"): 0.027,
    ("santo andre", "SP"): 0.03,
    ("guarulhos", "SP"): 0.03,
    ("osasco", "SP"): 0.03,
    ("santos", "SP"): 0.027,
    ("sao bernardo do campo", "SP"): 0.03,
    ("pindamonhangaba", "SP"): 0.02,
    ("niteroi", "RJ"): 0.03,
    ("florianopolis", "SC"): 0.02,
}
ITBI_DEFAULT: Final[float] = 0.03  # 3% — alíquota mais comum no Brasil


# Comissão do leiloeiro:
#   * Tradicional (judicial/extrajudicial particular): 5% sobre o arremate
#     (Decreto 21.981/1932). Quando o edital não declara, usamos o default.
#   * Caixa Online ("venda online direta"): 0% — a Caixa não cobra comissão
#     de leiloeiro nessa modalidade.
#   * SEM leiloeiro nominal (auctioneer_id is None): 0% — venda direta sem
#     intermediário, não há a quem pagar comissão. Esse é o caso típico
#     dos lotes em ``venda-imoveis.caixa.gov.br`` que não têm leiloeiro
#     designado.
AUCTIONEER_FEE_PCT_DEFAULT: Final[float] = 0.05
AUCTIONEER_FEE_PCT_CAIXA: Final[float] = 0.00
AUCTIONEER_FEE_PCT_NO_AUCTIONEER: Final[float] = 0.00

# Slugs dos leiloeiros que usam venda online direta SEM comissão.
# Mantenha em lowercase. (Caixa atua via portal próprio; quando virmos um
# auctioneer com slug "caixa" ou variantes, não cobramos taxa de leiloeiro.)
SLUGS_NO_AUCTIONEER_FEE: Final[frozenset[str]] = frozenset({"caixa", "caixa-leiloes"})

# Registro de imóveis: cartórios cobram por TABELA progressiva por estado.
# 1.5% é uma boa aproximação para imóveis até ~1MM em SP/RJ. O valor real
# pode ser consultado nas tabelas dos TJs — para o MVP, usamos linear.
REGISTRATION_PCT_DEFAULT: Final[float] = 0.015


# =============================================================================
# 2. Custos da VENDA
# =============================================================================
REALTOR_FEE_PCT: Final[float] = 0.06  # comissão de venda do imóvel


# =============================================================================
# 3. Imposto de Renda
# =============================================================================
# Pessoa Física — ganho de capital sobre operações imobiliárias (Lei 13.259/2016).
# Alíquota PROGRESSIVA por faixa sobre o ganho de capital (em BRL):
#   * até R$ 5.000.000     → 15%
#   * R$ 5MM a R$ 10MM     → 17,5%
#   * R$ 10MM a R$ 30MM    → 20%
#   * acima de R$ 30MM     → 22,5%
#
# Cada bracket = (teto_da_faixa_BRL, alíquota). Última faixa usa inf como teto.
# Importante: progressivo = a alíquota maior só incide sobre a PARCELA do ganho
# que excede o teto da faixa anterior (não sobre o ganho inteiro).
PFBracket = tuple[float, float]
IR_PF_BRACKETS: Final[tuple[PFBracket, ...]] = (
    (5_000_000.0, 0.150),
    (10_000_000.0, 0.175),
    (30_000_000.0, 0.200),
    (float("inf"), 0.225),
)

# Alíquota da PRIMEIRA faixa — usada como referência no snapshot/UI e como
# fallback quando o consumidor precisa de "uma alíquota" representativa.
# A maioria dos leilões cabe na primeira faixa (<R$5MM), então 15% é a
# alíquota efetiva esperada em 99% dos casos.
IR_PF_PCT: Final[float] = IR_PF_BRACKETS[0][1]

# Pessoa Jurídica — Lucro Presumido (estimativa simplificada):
#   IRPJ + CSLL + PIS + COFINS sobre venda de imóvel costuma somar ~6.73%
#   (32% × 15% IRPJ + 32% × 9% CSLL + 0.65% PIS + 3% COFINS).
# Usamos 6.5% para o cliente entender que é uma estimativa. O UI deve
# DEIXAR CLARO que é "estimativa simplificada — consulte seu contador".
IR_PJ_PCT: Final[float] = 0.065

# Pessoa Jurídica — Lucro REAL (estimativa simplificada conservadora):
#   * IRPJ 15% + CSLL 9% sobre o LUCRO (sale_price − acquisition_cost − realtor_fee).
#     Ignoramos o adicional de 10% acima de R$240k/ano (depende do consolidado
#     anual da empresa, não dá pra computar deal-a-deal de forma defensável).
#   * PIS 1,65% + COFINS 7,6% sobre a RECEITA (não-cumulativo). Em Lucro Real
#     o contribuinte tem crédito de PIS/COFINS sobre algumas despesas (ITBI,
#     registro, materiais de reforma quando há nota), mas ignoramos os créditos
#     na estimativa (cenário CONSERVADOR — imposto mais alto).
#
# Em deals com PREJUÍZO contábil, Lucro Real é vantajoso (IRPJ/CSLL = 0; só
# PIS/COFINS sobre venda). Em deals lucrativos isolados, Presumido costuma
# ganhar (6,5% liso vs ~24% sobre lucro + 9,25% sobre receita). O usuário PJ
# que escolhe ``regime="real"`` geralmente JÁ é obrigado pelo regime anual.
IR_PJ_REAL_INCOME_RATE: Final[float] = 0.24
IR_PJ_REAL_REVENUE_RATE: Final[float] = 0.0925


def pf_income_tax_progressive(
    gross_profit: float,
    brackets: tuple[PFBracket, ...] = IR_PF_BRACKETS,
) -> float:
    """Imposto PF sobre ganho de capital aplicando a tabela PROGRESSIVA.

    Para ``gross_profit <= 0`` devolve 0 (PF não paga IR sobre prejuízo).
    Para ``gross_profit > 0``, soma a contribuição de cada faixa sobre a
    parcela do ganho que cai dentro dela. Ex.: ganho de R$ 6MM resulta
    em 5MM × 15% + 1MM × 17,5% = 925k (alíquota efetiva ≈ 15,42%), e
    NÃO 6MM × 17,5% = 1,05M.

    ``brackets`` deve estar ordenado por teto crescente. A última faixa
    geralmente usa ``float("inf")`` como teto para capturar qualquer
    excesso. Brackets vazios → imposto 0.
    """
    if gross_profit <= 0 or not brackets:
        return 0.0
    tax = 0.0
    prev_limit = 0.0
    for limit, rate in brackets:
        if gross_profit <= prev_limit:
            break
        taxable_in_bracket = min(gross_profit, limit) - prev_limit
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev_limit = limit
    return tax


# =============================================================================
# 4. Reforma — R$/m²
# =============================================================================
RENOVATION_PER_M2: Final[dict[RenovationLevel, float]] = {
    "none": 0.0,
    "basic": 500.0,      # pintura, pequenos reparos
    "moderate": 1_000.0, # acabamentos novos, elétrica/hidráulica parcial
    "full": 1_500.0,     # reforma estrutural completa, sem mudar planta
    "premium": 2_500.0,  # alto padrão, materiais top de linha
}


# =============================================================================
# 5. Outros custos — defaults sugeridos por tipo de ocupação
# =============================================================================
OTHER_COSTS_DEFAULT: Final[dict[OccupancyKey, float]] = {
    "vacant": 3_000.0,    # mudança/limpeza inicial
    "occupied": 15_000.0, # advogado + oficial de justiça + caminhão
    "unknown": 8_000.0,   # média — sinal amarelo
}


# =============================================================================
# 6. ROI alvo padrão
# =============================================================================
DEFAULT_TARGET_NET_ROI: Final[float] = 0.40


# =============================================================================
# 7. Probabilidades dos 3 cenários (pessimista / realista / otimista)
# =============================================================================
# Pesos que defaultam a heurística "cauda P10 / centro P50 / cauda P90".
# Soma exatamente 1,0. Quando o Monte Carlo da Fase 3 entrar, esses pesos
# serão substituídos por amostragem real e essas constantes serão usadas
# apenas como fallback de UI quando a simulação não estiver disponível.
SCENARIO_PROB_PESSIMISTA: Final[float] = 0.30
SCENARIO_PROB_REALISTA: Final[float] = 0.40
SCENARIO_PROB_OTIMISTA: Final[float] = 0.30


# =============================================================================
# Helpers de lookup
# =============================================================================
def _normalize_city(city: str | None) -> str:
    """Normaliza cidade para chave do dicionário ITBI_BY_CITY:
    minúsculas, sem acentos, espaços compactados."""
    if not city:
        return ""
    nfkd = unicodedata.normalize("NFKD", city)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(no_accents.lower().split())


def itbi_pct_for(city: str | None, state: str | None) -> tuple[float, bool]:
    """Devolve a alíquota de ITBI para (cidade, UF).

    Retorna ``(alíquota, exact_match)`` — o flag indica se a cidade estava
    na tabela (True) ou se caímos no default (False). Útil para o UI mostrar
    "(estimativa)" quando o município não foi mapeado.
    """
    if not state:
        return ITBI_DEFAULT, False
    key = (_normalize_city(city), state.strip().upper())
    if key in ITBI_BY_CITY:
        return ITBI_BY_CITY[key], True
    return ITBI_DEFAULT, False


def auctioneer_fee_pct_for(
    *,
    declared_pct: float | None,
    has_auctioneer: bool,
    auctioneer_slug: str | None = None,
) -> float:
    """Resolve a comissão do leiloeiro com prioridade:

    1. Valor declarado pelo edital (se o Agente 1 conseguiu extrair).
       Quando o edital diz "0%", respeitamos — mesmo que ``has_auctioneer``
       seja True (caso típico: Caixa Online com auctioneer designado).
    2. ``has_auctioneer=False`` → ``0%``: venda direta sem intermediário.
       Regra do mercado: "no site da Caixa, quando o nome do leiloeiro
       está presente significa que existe comissão".
    3. ``auctioneer_slug`` na lista ``SLUGS_NO_AUCTIONEER_FEE`` → ``0%``
       (venda online da Caixa via slug específico).
    4. Default ``5%`` (Decreto 21.981/1932).
    """
    if declared_pct is not None and declared_pct >= 0:
        return float(declared_pct)
    if not has_auctioneer:
        return AUCTIONEER_FEE_PCT_NO_AUCTIONEER
    if auctioneer_slug and auctioneer_slug.strip().lower() in SLUGS_NO_AUCTIONEER_FEE:
        return AUCTIONEER_FEE_PCT_CAIXA
    return AUCTIONEER_FEE_PCT_DEFAULT


def renovation_cost_for(level: RenovationLevel, area_m2: float | None) -> float:
    """Custo total da reforma = R$/m² × área. ``area_m2 None`` ⇒ 0."""
    if not area_m2 or area_m2 <= 0:
        return 0.0
    return RENOVATION_PER_M2[level] * float(area_m2)


def effective_renovation_area_m2(
    property_row: dict | None,
) -> tuple[float | None, str | None]:
    """Devolve ``(area_m2, source_field)`` a usar no cálculo da reforma.

    Política por ``property_type`` (case-insensitive):

    * ``apartamento``, ``casa``, ``sobrado``, ``comercial``, ``galpao``:
      reforma incide sobre a PARTE CONSTRUÍDA. Prioridade
      ``area_built_m2`` → ``area_useful_m2`` → ``area_total_m2`` (este
      último só como último recurso, com ressalva: para casas o
      ``area_total_m2`` costuma ser o terreno).
    * ``terreno``, ``lote``: NÃO há reforma — é solo, não construção.
      Devolve ``(None, "no_construction")``. O caller deve aplicar
      ``renovation_cost = 0`` independentemente do nível escolhido.
    * ``rural``: pode ter benfeitorias, mas é incomum estarem
      inventariadas. Usa ``area_built_m2`` se houver; senão devolve
      ``(None, "no_construction")``.
    * Tipo desconhecido: tenta ``area_built_m2`` → ``area_useful_m2``
      como melhor palpite (mais conservador que ``area_total_m2``,
      que pode incluir terreno).

    Por que existe (separada de ``effective_target_area_m2`` do
    pricing): o pricing precisa decidir a base de R$/m² de mercado e
    para terrenos isso É a área total. A reforma é semanticamente
    diferente — você não reforma terra, então terreno deve sempre
    cair em ``0``.
    """
    if not property_row:
        return (None, None)

    def _pick(*keys: str) -> tuple[float | None, str | None]:
        for k in keys:
            v = property_row.get(k)
            try:
                fv = float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                continue
            if fv > 0:
                return (fv, k)
        return (None, None)

    ptype = (property_row.get("property_type") or "").strip().lower()

    if ptype in {"terreno", "lote"}:
        return (None, "no_construction")

    if ptype in {"apartamento", "casa", "sobrado", "comercial", "galpao"}:
        return _pick("area_built_m2", "area_useful_m2", "area_total_m2")

    if ptype == "rural":
        picked, source = _pick("area_built_m2", "area_useful_m2")
        return (picked, source if picked is not None else "no_construction")

    # Tipo desconhecido / "outro" — palpite conservador.
    return _pick("area_built_m2", "area_useful_m2")


def other_costs_default_for(occupancy_status: str | None) -> float:
    """Default de "outros custos" baseado no status de ocupação."""
    s = (occupancy_status or "").strip().lower()
    if s in {"desocupado", "vacant", "livre"}:
        return OTHER_COSTS_DEFAULT["vacant"]
    if s in {"ocupado", "occupied"}:
        return OTHER_COSTS_DEFAULT["occupied"]
    return OTHER_COSTS_DEFAULT["unknown"]
