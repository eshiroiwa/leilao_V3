"""Nó DEMOGRAPHICS — população da cidade via Wikipedia/IBGE.

Estratégia em 2 saltos:

1. **Search** com Firecrawl: ``"<cidade> <UF> população wikipedia"``.
2. Lê a primeira URL ``pt.wikipedia.org`` retornada e extrai população
   + ano de referência via LLM com structured output.

Por que Wikipedia e não API direta do IBGE? A API do IBGE Cidades não
expõe um endpoint REST público trivial para "população da cidade X UF Y".
Wikipedia consolida o último Censo + estimativas anuais, e um LLM
compacto (gpt-5-mini) extrai com precisão suficiente.

Confidence:
* HIGH se conseguimos um número e um ano de Wikipedia/IBGE.
* MEDIUM se o ano não foi extraído.
* LOW se nada foi obtido.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents.deep.schemas import DemographicsResult, SourceDocument
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.firecrawl_service import (
    FirecrawlScrapeError,
    FirecrawlService,
)

logger = get_logger(__name__)


class _PopulationExtraction(BaseModel):
    """Esquema do LLM para extração estruturada."""

    population: int | None = Field(
        default=None,
        description="População total da cidade (somente número).",
    )
    year: int | None = Field(
        default=None,
        description=(
            "Ano da estimativa/censo. Use o ano mais recente que a página citar."
        ),
    )


def _is_wikipedia(url: str) -> bool:
    return "pt.wikipedia.org" in url or "ibge.gov.br" in url


async def _scrape(firecrawl: FirecrawlService, url: str) -> dict[str, Any] | None:
    try:
        return await asyncio.to_thread(firecrawl.scrape_to_markdown, url)
    except FirecrawlScrapeError as exc:
        logger.warning("deep.demographics.scrape_failed", url=url, error=str(exc))
        return None


async def fetch_demographics(
    *,
    firecrawl: FirecrawlService,
    city: str,
    state: str,
) -> tuple[DemographicsResult, list[SourceDocument]]:
    """Busca a população da cidade. Retorna ``(resultado, fontes)``."""
    query = f"{city} {state} população wikipedia"
    try:
        results = await asyncio.to_thread(firecrawl.search, query, limit=5)
    except Exception as exc:  # defensivo
        logger.warning("deep.demographics.search_failed", error=str(exc))
        return DemographicsResult(confidence="LOW"), []

    target_url: str | None = None
    for hit in results or []:
        url = hit.get("url")
        if url and _is_wikipedia(url):
            target_url = url
            break
    if not target_url and results:
        target_url = results[0].get("url")

    if not target_url:
        return DemographicsResult(confidence="LOW"), []

    scraped = await _scrape(firecrawl, target_url)
    if not scraped or not scraped.get("markdown"):
        return DemographicsResult(
            confidence="LOW", evidence={"reason": "scrape_vazio"}
        ), []

    markdown = scraped["markdown"]
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_extraction_model,
        api_key=settings.openai_api_key.get_secret_value(),
        temperature=0,
    ).with_structured_output(_PopulationExtraction)

    prompt = (
        "Você está lendo a página da Wikipedia/IBGE sobre uma cidade brasileira. "
        f"A cidade é '{city}/{state}'. Extraia APENAS a população total da CIDADE "
        "(não da região metropolitana, não do estado) e o ano da estimativa/censo. "
        "Se a página não cita explicitamente, retorne null nos dois campos. "
        "Não invente números.\n\n"
        "Conteúdo (truncado em 8 000 caracteres):\n\n" + markdown[:8000]
    )

    try:
        extracted: _PopulationExtraction = await asyncio.to_thread(
            llm.invoke, prompt
        )  # type: ignore[assignment]
    except Exception as exc:
        logger.warning("deep.demographics.llm_failed", error=str(exc))
        return (
            DemographicsResult(
                confidence="LOW", evidence={"reason": "llm_failed"}
            ),
            [
                SourceDocument(
                    url=target_url,
                    title=scraped.get("metadata", {}).get("title"),
                )
            ],
        )

    population = extracted.population
    year = extracted.year

    if population is None:
        confidence = "LOW"
    elif year is None:
        confidence = "MEDIUM"
    else:
        confidence = "HIGH"

    docs = [
        SourceDocument(
            url=target_url,
            title=scraped.get("metadata", {}).get("title"),
            excerpt=markdown[:280],
        )
    ]

    return (
        DemographicsResult(
            city_population=population,
            city_population_year=year,
            source=target_url,
            confidence=confidence,  # type: ignore[arg-type]
            evidence={"query": query, "scraped_url": target_url},
        ),
        docs,
    )
