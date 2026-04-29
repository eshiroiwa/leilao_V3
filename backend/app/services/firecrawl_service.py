"""Wrapper assíncrono em torno do SDK Firecrawl (v4+).

Por padrão extraímos a página em **Markdown limpo**, ideal para alimentar o LLM.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from firecrawl import Firecrawl  # SDK >=4.x

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class FirecrawlScrapeError(RuntimeError):
    """Falha ao raspar a URL com Firecrawl."""


class FirecrawlService:
    """Cliente fino para o Firecrawl, focado no caso de uso 'URL → Markdown'."""

    def __init__(self, api_key: str) -> None:
        self._client = Firecrawl(api_key=api_key)

    def scrape_to_markdown(
        self,
        url: str,
        *,
        only_main_content: bool = True,
        wait_for_ms: int = 1500,
        timeout_ms: int = 30_000,
    ) -> dict[str, Any]:
        """Raspa a URL e retorna ``{"markdown": ..., "metadata": ..., "html": ...}``.

        Levanta :class:`FirecrawlScrapeError` se o Firecrawl não conseguir extrair conteúdo.
        """
        logger.info("firecrawl.scrape.start", url=url)
        try:
            doc = self._client.scrape(
                url,
                formats=["markdown"],
                only_main_content=only_main_content,
                wait_for=wait_for_ms,
                timeout=timeout_ms,
            )
        except Exception as exc:  # SDK pode lançar exceções diversas
            logger.error("firecrawl.scrape.exception", url=url, error=str(exc))
            raise FirecrawlScrapeError(f"Firecrawl falhou: {exc}") from exc

        # SDK v4 retorna um Document (Pydantic). Normalizamos para dict.
        markdown = getattr(doc, "markdown", None) or ""
        if not markdown.strip():
            logger.warning("firecrawl.scrape.empty", url=url)
            raise FirecrawlScrapeError("Firecrawl retornou markdown vazio.")

        metadata: dict[str, Any] = {}
        meta_obj = getattr(doc, "metadata", None)
        if meta_obj is not None:
            metadata = (
                meta_obj.model_dump(exclude_none=True)
                if hasattr(meta_obj, "model_dump")
                else dict(meta_obj)
            )

        logger.info("firecrawl.scrape.ok", url=url, length=len(markdown))
        return {
            "markdown": markdown,
            "metadata": metadata,
            "html": getattr(doc, "html", None),
        }

    # ------------------------------------------------------------------ #
    # Search — usado pelo AGENTE 2 para descobrir anúncios candidatos.
    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        timeout_ms: int = 30_000,
    ) -> list[dict[str, Any]]:
        """Busca web e devolve uma lista de ``{"url","title","description"}``.

        Cada call consome 1 crédito Firecrawl. Erros são logados e devolvem
        lista vazia (busca degradada nunca aborta o pipeline; o caller
        pode tentar a próxima estratégia).
        """
        logger.info("firecrawl.search.start", query=query, limit=limit)
        try:
            res = self._client.search(query, limit=limit, timeout=timeout_ms)
        except Exception as exc:
            logger.error("firecrawl.search.exception", query=query, error=str(exc))
            return []

        # SDK v4: SearchResult Pydantic com .web (lista de SearchResultWeb).
        web = getattr(res, "web", None) or []
        out: list[dict[str, Any]] = []
        for item in web:
            url = getattr(item, "url", None)
            if not url:
                continue
            out.append(
                {
                    "url": url,
                    "title": getattr(item, "title", None),
                    "description": getattr(item, "description", None),
                }
            )
        logger.info("firecrawl.search.ok", query=query, n_results=len(out))
        return out


@lru_cache(maxsize=1)
def get_firecrawl_service() -> FirecrawlService:
    settings = get_settings()
    return FirecrawlService(api_key=settings.firecrawl_api_key.get_secret_value())
