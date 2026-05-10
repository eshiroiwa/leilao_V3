"""Testes dos helpers internos do `nodes.py` do AGENTE 2.

Cobertura focada em ``_reconcile_listing_urls``: pipeline em três camadas
(LLM-validado → reconcilição via markdown → fallback sintético) que
decide a ``source_url`` final de cada card extraído de uma página de
busca. Garante que o frontend nunca receba um link que aponta de volta
para a lista quando há URLs canônicas disponíveis no markdown.

Esses helpers são privados (prefixo ``_``), mas testá-los unitariamente
nos protege do clássico "LLM alucinou domínio" sem precisar montar o grafo
inteiro com mocks de Firecrawl/OpenAI/Supabase.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from app.agents.comparables.nodes import (
    _reconcile_listing_urls,
    _synthetic_listing_url,
    node_enrich_geo,
)


def _resolve_one(
    *, raw: dict[str, Any], parent_url: str, parent_markdown: str = ""
) -> tuple[str, bool]:
    """Atalho para os testes single-listing (chama o pipeline com 1 card)."""
    out = _reconcile_listing_urls(
        raw_listings=[raw],
        parent_url=parent_url,
        parent_markdown=parent_markdown,
    )
    return out[0]


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
    url, is_real = _resolve_one(raw=raw, parent_url=PARENT_VIVAREAL)

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
    url, is_real = _resolve_one(raw=raw, parent_url=PARENT_ZAP)

    assert is_real is True
    assert url.endswith("-id-2748234907")
    assert "/imovel/" in url


# =============================================================================
# Caso 3 — Fallback: nenhuma URL no raw + markdown vazio
# =============================================================================
def test_resolve_falls_back_when_no_url_and_no_markdown() -> None:
    raw = _raw(source_url=None)
    url, is_real = _resolve_one(raw=raw, parent_url=PARENT_VIVAREAL)

    assert is_real is False
    assert url == _synthetic_listing_url(PARENT_VIVAREAL, 0, raw)
    # Deve ser estável (mesmo hash em re-execução).
    again, _ = _resolve_one(raw=raw, parent_url=PARENT_VIVAREAL)
    assert again == url


# =============================================================================
# Caso 4 — Fallback: URL relativa (sem http) é descartada (markdown vazio
# para forçar fallback determinístico → sintético)
# =============================================================================
def test_resolve_rejects_relative_url() -> None:
    raw = _raw(source_url="/imovel/algum-imovel-id-123/")
    url, is_real = _resolve_one(raw=raw, parent_url=PARENT_VIVAREAL)

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
    url, is_real = _resolve_one(raw=raw, parent_url=PARENT_VIVAREAL)

    assert is_real is False
    assert url.startswith(PARENT_VIVAREAL)


# =============================================================================
# Caso 6 — Domínio totalmente desconhecido é descartado
# =============================================================================
def test_resolve_rejects_unknown_domain() -> None:
    raw = _raw(source_url="https://example.com/qualquer-coisa")
    url, is_real = _resolve_one(raw=raw, parent_url=PARENT_VIVAREAL)

    assert is_real is False
    assert url.startswith(PARENT_VIVAREAL)


# =============================================================================
# Caso 7 — URL de PÁGINA DE BUSCA (não é anúncio individual) → descartada
# =============================================================================
def test_resolve_rejects_search_results_url() -> None:
    """O LLM pode confundir e devolver a própria URL da página de busca.
    `is_listing_url` exige `-id-N` no final, então isso é filtrado."""
    raw = _raw(source_url=PARENT_VIVAREAL)
    url, is_real = _resolve_one(raw=raw, parent_url=PARENT_VIVAREAL)

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
    url, is_real = _resolve_one(raw=raw, parent_url=PARENT_VIVAREAL)

    assert is_real is True
    assert "utm_source" not in url
    assert "?" not in url
    assert url.endswith("-id-2748234907")


# =============================================================================
# Caso 9 — Reconciliação SEMÂNTICA via markdown da parent
# =============================================================================
def test_reconcile_semantic_match_by_area() -> None:
    """LLM falhou em devolver source_url, mas o slug da URL canônica no
    markdown contém ``148m2`` — match semântico exato pega esse link em
    vez de cair no sintético."""
    parent_url = (
        "https://www.zapimoveis.com.br/venda/casas/"
        "pr+maringa++conj-hab-inocente-vl-nv-junior"
    )
    markdown = (
        "Casa 148 m² R$ 379.500\n"
        "[Veja mais](https://www.zapimoveis.com.br/imovel/"
        "venda-casa-2-quartos-conj-hab-inocente-maringa-148m2-id-2773220442/)\n"
        "Casa 92 m² R$ 265.000\n"
        "[Veja mais](https://www.zapimoveis.com.br/imovel/"
        "venda-casa-3-quartos-conj-hab-inocente-maringa-92m2-id-2843134883/)\n"
    )
    raw = _raw(source_url=None, area_total_m2=148.0)

    url, is_real = _resolve_one(
        raw=raw, parent_url=parent_url, parent_markdown=markdown
    )

    assert is_real is True
    assert url.endswith("-id-2773220442")  # bateu pelo "148m2" no slug
    assert "#item=" not in url  # não caiu no sintético


# =============================================================================
# Caso 10 — Reconciliação POSICIONAL: 3 cards sem URL, 3 URLs no markdown
# =============================================================================
def test_reconcile_positional_assigns_canonical_urls_in_order() -> None:
    """Quando o markdown da parent tem URLs canônicas mas o LLM não
    capturou nenhuma, atribui posicional na ordem de aparição."""
    parent_url = (
        "https://www.zapimoveis.com.br/venda/casas/"
        "pr+maringa++conj-hab-inocente-vl-nv-junior"
    )
    markdown = (
        "Casa A R$ 380k\n"
        "https://www.zapimoveis.com.br/imovel/casa-a-id-1111111/\n"
        "Casa B R$ 260k\n"
        "https://www.zapimoveis.com.br/imovel/casa-b-id-2222222/\n"
        "Casa C R$ 550k\n"
        "https://www.zapimoveis.com.br/imovel/casa-c-id-3333333/\n"
    )
    raws = [
        _raw(source_url=None, listed_price=380_000, area_total_m2=148.0),
        _raw(source_url=None, listed_price=260_000, area_total_m2=92.0),
        _raw(source_url=None, listed_price=550_000, area_total_m2=144.0),
    ]

    out = _reconcile_listing_urls(
        raw_listings=raws,
        parent_url=parent_url,
        parent_markdown=markdown,
    )

    assert [r[1] for r in out] == [True, True, True]
    assert out[0][0].endswith("-id-1111111")
    assert out[1][0].endswith("-id-2222222")
    assert out[2][0].endswith("-id-3333333")
    # Nenhum sintético.
    assert all("#item=" not in r[0] for r in out)


# =============================================================================
# Caso 11 — Mistura: alguns LLM-OK, outros precisam reconciliação
# =============================================================================
def test_reconcile_does_not_reuse_url_already_picked_by_llm() -> None:
    """Se o LLM já devolveu uma URL canônica para o card #1, ela NÃO pode
    ser atribuída de novo ao card #2 pela reconcilição posicional."""
    parent_url = (
        "https://www.vivareal.com.br/venda/sp/sao-paulo/zona-sul/santana/"
        "rua-imperatriz/casa_residencial"
    )
    url_a = "https://www.vivareal.com.br/imovel/casa-a-id-1111111/"
    url_b = "https://www.vivareal.com.br/imovel/casa-b-id-2222222/"
    markdown = f"Card 1\n{url_a}\nCard 2\n{url_b}\n"

    raws = [
        _raw(source_url=url_a),  # LLM acertou
        _raw(source_url=None),   # LLM falhou — deve pegar url_b
    ]

    out = _reconcile_listing_urls(
        raw_listings=raws, parent_url=parent_url, parent_markdown=markdown
    )

    assert out[0][0].endswith("-id-1111111")
    assert out[1][0].endswith("-id-2222222")
    assert out[1][1] is True  # canônica, não sintética


