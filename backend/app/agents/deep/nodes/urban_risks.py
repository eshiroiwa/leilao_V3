"""Nó URBAN_RISKS — riscos urbanos (enchente, ZEIS, área de risco).

Sinaliza, em tom *informativo*, riscos urbanos típicos do bairro:
enchentes, deslizamentos, áreas de risco da Defesa Civil, ZEIS (Zonas
Especiais de Interesse Social — podem dificultar revenda).

Implementação honesta:

* Faz UMA busca Firecrawl: ``"<bairro> <cidade> <UF> enchente OR
  deslizamento OR área de risco"``.
* Lê até 3 resultados; LLM pequeno (gpt-5-mini) extrai uma lista
  estruturada de ``UrbanRiskItem`` (cada um com ``type``, ``summary``,
  ``confidence``, ``source_url``).
* Confidence é declaradamente LOW/MEDIUM — nunca HIGH. A lógica é "é
  uma orientação para diligência", não dado oficial.

Se não houver bairro (cidade muito pequena) → busca por cidade.
"""

from __future__ import annotations

import asyncio

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents.deep.schemas import (
    SourceDocument,
    UrbanRiskItem,
    UrbanRisksResult,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.firecrawl_service import (
    FirecrawlScrapeError,
    FirecrawlService,
)

logger = get_logger(__name__)

MAX_PAGES_TO_READ = 3


class _UrbanRisksLLMOutput(BaseModel):
    risks: list[UrbanRiskItem] = Field(default_factory=list, max_length=8)


async def _scrape(firecrawl: FirecrawlService, url: str) -> str | None:
    try:
        doc = await asyncio.to_thread(firecrawl.scrape_to_markdown, url)
    except FirecrawlScrapeError as exc:
        logger.warning("deep.risks.scrape_failed", url=url, error=str(exc))
        return None
    return doc.get("markdown") or None


async def fetch_urban_risks(
    *,
    firecrawl: FirecrawlService,
    neighborhood: str | None,
    city: str,
    state: str,
) -> tuple[UrbanRisksResult, list[SourceDocument]]:
    where = f"{neighborhood} {city} {state}" if neighborhood else f"{city} {state}"
    query = f'"{where}" enchente OR deslizamento OR "área de risco" OR ZEIS'

    try:
        results = await asyncio.to_thread(firecrawl.search, query, limit=5)
    except Exception as exc:
        logger.warning("deep.risks.search_failed", error=str(exc))
        return UrbanRisksResult(), []

    pages: list[tuple[str, str]] = []
    docs: list[SourceDocument] = []
    for hit in (results or [])[:MAX_PAGES_TO_READ]:
        url = hit.get("url")
        if not url:
            continue
        markdown = await _scrape(firecrawl, url)
        if not markdown:
            continue
        pages.append((url, markdown[:5000]))
        docs.append(
            SourceDocument(
                url=url,
                title=hit.get("title"),
                excerpt=markdown[:280],
            )
        )

    if not pages:
        return UrbanRisksResult(), docs

    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_extraction_model,
        api_key=settings.openai_api_key.get_secret_value(),
        temperature=0,
    ).with_structured_output(_UrbanRisksLLMOutput)

    consolidated = "\n\n---\n\n".join(
        f"FONTE: {url}\n\n{md}" for (url, md) in pages
    )
    prompt = (
        f"Você está investigando riscos urbanos do local '{where}'. "
        "Leia o conteúdo abaixo e extraia uma lista de RISCOS REAIS e "
        "específicos do local (não risco genérico do estado/país).\n\n"
        "Para cada risco encontrado, retorne:\n"
        "  - type: uma das palavras: 'enchente', 'deslizamento', 'area_risco', "
        "    'zeis', 'outro'.\n"
        "  - summary: 1-2 frases descrevendo o risco e onde foi mencionado.\n"
        "  - confidence: 'LOW' (só uma menção fraca), 'MEDIUM' (citação clara), "
        "    'HIGH' (mapa/decreto oficial).\n"
        "  - source_url: a URL exata da fonte que afirma o risco.\n\n"
        "Se NÃO houver risco específico, retorne lista vazia.\n"
        "NÃO invente. Se duvidar, marque LOW.\n\n"
        "CONTEÚDO:\n\n" + consolidated
    )

    try:
        out: _UrbanRisksLLMOutput = await asyncio.to_thread(llm.invoke, prompt)  # type: ignore[assignment]
    except Exception as exc:
        logger.warning("deep.risks.llm_failed", error=str(exc))
        return UrbanRisksResult(), docs

    return UrbanRisksResult(items=out.risks), docs
