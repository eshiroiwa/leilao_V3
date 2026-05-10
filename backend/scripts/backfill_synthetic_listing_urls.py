"""Backfill: corrige ``listings.source_url`` que ficaram com URL sintética
(``...#item=hash``) por falha de extração do LLM no batch da página de
busca.

Para cada listing com ``#item=`` na URL:
  1. Calcula a parent URL (URL sem o fragment).
  2. Re-scrapeia a parent via Firecrawl (markdown atualizado).
  3. Extrai TODAS as URLs canônicas via
     ``SourceAdapter.find_listing_urls_in_markdown``.
  4. Tenta reconciliar pelo ``area_total_m2`` do listing — se exatamente
     UMA URL canônica do markdown tem ``{area}m2`` no slug, usa.
  5. Atualiza ``source_url`` no banco (com ``upsert`` para evitar
     conflito caso o canonical já exista).

Casos ambíguos (várias URLs com a mesma área) são logados e DEIXADOS
inalterados — preferimos sintético determinístico do que atribuir
URL incorreta.

Uso::

    python -m scripts.backfill_synthetic_listing_urls            # dry-run
    python -m scripts.backfill_synthetic_listing_urls --commit   # persiste
"""

from __future__ import annotations

import argparse
from urllib.parse import urlparse, urlunparse

from app.agents.comparables.nodes import _slug_contains_area
from app.agents.comparables.sources import find_adapter
from app.services.firecrawl_service import (
    FirecrawlScrapeError,
    get_firecrawl_service,
)
from app.services.supabase_service import get_supabase_service


def _parent_url_of(synthetic_url: str) -> str:
    """Remove o ``#item=hash`` do final, devolvendo a URL pai."""
    parts = urlparse(synthetic_url)
    cleaned = parts._replace(fragment="", query="")
    return urlunparse(cleaned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persiste alterações no banco. Sem isso, apenas relata.",
    )
    args = parser.parse_args()

    sb = get_supabase_service()
    fc = get_firecrawl_service()

    rows = (
        sb._client.table("listings")
        .select("id,source_url,area_total_m2,source")
        .like("source_url", "%#item=%")
        .execute()
        .data
        or []
    )
    print(f"Listings com URL sintética: {len(rows)}")
    if not rows:
        return 0

    # Agrupa por parent URL para amortizar o scrape.
    by_parent: dict[str, list[dict]] = {}
    for r in rows:
        parent = _parent_url_of(r["source_url"])
        by_parent.setdefault(parent, []).append(r)

    print(f"Parent pages distintas: {len(by_parent)}")
    print("─" * 80)

    n_fixed = 0
    n_ambiguous = 0
    n_no_match = 0
    n_scrape_fail = 0

    for parent, listings in by_parent.items():
        print(f"\n→ {parent}")
        print(f"  {len(listings)} listing(s) sintético(s) para reconciliar")

        adapter = find_adapter(parent)
        if adapter is None:
            print("  ⚠ Sem adapter para esse domínio — pulando.")
            continue

        try:
            md = (fc.scrape_to_markdown(parent) or {}).get("markdown") or ""
        except FirecrawlScrapeError as exc:
            print(f"  ⚠ Scrape falhou: {exc}")
            n_scrape_fail += len(listings)
            continue

        canonical = adapter.find_listing_urls_in_markdown(md)
        print(f"  URLs canônicas encontradas no markdown: {len(canonical)}")
        if not canonical:
            n_no_match += len(listings)
            continue

        # Coleta as URLs canônicas que JÁ estão no banco para esses
        # mesmos listings (não queremos pisar em cima delas).
        already_in_db: set[str] = set()
        for url in canonical:
            existing = (
                sb._client.table("listings")
                .select("id")
                .eq("source_url", url)
                .execute()
                .data
            )
            if existing:
                already_in_db.add(url)

        for r in listings:
            area = r.get("area_total_m2")
            cands = [
                u for u in canonical
                if u not in already_in_db and _slug_contains_area(u, area)
            ]
            if len(cands) == 1:
                new_url = cands[0]
                print(f"    ✓ id={r['id'][:8]} area={area} → {new_url[-70:]}")
                if args.commit:
                    sb._client.table("listings").update(
                        {"source_url": new_url}
                    ).eq("id", r["id"]).execute()
                    already_in_db.add(new_url)  # consome do pool
                n_fixed += 1
            elif len(cands) > 1:
                print(
                    f"    ? id={r['id'][:8]} area={area} → AMBÍGUO "
                    f"({len(cands)} matches: {[c[-50:] for c in cands]})"
                )
                n_ambiguous += 1
            else:
                print(
                    f"    ✗ id={r['id'][:8]} area={area} → "
                    "sem URL canônica com essa área no markdown"
                )
                n_no_match += 1

    print("\n" + "─" * 80)
    print("RESUMO:")
    print(f"  Fixed (URL canônica única atribuída): {n_fixed}")
    print(f"  Ambíguos (várias URLs com mesma área): {n_ambiguous}")
    print(f"  Sem match: {n_no_match}")
    print(f"  Scrape falhou: {n_scrape_fail}")
    if not args.commit:
        print("\n⚠ DRY-RUN — nada foi persistido. Use --commit para aplicar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
