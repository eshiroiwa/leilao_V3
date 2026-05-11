"""Schemas Pydantic do AGENTE 3 (Análise de Oportunidade).

Três entidades principais:

* :class:`AnalysisInput` — o que o usuário (UI ou API) envia: tipo de
  pessoa, ROI alvo, nível de reforma, lance, etc. **Nada que dependa
  do imóvel**: o serviço carrega o resto do banco.

* :class:`Scenario` — resultado financeiro de UMA hipótese de preço
  de venda (pessimista/realista/otimista).

* :class:`AnalysisResult` — o pacote completo: 3 cenários + lance máximo
  + parecer + warnings + assumptions snapshotadas.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.opportunity.assumptions import (
    BuyerType,
    RenovationLevel,
    VerdictType,
)


# =============================================================================
# Entrada
# =============================================================================
class AnalysisInput(BaseModel):
    """Inputs do usuário (UI ou API)."""

    model_config = ConfigDict(extra="forbid")

    buyer_type: BuyerType = Field(
        default="PF", description="PF (pessoa física) ou PJ (pessoa jurídica)."
    )
    target_net_roi_pct: Annotated[float, Field(ge=0, le=2.0)] = Field(
        default=0.40,
        description=(
            "ROI líquido alvo (fração, ex.: 0.40 = 40%). Usado para calcular"
            " o lance máximo aceitável."
        ),
    )
    renovation_level: RenovationLevel = Field(
        default="moderate",
        description="Nível da reforma planejada (none/basic/moderate/full/premium).",
    )
    bid_amount: Annotated[float, Field(ge=0)] = Field(
        ...,
        description=(
            "Lance proposto no leilão (BRL). Default sugerido pelo UI ="
            " minimum_bid_first do property."
        ),
    )
    other_costs: Annotated[float, Field(ge=0)] = Field(
        default=0.0,
        description="Outros custos (desocupação, mudança, advogado etc.).",
    )
    iptu_arrears: Annotated[float, Field(ge=0)] = Field(
        default=0.0, description="IPTU em atraso (BRL)."
    )
    condo_arrears: Annotated[float, Field(ge=0)] = Field(
        default=0.0, description="Condomínio em atraso (BRL)."
    )
    holding_months: Annotated[int, Field(ge=1, le=120)] = Field(
        default=12,
        description=(
            "Horizonte planejado de carregamento até a venda, em meses."
            " Usado para anualizar o ROI: holding=12 deixa o annualized"
            " idêntico ao ROI bruto; holding mais longo descobre custo"
            " temporal (e.g. 50% bruto em 24 meses ≈ 22,5% anualizado)."
        ),
    )
    monthly_iptu: Annotated[float, Field(ge=0)] = Field(
        default=0.0,
        description=(
            "IPTU mensal CORRENTE (parcela/12), em BRL. Junto com"
            " ``monthly_condo`` × ``holding_months`` compõe o custo de"
            " carregamento somado ao custo de aquisição (default 0 mantém"
            " comportamento histórico do balisador)."
        ),
    )
    monthly_condo: Annotated[float, Field(ge=0)] = Field(
        default=0.0,
        description=(
            "Condomínio mensal CORRENTE, em BRL. Custo de carregamento"
            " enquanto o imóvel não é revendido."
        ),
    )

    # Override opcionais (raros, mas úteis para casos onde o usuário sabe
    # mais que a tabela — ex.: ITBI numa cidade fora da whitelist).
    itbi_pct_override: float | None = Field(
        default=None, ge=0, le=1, description="Override da alíquota de ITBI (0..1)."
    )
    registration_pct_override: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Override da alíquota de registro (0..1).",
    )
    auctioneer_fee_pct_override: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Override da comissão do leiloeiro (0..1).",
    )
    sale_price_override: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Preço de venda esperado para o cenário REALISTA. Quando informado,"
            " sobrescreve o valor calculado a partir da CMA. Pessimista e"
            " otimista são derivados como ±10% deste valor."
        ),
    )


# =============================================================================
# Resultado por cenário
# =============================================================================
class Scenario(BaseModel):
    """Resultado financeiro para UM preço de venda."""

    model_config = ConfigDict(extra="forbid")

    label: Literal["pessimista", "realista", "otimista"]

    # Receita
    sale_price: float

    # Custos de aquisição (decomposto)
    bid: float
    auctioneer_fee: float
    itbi: float
    registration: float
    iptu_arrears: float
    condo_arrears: float
    renovation_cost: float
    other_costs: float
    # Custo de carregamento: (monthly_iptu + monthly_condo) × holding_months.
    # Default 0 quando o usuário não preenche os campos correspondentes.
    holding_costs: float = 0.0
    total_acquisition_cost: float  # = soma dos itens acima

    # Custo de venda
    realtor_fee: float

    # Lucro e impostos
    gross_profit: float
    income_tax: float
    net_profit: float

    # ROI
    gross_roi_pct: float  # lucro_bruto / total_acquisition_cost
    net_roi_pct: float    # lucro_liquido / total_acquisition_cost
    # ROI ANUALIZADO líquido — net_roi convertido para base anual via
    # (1 + net_roi)^(12/holding_months) − 1. Para holding_months = 12
    # coincide com net_roi_pct.
    annualized_net_roi_pct: float


# =============================================================================
# Snapshot das premissas usadas (para auditoria / reprodutibilidade)
# =============================================================================
class AssumptionsSnapshot(BaseModel):
    """Foto das alíquotas/defaults usadas — snapshotada na análise para que
    rerodar a mesma análise no futuro produza o mesmo número, mesmo se as
    tabelas globais mudarem."""

    model_config = ConfigDict(extra="forbid")

    itbi_pct: float
    itbi_source: Literal["city_table", "default", "override"]
    registration_pct: float
    auctioneer_fee_pct: float
    auctioneer_fee_source: Literal[
        "edital",
        "caixa_zero",
        "no_auctioneer",
        "default",
        "override",
    ]
    realtor_fee_pct: float
    income_tax_pct: float
    income_tax_basis: Literal["gross_profit", "sale_price"]
    renovation_per_m2: float


# =============================================================================
# Pacote final
# =============================================================================
class AnalysisResult(BaseModel):
    """Resultado completo de uma análise de oportunidade."""

    model_config = ConfigDict(extra="forbid")

    # Echo dos inputs (para debug)
    input: AnalysisInput

    # Cenários
    pessimista: Scenario
    realista: Scenario
    otimista: Scenario

    # =================================================================
    # Métricas probabilísticas — combinação ponderada dos 3 cenários
    # =================================================================
    # Pesos default 30/40/30 (P10/P50/P90). Embrião do Monte Carlo da
    # Fase 3 — quando a simulação real entrar, esses campos serão
    # substituídos por médias amostrais e P[loss] virá de contagem direta.
    expected_net_roi_pct: float | None = Field(
        default=None,
        description=(
            "ROI líquido ESPERADO ponderado pelos 3 cenários (P10/P50/P90)."
            " E[ROI] = 0,30·pessimista + 0,40·realista + 0,30·otimista."
        ),
    )
    expected_annualized_net_roi_pct: float | None = Field(
        default=None,
        description=(
            "ROI líquido ANUALIZADO esperado, ponderado pelos 3 cenários."
            " Comparável diretamente com CDI/Selic do ano."
        ),
    )
    prob_loss: float | None = Field(
        default=None,
        description=(
            "Probabilidade APROXIMADA de prejuízo (NP < 0), em fração."
            " Soma os pesos dos cenários cujo net_profit é negativo."
            " Aproximação grosseira — será substituída por Monte Carlo."
        ),
    )

    # Lance máximo p/ atingir o ROI alvo (calculado sobre o cenário REALISTA)
    max_bid_for_target: float | None = Field(
        default=None,
        description=(
            "Maior lance que ainda atinge o `target_net_roi_pct`, considerando"
            " preço de venda do cenário realista. None se inalcançável."
        ),
    )

    # Parecer + alertas
    verdict: VerdictType
    verdict_base: VerdictType = Field(
        ...,
        description=(
            "Verdict antes dos downgrades — apenas baseado no ROI realista."
            " Útil para o UI explicar a diferença entre 'parecer base' e final."
        ),
    )
    verdict_factors: list[str] = Field(
        default_factory=list,
        description=(
            "Fatores que rebaixaram o verdict do `verdict_base` para o final."
            " Ex.: 'Cenário pessimista é deficitário'."
        ),
    )
    warnings: list[str] = Field(default_factory=list)

    # Auditoria
    assumptions: AssumptionsSnapshot
