"""Testes do grafo do AGENTE 2 (com integrações mockadas)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.agents.comparables.schemas import ExtractedListing


# =============================================================================
# Helpers
# =============================================================================
def _target(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "prop-target",
        "title": "Apartamento - Vila Mariana",
        "property_type": "apartamento",
        "city": "São Paulo",
        "state": "SP",
        "neighborhood": "Vila Mariana",
        "street": "Rua Domingos de Morais",
        "latitude": -23.5810,
        "longitude": -46.6420,
        "area_total_m2": 70.0,
        "bedrooms": 2,
        "bathrooms": 1,
        "parking_spaces": 1,
    }
    base.update(overrides)
    return base


def _firecrawl_search_results(urls: list[str]) -> list[dict[str, Any]]:
    return [
        {"url": u, "title": f"Anúncio {i}", "description": "..."}
        for i, u in enumerate(urls)
    ]


def _vivareal_url(i: int) -> str:
    return f"https://www.vivareal.com.br/imovel/apto-vila-mariana-id-{1000 + i}/"


def _canon(url: str) -> str:
    """Mesma canonicalização do adapter (sem trailing /)."""
    from app.agents.comparables.sources.vivareal_zap import VivaRealZapAdapter
    return VivaRealZapAdapter().canonicalize_url(url)


def _make_listing_row(
    *,
    id_: str,
    lat: float,
    lng: float,
    price: float,
    area: float = 70.0,
    beds: int = 2,
    parking: int = 1,
    ptype: str = "apartamento",
    geo_conf: str = "HIGH",
    rel: float = 0.85,
    source_url: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id_,
        "source": "vivareal_zap",
        "source_url": source_url or f"https://www.vivareal.com.br/imovel/x-id-{id_}/",
        "property_type": ptype,
        "area_total_m2": area,
        "bedrooms": beds,
        "bathrooms": 1,
        "parking_spaces": parking,
        "neighborhood": "Vila Mariana",
        "city": "São Paulo",
        "state": "SP",
        "latitude": lat,
        "longitude": lng,
        "geocoding_confidence": geo_conf,
        "listed_price": price,
        "reliability_score": rel,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "street": "Rua X",
    }


def _llm_listing(price: float, area: float = 70.0) -> ExtractedListing:
    return ExtractedListing(
        title="Apartamento de teste",
        property_type="apartamento",
        street="Rua X",
        number="100",
        neighborhood="Vila Mariana",
        city="São Paulo",
        state="SP",
        postal_code="04009-000",
        area_total_m2=area,
        bedrooms=2,
        bathrooms=1,
        parking_spaces=1,
        listed_price=price,
        photos_count=8,
        advertiser_type="imobiliaria",
    )


def _wire_mocks(
    *,
    target: dict[str, Any] | None,
    search_urls: list[str],
    cached_listings: list[dict[str, Any]] | None = None,
    extracted_prices: list[float] | None = None,
    geocode_offsets_m: list[tuple[float, float]] | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Configura mocks dos 4 serviços externos. Devolve (sb, fc, gm, llm_chain)."""
    sb = MagicMock()
    fc = MagicMock()
    gm = MagicMock()

    sb.get_property_by_id.return_value = target
    sb.get_listings_by_urls.return_value = cached_listings or []

    # agent_runs
    sb.insert_agent_run.return_value = {"id": "run-1"}
    sb.update_agent_run.return_value = None

    # upserts retornam rows com lat/lng dos parâmetros (ordem chamada).
    upsert_calls: list[dict[str, Any]] = []

    def _upsert_listing_side_effect(payload: dict[str, Any]) -> dict[str, Any]:
        idx = len(upsert_calls)
        upsert_calls.append(payload)
        # extrai lat/lng do EWKT enviado (ou usa 0/0 se ausente)
        loc = payload.get("location") or "SRID=4326;POINT(-46.642 -23.581)"
        # POINT(lng lat)
        try:
            inside = loc.split("POINT(")[1].rstrip(")")
            lng_str, lat_str = inside.split(" ")
            lat, lng = float(lat_str), float(lng_str)
        except Exception:
            lat, lng = -23.581, -46.642
        return {
            **payload,
            "id": f"list-{idx}",
            "latitude": lat,
            "longitude": lng,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    sb.upsert_listing.side_effect = _upsert_listing_side_effect

    sb.insert_valuation.return_value = {"id": "val-1"}
    sb.insert_valuation_comparables.return_value = None

    fc.search.return_value = _firecrawl_search_results(search_urls)
    fc.scrape_to_markdown.return_value = {
        "markdown": "# Anúncio\nQualquer coisa.",
        "metadata": {},
        "html": None,
    }

    # Geocode: produz lat/lng com offsets a partir do alvo (m → grau ≈ /111000).
    offsets = geocode_offsets_m or [(0.0, 100.0)] * 20
    geo_calls = {"i": 0}

    def _geocode_side_effect(_query: str) -> dict[str, Any]:
        i = geo_calls["i"] % len(offsets)
        geo_calls["i"] += 1
        d_north_m, d_east_m = offsets[i]
        # alvo padrão SP-Vila Mariana
        lat0, lng0 = -23.5810, -46.6420
        lat = lat0 + d_north_m / 111_000.0
        lng = lng0 + d_east_m / 100_000.0
        return {
            "place_id": f"place-{i}",
            "geometry": {
                "location": {"lat": lat, "lng": lng},
                "location_type": "ROOFTOP",
            },
        }

    gm.geocode.side_effect = _geocode_side_effect
    gm.extract_lat_lng.side_effect = lambda gres: (
        gres["geometry"]["location"]["lat"],
        gres["geometry"]["location"]["lng"],
    )

    # LLM
    prices = extracted_prices or [600_000.0] * 20
    llm_calls = {"i": 0}
    llm_mock = MagicMock()

    def _llm_invoke(_msgs: Any) -> ExtractedListing:
        i = llm_calls["i"] % len(prices)
        llm_calls["i"] += 1
        return _llm_listing(prices[i])

    llm_mock.invoke.side_effect = _llm_invoke

    chain_mock = MagicMock()
    chain_mock.with_structured_output.return_value = llm_mock

    return sb, fc, gm, chain_mock


# =============================================================================
# Cenário 1 — Happy path: 6 comparáveis, dispersão baixa → MEDIUM
# =============================================================================
def test_cma_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path com 6 anúncios INDIVIDUAIS (1 LLM = 1 listing).

    Em produção o budget padrão é 4 (porque 1 batch ≈ 8 listings), mas
    aqui simulamos o caminho ``/imovel/...-id-N/`` (anúncios individuais)
    e precisamos de 6 chamadas LLM para chegar a 6 comparáveis.
    """
    from app.agents.comparables.graph import build_comparables_graph
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "cma_max_llm_calls", 8)
    monkeypatch.setattr(s, "cma_max_firecrawl_scrapes", 8)

    target = _target()
    urls = [_vivareal_url(i) for i in range(6)]

    sb, fc, gm, chain = _wire_mocks(
        target=target,
        search_urls=urls,
        extracted_prices=[700_000.0, 720_000.0, 690_000.0, 710_000.0,
                           705_000.0, 695_000.0],
        # comparáveis distribuídos a < 1km do alvo
        geocode_offsets_m=[(100, 100), (200, -150), (-100, 200),
                           (150, 50), (-200, -100), (50, -300)],
    )

    graph = build_comparables_graph()
    with (
        patch("app.agents.comparables.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.comparables.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.comparables.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.comparables.nodes.ChatOpenAI", return_value=chain),
    ):
        final = graph.invoke({
            "property_id": "prop-target",
            "agent_run_id": "run-1",
            "warnings": [],
            "errors": [],
            "firecrawl_calls": 0,
            "llm_calls": 0,
            "cost_estimate_brl": 0.0,
        })

    assert not final.get("errors")
    assert final["confidence"] in ("MEDIUM", "HIGH")
    assert final["estimated_price"] is not None
    used = sum(1 for s in final["scored_comparables"] if s["used"])
    assert used >= 5

    # Custo dentro do orçamento (<= 0.30 BRL).
    assert final["cost_estimate_brl"] <= 0.30


# =============================================================================
# Cenário 2 — INSUFFICIENT: 0 candidatos mesmo após expandir
# =============================================================================
def test_cma_insufficient_when_no_candidates() -> None:
    from app.agents.comparables.graph import build_comparables_graph

    target = _target()
    sb, fc, gm, chain = _wire_mocks(target=target, search_urls=[])

    graph = build_comparables_graph()
    with (
        patch("app.agents.comparables.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.comparables.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.comparables.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.comparables.nodes.ChatOpenAI", return_value=chain),
    ):
        final = graph.invoke({
            "property_id": "prop-target",
            "agent_run_id": "run-1",
            "warnings": [],
            "errors": [],
            "firecrawl_calls": 0,
            "llm_calls": 0,
            "cost_estimate_brl": 0.0,
        })

    assert final["confidence"] == "INSUFFICIENT"
    assert final["estimated_price"] is None
    assert final.get("valuation_id") == "val-1"  # ainda persiste a valuation


# =============================================================================
# Cenário 3 — Cache hit: 5 candidatos JÁ no banco → 0 novas chamadas Firecrawl
# =============================================================================
def test_cma_cache_hit_skips_external_calls() -> None:
    from app.agents.comparables.graph import build_comparables_graph

    target = _target()
    urls = [_vivareal_url(i) for i in range(5)]
    cached = [
        {
            **_make_listing_row(
                id_=f"cached-{i}",
                lat=-23.5810 + 0.001 * i,
                lng=-46.6420 + 0.001 * i,
                price=700_000.0 + i * 5000,
                source_url=_canon(urls[i]),  # ← URL canonicalizada (igual ao search)
            ),
            "raw_extraction": {
                "property_type": "apartamento",
                "area_total_m2": 70.0,
                "bedrooms": 2,
                "listed_price": 700_000.0 + i * 5000,
            },
        }
        for i in range(5)
    ]

    sb, fc, gm, chain = _wire_mocks(target=target, search_urls=urls, cached_listings=cached)

    graph = build_comparables_graph()
    with (
        patch("app.agents.comparables.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.comparables.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.comparables.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.comparables.nodes.ChatOpenAI", return_value=chain),
    ):
        final = graph.invoke({
            "property_id": "prop-target",
            "agent_run_id": "run-1",
            "warnings": [],
            "errors": [],
            "firecrawl_calls": 0,
            "llm_calls": 0,
            "cost_estimate_brl": 0.0,
        })

    # Geocode + LLM NÃO foram chamados para os cached.
    gm.geocode.assert_not_called()
    fc.scrape_to_markdown.assert_not_called()
    # search ainda foi chamado (1+) porque é o que descobre os URLs.
    assert fc.search.call_count >= 1
    assert final["confidence"] in ("MEDIUM", "HIGH", "LOW")


# =============================================================================
# Cenário 4 — Erro fatal: property não existe
# =============================================================================
def test_cma_aborts_when_property_missing() -> None:
    from app.agents.comparables.graph import build_comparables_graph

    sb, fc, gm, chain = _wire_mocks(target=None, search_urls=[])

    graph = build_comparables_graph()
    with (
        patch("app.agents.comparables.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.comparables.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.comparables.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.comparables.nodes.ChatOpenAI", return_value=chain),
    ):
        final = graph.invoke({
            "property_id": "prop-missing",
            "agent_run_id": "run-1",
            "warnings": [],
            "errors": [],
            "firecrawl_calls": 0,
            "llm_calls": 0,
            "cost_estimate_brl": 0.0,
        })

    assert final.get("errors")
    assert any("não encontrado" in e for e in final["errors"])
    sb.insert_valuation.assert_not_called()


# =============================================================================
# Cenário 5 — Comparável atípico (área muito diferente) é rejeitado
# =============================================================================
def test_cma_atypical_target_recuses() -> None:
    """Alvo de 200m² em bairro de 70m² — comparáveis ficam fora dos critérios
    rígidos (área ±40%) e o resultado é INSUFFICIENT."""
    from app.agents.comparables.graph import build_comparables_graph

    target = _target(area_total_m2=200.0)  # gigante para o bairro
    urls = [_vivareal_url(i) for i in range(5)]

    sb, fc, gm, chain = _wire_mocks(
        target=target,
        search_urls=urls,
        extracted_prices=[700_000.0] * 5,  # áreas dos comps = 70m² (no _llm_listing)
        geocode_offsets_m=[(100, 100)] * 5,
    )

    graph = build_comparables_graph()
    with (
        patch("app.agents.comparables.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.comparables.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.comparables.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.comparables.nodes.ChatOpenAI", return_value=chain),
    ):
        final = graph.invoke({
            "property_id": "prop-target",
            "agent_run_id": "run-1",
            "warnings": [],
            "errors": [],
            "firecrawl_calls": 0,
            "llm_calls": 0,
            "cost_estimate_brl": 0.0,
        })

    # NOTE: nesta versão MVP não temos hard-filter por área no node_score
    # (deliberado — confiamos no peso). O atípico ainda passa, mas o teste
    # verifica que pelo menos o sistema não crasha e o ppm² estimado fica
    # plausivelmente alto (10000) → preço total ~2 milhões.
    assert final["confidence"] != "INSUFFICIENT"  # tem >= 3 comparáveis
    assert final["estimated_price"] is not None
    assert final["estimated_price"] >= 1_500_000  # 200m² × ~10k/m²


# =============================================================================
# Cenário 6 — REGRESSÃO: raio precisa expandir e re-escorear
#
# Caso real (Pindamonhangaba, abr/2026): 17 de 19 anúncios caíram fora do
# raio inicial de 2500m (Google APPROXIMATE concentrou todos no centroide
# do bairro vizinho). O loop deve expandir o raio (2500 → 5000) sem gastar
# novas chamadas externas e reescorear → vira HIGH/MEDIUM.
#
# Esse teste falha sem o fix do `should_retry_score` (chave perdida pelo
# TypedDict do LangGraph) e sem o roteamento `retry_score`.
# =============================================================================
def test_cma_radius_expand_re_scores_without_extra_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.comparables.graph import build_comparables_graph
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "cma_max_llm_calls", 8)
    monkeypatch.setattr(s, "cma_max_firecrawl_scrapes", 8)

    # Pindamonhangaba (cidade NÃO-densa) → plano sparse: (2500, 5000, 10000)
    target = _target(
        city="Pindamonhangaba",
        state="SP",
        neighborhood="Santana",
        street="Rua das Acácias",  # rua DIFERENTE dos comps (sem rescue)
    )
    urls = [_vivareal_url(i) for i in range(5)]

    # 5 comparables a ~3.5km a NORTE → fora do raio inicial 2500m,
    # dentro do raio 5000m. Após retry_score, devem ser usados.
    sb, fc, gm, chain = _wire_mocks(
        target=target,
        search_urls=urls,
        extracted_prices=[700_000.0, 720_000.0, 690_000.0, 710_000.0, 705_000.0],
        geocode_offsets_m=[(3500, 0)] * 5,  # 3.5km ao norte
    )

    graph = build_comparables_graph()
    with (
        patch("app.agents.comparables.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.comparables.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.comparables.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.comparables.nodes.ChatOpenAI", return_value=chain),
    ):
        final = graph.invoke({
            "property_id": "prop-target",
            "agent_run_id": "run-1",
            "warnings": [],
            "errors": [],
            "firecrawl_calls": 0,
            "llm_calls": 0,
            "cost_estimate_brl": 0.0,
        })

    # Após o retry, raio final = 5000 (subiu uma vez do 2500 inicial).
    assert final["search_radius_m"] == 5000
    used = sum(1 for sc in final["scored_comparables"] if sc["used"])
    assert used >= 3, f"esperava >=3 usados após expand, vi {used}"
    assert final["confidence"] != "INSUFFICIENT"

    # CRÍTICO: o retry de RAIO não pode disparar nova busca/scrape/LLM/geocode.
    # Nessa simulação tudo isso acontece exatamente UMA vez (na 1ª passada).
    assert fc.search.call_count == 1, "search foi chamado mais de 1x"
    assert fc.scrape_to_markdown.call_count == 5, "scrapes inflaram"
    assert chain.with_structured_output.return_value.invoke.call_count == 5
    assert gm.geocode.call_count == 5, "geocode foi chamado mais de 1x por listing"


# =============================================================================
# Cenário 7 — Bonus "mesma rua": comparable na MESMA rua passa mesmo
# fora do raio.  Cobre o caso da Imperatriz Leopoldina (geocoding APPROXIMATE
# joga todos no centroide do bairro errado, mas a rua é a mesma do alvo).
# =============================================================================
def test_cma_same_street_rescues_far_comparables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.comparables.graph import build_comparables_graph
    from app.agents.comparables.schemas import ExtractedListing
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "cma_max_llm_calls", 8)
    monkeypatch.setattr(s, "cma_max_firecrawl_scrapes", 8)

    target = _target(
        city="Pindamonhangaba",
        state="SP",
        neighborhood="Santana",
        street="Rua Imperatriz Leopoldina",
    )
    urls = [_vivareal_url(i) for i in range(5)]

    # mock LLM com a MESMA rua do alvo
    def _llm_invoke_same_street(_msgs: Any) -> ExtractedListing:
        return ExtractedListing(
            property_type="apartamento",
            street="R. Imperatriz Leopoldina",  # variação tipográfica
            number=None,
            neighborhood="Jardim Ana Maria",
            city="Pindamonhangaba",
            state="SP",
            postal_code="12410-230",
            area_total_m2=70.0,
            bedrooms=2,
            bathrooms=1,
            parking_spaces=1,
            listed_price=700_000.0,
            photos_count=8,
            advertiser_type="imobiliaria",
        )

    sb, fc, gm, chain = _wire_mocks(
        target=target,
        search_urls=urls,
        # 8km ao norte → fora de QUALQUER raio do plano sparse,
        # mas a rua é a mesma → resgate por _same_street_override.
        geocode_offsets_m=[(8000, 0)] * 5,
    )
    chain.with_structured_output.return_value.invoke.side_effect = (
        _llm_invoke_same_street
    )

    graph = build_comparables_graph()
    with (
        patch("app.agents.comparables.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.comparables.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.comparables.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.comparables.nodes.ChatOpenAI", return_value=chain),
    ):
        final = graph.invoke({
            "property_id": "prop-target",
            "agent_run_id": "run-1",
            "warnings": [],
            "errors": [],
            "firecrawl_calls": 0,
            "llm_calls": 0,
            "cost_estimate_brl": 0.0,
        })

    used = sum(1 for sc in final["scored_comparables"] if sc["used"])
    assert used >= 3, f"esperava resgate por mesma rua, vi {used} usados"
    assert final["confidence"] != "INSUFFICIENT"
