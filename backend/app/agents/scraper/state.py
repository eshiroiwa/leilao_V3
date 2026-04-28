"""State do grafo do Agente 1 (LangGraph)."""

from __future__ import annotations

from typing import Any, TypedDict

from app.agents.scraper.schemas import ExtractedAuctionData


class ScraperState(TypedDict, total=False):
    """Estado compartilhado entre os nós do grafo.

    LangGraph permite atualizar o state de forma incremental — cada nó retorna
    apenas as chaves que deseja sobrescrever.
    """

    # ---- Input ----
    url: str

    # ---- Firecrawl ----
    raw_markdown: str
    page_metadata: dict[str, Any]

    # ---- LLM ----
    extracted: ExtractedAuctionData

    # ---- Google Maps ----
    address_validation: dict[str, Any]
    geocode_result: dict[str, Any]
    latitude: float
    longitude: float
    google_place_id: str
    # HIGH         — geocoded em PREMISE (rooftop), validation aprovou
    # MEDIUM       — geocoded com tipo intermediário
    # LOW          — geocoded em APPROXIMATE (não confiável p/ análise espacial)
    # POSTAL_CODE  — fallback: geocodado apenas pelo CEP+cidade+UF
    # REJECTED     — Address Validation pediu FIX e nem o fallback resolveu;
    #                 NÃO persistimos `location` neste caso
    geocoding_confidence: str
    normalized_address: dict[str, Any]
    # Sinaliza que o Address Validation desaconselhou usar o `formatted`
    # devolvido (verdict.possibleNextAction == "FIX" ou
    # validationGranularity == "OTHER"). O nó `geocode` então tenta o
    # fallback por CEP em vez do geocoding direto.
    validation_rejected: bool
    # Granularidade do Address Validation (PREMISE / ROUTE / OTHER / SUB_PREMISE…),
    # usada pelo node_geocode para refinar a classificação final de confidence.
    # Ex.: ROUTE + APPROXIMATE = MEDIUM (precisão de quadra é o esperado em DF),
    # não LOW.
    validation_granularity: str

    # ---- Persistência ----
    property_id: str
    saved_property: dict[str, Any]

    # ---- Auditoria ----
    errors: list[str]
    warnings: list[str]
