"""Nó PRIOR AUCTION — tentativas anteriores de leilão.

Estratégia pragmática: faz uma busca web com Firecrawl pelo endereço/
matrícula e conta as menções a "1ª praça", "2ª praça", "deserto",
"sem licitantes", "sem proposta", "novo leilão" etc.

Por que isso importa: imóvel que já foi a leilão 2-3 vezes sem sucesso
costuma ter algum problema (matrícula, ônus, ocupação difícil). É um
"smell test" complementar à diligência manual.

Confidence é declaradamente baixo (LOW) porque a contagem por palavras-
chave dá falsos positivos (notícias mencionando "leilão" sem ser do
mesmo imóvel). O score é informativo, nunca decisivo.
"""

from __future__ import annotations

import re

from app.agents.deep.schemas import PriorAuctionResult, SourceDocument
from app.core.logging import get_logger
from app.services.firecrawl_service import FirecrawlScrapeError, FirecrawlService

logger = get_logger(__name__)

# Palavras-chave indicando que um leilão anterior aconteceu / fracassou.
# Lista mantida curta de propósito — adicionar termos genéricos demais
# explode a taxa de falso positivo.
_AUCTION_KEYWORDS = (
    r"\bsem licitantes\b",
    r"\bsem proposta\b",
    r"\bdeserto\b",
    r"\bnovo leilão\b",
    r"\bsegundo leilão\b",
    r"\bsegunda praça\b",
    r"\bredesignaç(ão|oes)\b",
)


def _count_mentions(text: str) -> int:
    text = text.lower()
    total = 0
    for pat in _AUCTION_KEYWORDS:
        total += len(re.findall(pat, text))
    return total


async def fetch_prior_auction_signals(
    *,
    firecrawl: FirecrawlService,
    address_full: str,
    matricula: str | None = None,
) -> tuple[PriorAuctionResult, list[SourceDocument]]:
    """Busca menções a leilões anteriores. Retorna (resultado, fontes lidas)."""
    queries: list[str] = []
    if matricula:
        queries.append(f"matrícula {matricula} leilão")
    queries.append(f'"{address_full}" leilão deserto OR "sem licitantes"')

    docs: list[SourceDocument] = []
    total_count = 0
    pages_consulted = 0

    for q in queries[:2]:
        try:
            results = firecrawl.search(query=q, limit=5)
        except FirecrawlScrapeError as exc:
            logger.warning("deep.prior_auction.search_failed", query=q, error=str(exc))
            continue
        for hit in results or []:
            url = hit.get("url")
            content = hit.get("markdown") or hit.get("description") or ""
            if not url or not content:
                continue
            count = _count_mentions(content)
            if count > 0:
                docs.append(
                    SourceDocument(
                        url=url,
                        title=hit.get("title"),
                        excerpt=content[:280],
                    )
                )
                total_count += count
            pages_consulted += 1

    return (
        PriorAuctionResult(
            count=total_count,
            evidence={
                "pages_consulted": pages_consulted,
                "matched_pages": len(docs),
                "keyword_mention_total": total_count,
                "queries": queries[:2],
                "confidence_note": (
                    "Contagem por palavras-chave; pode haver falso positivo."
                ),
            },
        ),
        docs,
    )
