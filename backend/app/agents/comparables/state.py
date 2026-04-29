"""Estado compartilhado do grafo do AGENTE 2 (LangGraph).

Tudo que precisa fluir entre nodes vive aqui. Quando um node falha de forma
não-fatal, ele anexa em ``warnings`` e o pipeline continua. Erros fatais vão
para ``errors`` e abortamos antes de persistir.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

# Tipos auxiliares para clareza nas assinaturas.
SearchStrategy = Literal["condo", "street", "neighborhood", "radius"]
Confidence = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]


class ComparablesState(TypedDict, total=False):
    # ---------- Entrada ----------
    property_id: str

    # ---------- Carregado do banco ----------
    target: dict[str, Any]
    """Linha de ``properties`` (dict) já com latitude/longitude expandidos."""

    # ---------- Busca ----------
    search_strategy: SearchStrategy
    search_radius_m: int
    search_queries: list[str]
    """Cada string é uma query montada para o source adapter."""

    candidate_urls: list[str]
    """URLs únicas de anúncios candidatos vindas dos motores de busca."""

    # ---------- Coleta / extração ----------
    scraped_listings: list[dict[str, Any]]
    """Para cada candidato:  {"source_url", "markdown", "metadata", "from_cache"}."""

    extracted_listings: list[dict[str, Any]]
    """Para cada listing: payload Pydantic ``ExtractedListing.model_dump()``
    + ``source_url``."""

    enriched_listings: list[dict[str, Any]]
    """Após geocoding/score/persist: linha pronta da tabela ``listings``."""

    # ---------- Scoring ----------
    scored_comparables: list[dict[str, Any]]
    """{"listing_id", "distance_m", "similarity", "reliability",
        "weight", "used", "rejection_reason"}."""

    # ---------- Resultado ----------
    estimated_price: float | None
    price_lower_bound: float | None
    price_upper_bound: float | None
    ppm2_estimated: float | None
    confidence: Confidence

    valuation_id: str
    agent_run_id: str

    # ---------- Auditoria de custo ----------
    firecrawl_calls: int
    llm_calls: int
    cost_estimate_brl: float

    # ---------- Controle do loop de expansão ----------
    # Esses flags são lidos pelo conditional edge `_route_after_check`.
    # Eles PRECISAM existir no TypedDict — o LangGraph descarta chaves
    # não-declaradas no patch retornado pelos nodes (já mordemos esse bug).
    should_retry_score: bool
    """True ⇒ só re-rodar `score_similarity` com o novo `search_radius_m`
    (sem novo I/O em Firecrawl/LLM/Geo).  Setado quando ainda há um raio
    maior na mesma estratégia."""

    should_retry_search: bool
    """True ⇒ refazer `search_listings` em diante (novo Firecrawl).  Setado
    quando trocamos para uma estratégia mais ampla (street → neighborhood)."""

    # ---------- Sinalizações ----------
    warnings: list[str]
    errors: list[str]
