"""Testes dos helpers internos do `nodes.py` do AGENTE 2.

Cobertura focada em ``_resolve_listing_url``: a decisão entre usar a URL
real extraída pelo LLM (preferida, gera link clicável no frontend) vs.
o fallback `_synthetic_listing_url` (hash determinístico).

Esses helpers são privados (prefixo ``_``), mas testá-los unitariamente
nos protege do clássico "LLM alucinou domínio" sem precisar montar o grafo
inteiro com mocks de Firecrawl/OpenAI/Supabase.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from app.agents.comparables.nodes import (
    _resolve_listing_url,
    _synthetic_listing_url,
    node_enrich_geo,
)


# =============================================================================
# Fixtures simples
# =============================================================================
PARENT_VIVAREAL = (
    "https://www.vivareal.com.br/venda/sp/pindamonhangaba/bairros/santana/"
    "rua-imperatriz-leopoldina/com-area-de-servico"
)
PARENT_ZAP = (
    "https://www.zapimoveis.com.br/venda/apartamentos/sp+pindamonhangaba/"
    "rua-imperatriz-leopoldina"
)


def _raw(**overrides):
    base = {
        "listed_price": 700_000.0,
        "area_total_m2": 70.0,
        "street": "Rua Imperatriz Leopoldina",
        "neighborhood": "Santana",
        "title": "Apto 70m²",
    }
    base.update(overrides)
    return base


# =============================================================================
# Caso 1 — URL real do VivaReal (caminho feliz)
# =============================================================================
def test_resolve_uses_real_vivareal_listing_url() -> None:
    real_url = (
        "https://www.vivareal.com.br/imovel/"
        "apartamento-2-quartos-santana-bairros-pindamonhangaba-com-garagem-"
        "70m2-venda-RS700000-id-2748234907/"
    )
    raw = _raw(source_url=real_url)
    url, is_real = _resolve_listing_url(raw=raw, parent_url=PARENT_VIVAREAL, idx=0)

    assert is_real is True
    # Canonicalizada: sem trailing slash.
    assert url == real_url.rstrip("/")
    # NUNCA é a URL pai (página de busca).
    assert "/venda/sp/" not in url


# =============================================================================
# Caso 2 — URL real do ZAP
# =============================================================================
def test_resolve_uses_real_zap_listing_url() -> None:
    real_url = (
        "https://www.zapimoveis.com.br/imovel/"
        "apartamento-3-dormitorios-vila-mariana-sao-paulo-id-2748234907/"
    )
    raw = _raw(source_url=real_url)
    url, is_real = _resolve_listing_url(raw=raw, parent_url=PARENT_ZAP, idx=0)

    assert is_real is True
    assert url.endswith("-id-2748234907")
    assert "/imovel/" in url


# =============================================================================
# Caso 3 — Fallback: nenhuma URL no raw
# =============================================================================
def test_resolve_falls_back_when_no_url() -> None:
    raw = _raw(source_url=None)
    url, is_real = _resolve_listing_url(raw=raw, parent_url=PARENT_VIVAREAL, idx=2)

    assert is_real is False
    assert url == _synthetic_listing_url(PARENT_VIVAREAL, 2, raw)
    # Deve ser estável (mesmo hash em re-execução).
    again, _ = _resolve_listing_url(raw=raw, parent_url=PARENT_VIVAREAL, idx=2)
    assert again == url


# =============================================================================
# Caso 4 — Fallback: URL relativa (sem http) é descartada
# =============================================================================
def test_resolve_rejects_relative_url() -> None:
    raw = _raw(source_url="/imovel/algum-imovel-id-123/")
    url, is_real = _resolve_listing_url(raw=raw, parent_url=PARENT_VIVAREAL, idx=0)

    assert is_real is False
    assert url.startswith(PARENT_VIVAREAL)


# =============================================================================
# Caso 5 — Anti-alucinação: domínio cruzado é descartado
# =============================================================================
def test_resolve_rejects_cross_domain_hallucination() -> None:
    """LLM às vezes inventa link do ZAP quando estávamos no VivaReal — bloquear."""
    cross_url = (
        "https://www.zapimoveis.com.br/imovel/apartamento-id-9999999/"
    )
    raw = _raw(source_url=cross_url)
    url, is_real = _resolve_listing_url(raw=raw, parent_url=PARENT_VIVAREAL, idx=0)

    assert is_real is False
    assert url.startswith(PARENT_VIVAREAL)


# =============================================================================
# Caso 6 — Domínio totalmente desconhecido é descartado
# =============================================================================
def test_resolve_rejects_unknown_domain() -> None:
    raw = _raw(source_url="https://example.com/qualquer-coisa")
    url, is_real = _resolve_listing_url(raw=raw, parent_url=PARENT_VIVAREAL, idx=0)

    assert is_real is False
    assert url.startswith(PARENT_VIVAREAL)


# =============================================================================
# Caso 7 — URL de PÁGINA DE BUSCA (não é anúncio individual) → descartada
# =============================================================================
def test_resolve_rejects_search_results_url() -> None:
    """O LLM pode confundir e devolver a própria URL da página de busca.
    `is_listing_url` exige `-id-N` no final, então isso é filtrado."""
    raw = _raw(source_url=PARENT_VIVAREAL)
    url, is_real = _resolve_listing_url(raw=raw, parent_url=PARENT_VIVAREAL, idx=0)

    assert is_real is False
    # Caiu para o synthetic (que usa parent + #item=hash).
    assert "#item=" in url


# =============================================================================
# Caso 8 — Tracking params são removidos (canonicalização)
# =============================================================================
def test_resolve_strips_tracking_params() -> None:
    real_url = (
        "https://www.vivareal.com.br/imovel/apartamento-id-2748234907/"
        "?utm_source=google&utm_campaign=teste"
    )
    raw = _raw(source_url=real_url)
    url, is_real = _resolve_listing_url(raw=raw, parent_url=PARENT_VIVAREAL, idx=0)

    assert is_real is True
    assert "utm_source" not in url
    assert "?" not in url
    assert url.endswith("-id-2748234907")


# =============================================================================
# REGRESSÃO — O mesmo anúncio em 2 páginas de busca diferentes resulta no
# MESMO listing.id no banco (upsert por source_url). O `node_enrich_geo`
# precisa deduplicar por id ANTES do score/persist, senão a PK composta de
# `valuation_comparables (valuation_id, listing_id)` quebra com 23505.
# =============================================================================
def test_enrich_geo_dedups_listings_pointing_to_same_db_row() -> None:
    real_url = "https://www.vivareal.com.br/imovel/apartamento-2q-id-12345/"

    # Dois entries extraídos (de páginas de busca diferentes) com
    # source_url DIFERENTES, mas o `upsert_listing` resolve para a MESMA
    # row no banco. Caso real: o mesmo anúncio aparece em
    # /bairros/santana/ e /bairros/santana/com-area-de-servico/.
    extracted = [
        {
            "source_url": real_url,
            "from_cache": False,
            "raw": {
                "property_type": "apartamento",
                "street": "Rua X",
                "neighborhood": "Santana",
                "city": "Pindamonhangaba",
                "state": "SP",
                "listed_price": 700_000.0,
                "area_total_m2": 70.0,
            },
        },
        {
            "source_url": real_url,
            "from_cache": False,
            "raw": {
                "property_type": "apartamento",
                "street": "Rua X",
                "neighborhood": "Santana",
                "city": "Pindamonhangaba",
                "state": "SP",
                "listed_price": 700_000.0,
                "area_total_m2": 70.0,
            },
        },
    ]

    state: dict[str, Any] = {
        "extracted_listings": extracted,
        "scraped_listings": [],
        "warnings": [],
    }

    sb = MagicMock()
    gm = MagicMock()

    # Upsert idempotente: mesma source_url ⇒ MESMO id devolvido.
    by_url: dict[str, dict[str, Any]] = {}

    def _upsert(payload: dict[str, Any]) -> dict[str, Any]:
        src = payload["source_url"]
        if src not in by_url:
            by_url[src] = {
                **payload,
                "id": f"list-{len(by_url)}",
                "latitude": -23.0,
                "longitude": -46.0,
            }
        return by_url[src]

    sb.upsert_listing.side_effect = _upsert
    gm.geocode.return_value = {
        "geometry": {
            "location": {"lat": -23.0, "lng": -46.0},
            "location_type": "ROOFTOP",
        },
    }
    gm.extract_lat_lng.side_effect = lambda g: (
        g["geometry"]["location"]["lat"],
        g["geometry"]["location"]["lng"],
    )

    with (
        patch("app.agents.comparables.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.comparables.nodes.get_google_maps_service", return_value=gm),
    ):
        result = node_enrich_geo(state)

    enriched = result["enriched_listings"]
    # 2 entries entraram → 1 deve sair (mesmo listing.id).
    assert len(enriched) == 1, (
        f"esperava deduplicar para 1 listing, vi {len(enriched)}: "
        f"{[r['id'] for r in enriched]}"
    )
    assert enriched[0]["id"] == "list-0"
    # Upsert no Supabase ainda foi chamado 2x (cada extracted entry uma vez)
    # — a dedup acontece em memória DEPOIS, mantendo a primeira ocorrência.
    assert sb.upsert_listing.call_count == 2