# =============================================================================
# Caso 12 — Sem URLs canônicas no markdown → sintético (regressão)
# =============================================================================
def test_reconcile_falls_back_to_synthetic_when_pool_empty() -> None:
    """Se o markdown não tem URLs canônicas (página falhou em renderizar
    os links, por ex.), os cards sem URL caem no fallback sintético."""
    parent_url = (
        "https://www.zapimoveis.com.br/venda/casas/sp+pindamonhangaba"
    )
    markdown = "Casa A 100m² R$ 300.000\nCasa B 80m² R$ 250.000\n"
    raws = [
        _raw(source_url=None, area_total_m2=100.0),
        _raw(source_url=None, area_total_m2=80.0),
    ]

    out = _reconcile_listing_urls(
        raw_listings=raws, parent_url=parent_url, parent_markdown=markdown
    )

    assert all(r[1] is False for r in out)
    assert all("#item=" in r[0] for r in out)
    # Hashes diferentes (idx + área distintos).
    assert out[0][0] != out[1][0]


# =============================================================================
# Caso 13 — Match semântico ambíguo (2 URLs com mesma área) → cai pra
# posicional (mais conservador)
# =============================================================================
def test_reconcile_semantic_skipped_when_area_match_is_ambiguous() -> None:
    """Se há 2 URLs com '148m2' no slug, não dá pra escolher por área —
    delega à reconcilição posicional."""
    parent_url = (
        "https://www.zapimoveis.com.br/venda/casas/sp+sao-paulo+zona-sul"
    )
    url_x = "https://www.zapimoveis.com.br/imovel/casa-x-148m2-id-1111111/"
    url_y = "https://www.zapimoveis.com.br/imovel/casa-y-148m2-id-2222222/"
    markdown = f"Card 1\n{url_x}\nCard 2\n{url_y}\n"

    raws = [
        _raw(source_url=None, area_total_m2=148.0),
        _raw(source_url=None, area_total_m2=148.0),
    ]
    out = _reconcile_listing_urls(
        raw_listings=raws, parent_url=parent_url, parent_markdown=markdown
    )

    # Posicional: card 1 → url_x, card 2 → url_y (em ordem de aparição).
    assert out[0][0].endswith("-id-1111111")
    assert out[1][0].endswith("-id-2222222")


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
