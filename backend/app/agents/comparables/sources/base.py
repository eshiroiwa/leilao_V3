"""Interface comum dos source adapters.

Cada portal implementa :class:`SourceAdapter` com:
  * ``name``                       → slug salvo na coluna ``listings.source``
  * ``is_listing_url(url)``        → reconhece um anúncio (vs. resultado/categoria)
  * ``canonicalize_url(url)``      → remove tracking params, normaliza
  * ``classify(url)``              → tipo da página (listing | search | other)
  * ``extract_external_id(url)``   → id interno do anúncio (para dedupe)
  * ``find_listing_urls_in_markdown(md)`` → fallback determinístico:
    extrai TODAS as URLs canônicas de anúncio individual presentes
    no markdown de uma página de busca, em ordem de aparição. Usado
    quando o LLM falha em capturar a URL específica do card.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Literal
from urllib.parse import urlparse, urlunparse

PageKind = Literal["listing", "search", "other"]


class SourceAdapter(ABC):
    """Interface mínima esperada pelo grafo do AGENTE 2."""

    name: str
    domains: tuple[str, ...]

    # Subclasses devolvem aqui um regex que casa com URLs canônicas de
    # anúncio individual desse portal (ex.: ``/imovel/.../id-N/`` no
    # VivaReal/ZAP). Se ``None``, o fallback determinístico do markdown
    # fica desativado para esse adapter.
    listing_url_pattern: re.Pattern[str] | None = None

    @abstractmethod
    def is_listing_url(self, url: str) -> bool: ...

    @abstractmethod
    def extract_external_id(self, url: str) -> str | None: ...

    def classify(self, url: str) -> PageKind:
        if self.is_listing_url(url):
            return "listing"
        host = urlparse(url).netloc.lower()
        if any(host.endswith(d) for d in self.domains):
            return "search"
        return "other"

    def canonicalize_url(self, url: str) -> str:
        """Remove query string e fragmento (a maioria do tracking mora aí)."""
        parts = urlparse(url)
        cleaned = parts._replace(query="", fragment="")
        return urlunparse(cleaned).rstrip("/")

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host.endswith(d) for d in self.domains)

    def find_listing_urls_in_markdown(self, markdown: str) -> list[str]:
        """Extrai URLs canônicas de anúncios presentes no markdown.

        Retorna a lista ÚNICA preservando a ordem de aparição (quando o
        mesmo anúncio aparece duas vezes no markdown — destaque + grade
        — só a primeira ocorrência fica). É a fonte de verdade para
        reconciliação posicional/semântica quando o LLM devolve um card
        sem ``source_url`` válido.

        Implementação default usa ``listing_url_pattern``; subclasses
        podem sobrescrever se o portal precisar de filtros extras
        (ex.: ChavesNaMão precisa rejeitar ``/para-alugar/``).
        """
        if not markdown or self.listing_url_pattern is None:
            return []
        seen: set[str] = set()
        out: list[str] = []
        for m in self.listing_url_pattern.finditer(markdown):
            raw = m.group(0).rstrip(").,;\"'>")
            if not self.is_listing_url(raw):
                continue
            canonical = self.canonicalize_url(raw)
            if canonical in seen:
                continue
            seen.add(canonical)
            out.append(canonical)
        return out


__all__ = ["SourceAdapter", "PageKind"]
