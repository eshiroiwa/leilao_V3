"""Política de cache de listings.

A "tabela de cache" é a própria tabela ``listings``: se já existe um registro
com ``source_url == X`` e ``scraped_at`` dentro do TTL, NÃO precisamos chamar
o Firecrawl/LLM de novo. O caller usa ``filter_uncached_urls`` para descobrir
o subconjunto que ainda precisa ser fetched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def is_listing_fresh(scraped_at: datetime | str | None, ttl_days: int) -> bool:
    """True se a data está dentro de ``ttl_days`` a partir de agora.

    Aceita ``datetime`` aware/naive ou string ISO 8601.
    """
    if scraped_at is None:
        return False
    if isinstance(scraped_at, str):
        try:
            scraped_at = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    if scraped_at.tzinfo is None:
        scraped_at = scraped_at.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    return scraped_at >= cutoff


def split_cached_vs_fresh(
    candidates: list[str],
    cached_listings: list[dict[str, Any]],
    ttl_days: int,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Separa as URLs candidatas em (cached, ainda_a_buscar).

    Args:
        candidates: URLs vindas do search.
        cached_listings: registros pré-existentes em ``listings`` filtrados
            pelo caller a partir de ``source_url IN (...)``.
        ttl_days: TTL em dias.

    Returns:
        ``(by_url_cache, fresh_to_fetch)``: o primeiro é dict
        ``url -> listing_row`` para os que vamos reaproveitar; o segundo
        é a lista de URLs que ainda devem ir ao Firecrawl.
    """
    by_url = {row["source_url"]: row for row in cached_listings}
    cached_used: dict[str, dict[str, Any]] = {}
    fresh: list[str] = []
    for url in candidates:
        row = by_url.get(url)
        if row and is_listing_fresh(row.get("scraped_at"), ttl_days):
            cached_used[url] = row
        else:
            fresh.append(url)
    return cached_used, fresh


__all__ = ["is_listing_fresh", "split_cached_vs_fresh"]
