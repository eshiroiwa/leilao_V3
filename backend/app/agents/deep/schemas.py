"""Schemas Pydantic do AGENTE 4 (Deep Analysis).

Cada dimensão tem seu sub-resultado isolado, com uma trinca padronizada:

    score        : 1..5 (None quando indeterminado)
    confidence   : HIGH / MEDIUM / LOW (sempre presente)
    evidence     : dict livre com os números brutos que originaram o score
    sources      : list[SourceDocument] (transparência)

A confiabilidade é levada a sério: um score baixo de confidence aparece
na UI como badge cinza e *não* é usado para nada que não seja informativo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Enums / aliases
# =============================================================================
DeepAnalysisStatus = Literal["pending", "running", "completed", "failed"]
"""Estados do workflow assíncrono persistidos em ``deep_analyses.status``."""

Confidence = Literal["HIGH", "MEDIUM", "LOW"]


class SourceDocument(BaseModel):
    """Documento consultado durante o pipeline (URL + título + trecho)."""

    url: str
    title: str | None = None
    excerpt: str | None = None
    scraped_at: datetime | None = None


# =============================================================================
# Sub-resultados por dimensão
# =============================================================================
class DemographicsResult(BaseModel):
    """População da cidade (bairro raramente disponível em fonte estruturada)."""

    city_population: int | None = None
    city_population_year: int | None = None
    source: str | None = None  # url
    confidence: Confidence = "LOW"
    evidence: dict[str, Any] = Field(default_factory=dict)


class LiquidityResult(BaseModel):
    """Score combinado de liquidez (DOM médio + n listings + população)."""

    score: int | None = Field(default=None, ge=1, le=5)
    confidence: Confidence = "LOW"
    evidence: dict[str, Any] = Field(default_factory=dict)
    listings_per_km2: float | None = Field(
        default=None,
        description=(
            "Densidade de anúncios no raio de busca de vizinhos — proxy de"
            " adensamento populacional e dinamismo do entorno. Calculado"
            " como n_listings / (π · raio_km²)."
        ),
    )


class OutlierResult(BaseModel):
    """O imóvel é atípico para o bairro?"""

    is_outlier_size: bool = False
    is_outlier_price: bool = False
    size_zscore: float | None = None
    price_zscore: float | None = None
    n_neighbors: int = 0
    evidence: dict[str, Any] = Field(default_factory=dict)


class FlippingResult(BaseModel):
    """Há teto de preço que justifique investir em reforma para flipping?"""

    neighborhood_price_max: float | None = None
    neighborhood_price_p90: float | None = None
    neighborhood_ppm2_p90: float | None = None
    score: int | None = Field(default=None, ge=1, le=5)
    evidence: dict[str, Any] = Field(default_factory=dict)


class PriceTrendResult(BaseModel):
    """Tendência de preço dos listings nos últimos 12 meses (proxy)."""

    trend_pct_12m: float | None = None
    confidence: Confidence = "LOW"
    evidence: dict[str, Any] = Field(default_factory=dict)


class AmenitiesResult(BaseModel):
    """Distância (em metros) à amenidade mais próxima de cada categoria."""

    nearest_metro_m: int | None = None
    nearest_school_m: int | None = None
    nearest_hospital_m: int | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class UrbanRiskItem(BaseModel):
    """Um risco urbano localizado (enchente, ZEIS, área de risco etc.)."""

    type: str  # "enchente" | "deslizamento" | "zeis" | ...
    summary: str
    confidence: Confidence = "LOW"
    source_url: str | None = None


class UrbanRisksResult(BaseModel):
    items: list[UrbanRiskItem] = Field(default_factory=list)


class PriorAuctionResult(BaseModel):
    """Já apareceu em leilões anteriores? Quantas vezes?"""

    count: int | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Classe do bairro + bairros concorrentes
# =============================================================================
NeighborhoodTier = Literal["A", "B", "C", "D"]
NeighborhoodTierLabel = Literal["premium", "médio-alto", "médio", "popular"]


class NeighborhoodCompetitor(BaseModel):
    """Bairro vizinho com ppm² semelhante ao bairro-alvo.

    ``distance_km`` é a distância entre o centróide dos listings deste bairro
    e o centróide do bairro-alvo, em km."""

    name: str
    distance_km: float
    ppm2_median: float
    n_listings: int


class NeighborhoodClassResult(BaseModel):
    """Classifica o bairro-alvo em uma classe A/B/C/D pela razão entre o
    ppm² mediano dos listings do bairro e o ppm² da cidade (preferencialmente
    FipeZAP; cai para mediana global dos vizinhos quando ausente). Inclui
    até 3 bairros concorrentes geograficamente próximos com ppm² semelhante,
    para que o usuário tenha sugestões diretas de onde buscar imóveis equivalentes.
    """

    model_config = ConfigDict(extra="forbid")

    tier: NeighborhoodTier | None = None
    tier_label: NeighborhoodTierLabel | None = None
    target_ppm2_median: float | None = None
    city_ppm2_brl: float | None = None
    ratio: float | None = None
    competing_neighborhoods: list[NeighborhoodCompetitor] = Field(default_factory=list)
    confidence: Confidence = "LOW"
    evidence: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Input / Output do pipeline
# =============================================================================
NeighborhoodPattern = Literal["uniforme", "misto", "precario"]
"""Padrão construtivo predominante da quadra (inferido por Street View + aérea)."""

PropertyVsNeighbors = Literal["acima", "igual", "abaixo"]
"""O imóvel-alvo comparado aos vizinhos imediatos."""

SuggestedRenovationLevel = Literal[
    "none", "cosmetic", "light", "basic", "moderate", "full", "premium"
]
"""Sugestão de nível de reforma — espelha ``opportunity.RenovationLevel``."""


class ConditionAssessmentResult(BaseModel):
    """Avaliação visual do ENTORNO via Vision LLM sobre Street View + aérea.

    Substitui o antigo modelo de "fotos do edital" — agora o Vision olha
    um pacote geocodificado (4 Street Views + 1 vista aérea + opcionalmente
    a foto do edital) e devolve sinais sobre o entorno: padrão do bairro,
    comparação com vizinhos, presença de piscinas, sugestão de reforma e
    risk flags ambientais. NÃO sobrescreve o ``renovation_level`` do
    Agente 3 — só informa.
    """

    model_config = ConfigDict(extra="forbid")

    neighborhood_pattern: NeighborhoodPattern | None = None
    property_vs_neighbors: PropertyVsNeighbors | None = None
    pool_observed_nearby: bool | None = None
    suggested_renovation_level: SuggestedRenovationLevel | None = None
    risk_flags: list[str] = Field(default_factory=list, max_length=10)
    image_urls: list[str] = Field(default_factory=list)
    """URLs públicas (Supabase Storage) das imagens capturadas, em ordem.
    Cada URL termina em ``{slot}.jpg`` (aerial/sv_front/sv_left/sv_right/
    sv_back/listing) — frontend infere a legenda a partir do path."""
    notes: str | None = Field(default=None, max_length=600)
    confidence: Confidence = "LOW"
    cost_estimate_usd: float | None = None


class DeepAnalysisInput(BaseModel):
    property_id: str
    opportunity_analysis_id: str | None = None
    force_refresh: bool = False


class DeepAnalysisResult(BaseModel):
    """Resultado consolidado — espelha 1-pra-1 a row em ``deep_analyses``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    property_id: str
    opportunity_analysis_id: str | None = None

    status: DeepAnalysisStatus
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None

    # Sub-resultados
    demographics: DemographicsResult | None = None
    liquidity: LiquidityResult | None = None
    outlier: OutlierResult | None = None
    flipping: FlippingResult | None = None
    price_trend: PriceTrendResult | None = None
    amenities: AmenitiesResult | None = None
    urban_risks: UrbanRisksResult | None = None
    prior_auction: PriorAuctionResult | None = None
    condition_assessment: ConditionAssessmentResult | None = None
    neighborhood_class: NeighborhoodClassResult | None = None

    # Síntese
    overall_score: int | None = Field(default=None, ge=1, le=5)
    summary_text: str | None = None
    red_flags: list[str] = Field(default_factory=list)
    green_flags: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    # Auditoria
    source_documents: list[SourceDocument] = Field(default_factory=list)
    cost_estimate_usd: float | None = None
    firecrawl_calls: int = 0
    llm_calls: int = 0

    created_at: datetime | None = None


# =============================================================================
# Síntese (estruturado para o LLM)
# =============================================================================
class SynthesisOutput(BaseModel):
    """Saída estruturada do nó ``synthesize`` (LLM com structured output)."""

    overall_score: int = Field(ge=1, le=5)
    summary_text: str = Field(max_length=1200)
    red_flags: list[str] = Field(default_factory=list, max_length=10)
    green_flags: list[str] = Field(default_factory=list, max_length=10)
    recommendations: list[str] = Field(default_factory=list, max_length=10)
