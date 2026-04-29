"""Interface comum dos source adapters.

Cada portal implementa :class:`SourceAdapter` com:
  * ``name``                       → slug salvo na coluna ``listings.source``
  * ``is_listing_url(url)``        → reconhece um anúncio (vs. resultado/categoria)
  * ``canonicalize_url(url)``      → remove tracking params, normaliza
  * ``classify(url)``              → tipo da página (listing | search | other)
  * ``extract_external_id(url)``   → id interno do anúncio (para dedupe)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal
from urllib.parse import urlparse, urlunparse

PageKind = Literal["listing", "search", "other"]


class SourceAdapter(ABC):
    """Interface mínima esperada pelo grafo do AGENTE 2."""

    name: str
    domains: tuple[str, ...]

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


__all__ = ["SourceAdapter", "PageKind"]
