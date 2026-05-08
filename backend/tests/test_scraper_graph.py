"""Testes de unidade para o grafo do Agente 1 (com integrações mockadas)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.scraper.schemas import ExtractedAddress, ExtractedAuctionData


@pytest.fixture
def fake_extracted() -> ExtractedAuctionData:
    return ExtractedAuctionData(
        auctioneer_slug="zuk",
        auctioneer_lot_id="123",
        title="Apartamento 2 dormitórios — Vila Mariana",
        property_type="apartamento",
        address=ExtractedAddress(
            street="Rua Domingos de Morais",
            number="100",
            neighborhood="Vila Mariana",
            city="São Paulo",
            state="SP",
            postal_code="04009-000",
        ),
        area_total_m2=65.0,
        bedrooms=2,
        bathrooms=1,
        parking_spaces=1,
        appraisal_value=600_000.00,
        minimum_bid_first=600_000.00,
        minimum_bid_second=300_000.00,
    )


@pytest.fixture
def fake_extracted_dirty_neighborhood() -> ExtractedAuctionData:
    """Caso real do bug: bairro com prefixo 'LOTEAMENTO'."""
    return ExtractedAuctionData(
        auctioneer_slug="caixa",
        auctioneer_lot_id="999",
        title="Casa - CEF",
        property_type="casa",
        address=ExtractedAddress(
            street="Rua Imperatriz Leopoldina",
            number="129",
            neighborhood="LOTEAMENTO JARDIM ANA MARIA",
            city="Pindamonhangaba",
            state="SP",
            postal_code="12403-310",
        ),
    )


def _good_validation() -> dict:
    return {
        "verdict": {
            "validationGranularity": "PREMISE",
            "possibleNextAction": "ACCEPT",
        },
        "address": {
            "formattedAddress": "R. Domingos de Morais, 100 - Vila Mariana, São Paulo - SP",
            "addressComponents": [
                {"componentType": "route", "componentName": {"text": "Rua Domingos de Morais"}},
                {"componentType": "street_number", "componentName": {"text": "100"}},
                {"componentType": "sublocality", "componentName": {"text": "Vila Mariana"}},
                {"componentType": "locality", "componentName": {"text": "São Paulo"}},
                {"componentType": "administrative_area_level_1", "componentName": {"text": "SP"}},
                {"componentType": "postal_code", "componentName": {"text": "04009-000"}},
                {"componentType": "country", "componentName": {"text": "BR"}},
            ],
        },
    }


def _bad_validation() -> dict:
    return {
        "verdict": {
            "validationGranularity": "OTHER",
            "possibleNextAction": "FIX",
            "hasUnconfirmedComponents": True,
        },
        "address": {
            "formattedAddress": "LOTEAMENTO - Rua Imperatriz Leopoldina, 129 ...",
            "addressComponents": [],
        },
    }


def _good_geocode(*, lat: float = -23.5505, lng: float = -46.6333) -> dict:
    return {
        "place_id": "ChIJfake",
        "geometry": {
            "location": {"lat": lat, "lng": lng},
            "location_type": "ROOFTOP",
        },
    }


# --------------------------------------------------------------------------- #
# Happy path: validation aprovou, geocoding HIGH, persistência OK
# --------------------------------------------------------------------------- #
def test_scraper_graph_happy_path(fake_extracted: ExtractedAuctionData) -> None:
    from app.agents.scraper.graph import build_scraper_graph

    graph = build_scraper_graph()

    fc = MagicMock()
    fc.scrape_to_markdown.return_value = {"markdown": "# Lote", "metadata": {}}

    gm = MagicMock()
    gm.validate_address.return_value = _good_validation()
    gm.geocode.return_value = _good_geocode()
    gm.extract_lat_lng.return_value = (-23.5505, -46.6333)

    sb = MagicMock()
    sb.get_auctioneer_id_by_slug.return_value = "auc-uuid"
    sb.upsert_property.return_value = {"id": "prop-uuid"}

    llm_mock = MagicMock()
    llm_mock.invoke.return_value = fake_extracted

    chain_mock = MagicMock()
    chain_mock.with_structured_output.return_value = llm_mock

    with (
        patch("app.agents.scraper.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.scraper.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.scraper.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.scraper.nodes.ChatOpenAI", return_value=chain_mock),
    ):
        final = graph.invoke({"url": "https://www.zuk.com.br/leiloes/imoveis/123"})

    assert final["property_id"] == "prop-uuid"
    assert final.get("errors") in (None, [])
    # geocode chamado UMA vez (caminho A apenas)
    assert gm.geocode.call_count == 1
    saved = sb.upsert_property.call_args.args[0]
    assert saved["status"] == "scraped"
    assert saved["geocoding_confidence"] == "HIGH"
    assert "location" in saved


# --------------------------------------------------------------------------- #
# Aborto em erro fatal do Firecrawl (mantido)
# --------------------------------------------------------------------------- #
def test_scraper_graph_aborts_on_firecrawl_error() -> None:
    from app.agents.scraper.graph import build_scraper_graph
    from app.services.firecrawl_service import FirecrawlScrapeError

    graph = build_scraper_graph()

    fc = MagicMock()
    fc.scrape_to_markdown.side_effect = FirecrawlScrapeError("403 forbidden")

    gm = MagicMock()
    sb = MagicMock()

    with (
        patch("app.agents.scraper.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.scraper.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.scraper.nodes.get_supabase_service", return_value=sb),
    ):
        final = graph.invoke({"url": "https://www.zuk.com.br/leiloes/imoveis/999"})

    assert final.get("errors")
    assert any("firecrawl" in e for e in final["errors"])
    sb.upsert_property.assert_not_called()


# --------------------------------------------------------------------------- #
# NOVO: validation rejeitada → fallback por CEP geocoda com sucesso
# --------------------------------------------------------------------------- #
def test_scraper_graph_falls_back_to_postal_code(
    fake_extracted_dirty_neighborhood: ExtractedAuctionData,
) -> None:
    from app.agents.scraper.graph import build_scraper_graph

    graph = build_scraper_graph()

    fc = MagicMock()
    fc.scrape_to_markdown.return_value = {"markdown": "# Lote", "metadata": {}}

    # Address Validation devolve verdict ruim (FIX/OTHER)
    gm = MagicMock()
    gm.validate_address.return_value = _bad_validation()
    # Quando o caminho B (fallback por CEP) chamar geocode, devolve coords corretas
    gm.geocode.return_value = _good_geocode(lat=-22.9241, lng=-45.4630)
    gm.extract_lat_lng.return_value = (-22.9241, -45.4630)

    sb = MagicMock()
    sb.get_auctioneer_id_by_slug.return_value = None
    sb.upsert_property.return_value = {"id": "prop-fallback"}

    llm_mock = MagicMock()
    llm_mock.invoke.return_value = fake_extracted_dirty_neighborhood

    chain_mock = MagicMock()
    chain_mock.with_structured_output.return_value = llm_mock

    with (
        patch("app.agents.scraper.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.scraper.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.scraper.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.scraper.nodes.ChatOpenAI", return_value=chain_mock),
    ):
        final = graph.invoke({"url": "https://venda-imoveis.caixa.gov.br/x"})

    # Caminho A foi pulado (rejected). Apenas o fallback foi chamado.
    assert gm.geocode.call_count == 1
    fallback_query = gm.geocode.call_args.args[0]
    assert "CEP 12403-310" in fallback_query
    assert "Pindamonhangaba" in fallback_query

    # O `validate_address` NÃO recebeu o "LOTEAMENTO" (sanitização funcionou)
    val_kwargs = gm.validate_address.call_args.kwargs
    assert all(
        "LOTEAMENTO" not in line for line in val_kwargs["address_lines"]
    ), val_kwargs["address_lines"]

    saved = sb.upsert_property.call_args.args[0]
    assert saved["status"] == "scraped"
    assert saved["geocoding_confidence"] == "POSTAL_CODE"
    assert "location" in saved
    assert final.get("warnings"), "esperava warning sobre fallback"


# --------------------------------------------------------------------------- #
# NOVO: validation rejeitada + sem CEP → status="geo_unconfirmed", sem location
# --------------------------------------------------------------------------- #
def test_scraper_graph_geo_unconfirmed_when_no_cep() -> None:
    from app.agents.scraper.graph import build_scraper_graph

    graph = build_scraper_graph()

    extracted_no_cep = ExtractedAuctionData(
        auctioneer_slug="zuk",
        title="Imóvel sem CEP",
        address=ExtractedAddress(
            street="Rua Inexistente",
            number="0",
            city="Cidade Imaginária",
            state="SP",
            # sem postal_code
        ),
    )

    fc = MagicMock()
    fc.scrape_to_markdown.return_value = {"markdown": "# x", "metadata": {}}

    gm = MagicMock()
    gm.validate_address.return_value = _bad_validation()
    # geocode não deve nem ser chamado pois não há CEP

    sb = MagicMock()
    sb.get_auctioneer_id_by_slug.return_value = None
    sb.upsert_property.return_value = {"id": "prop-rejected"}

    llm_mock = MagicMock()
    llm_mock.invoke.return_value = extracted_no_cep
    chain_mock = MagicMock()
    chain_mock.with_structured_output.return_value = llm_mock

    with (
        patch("app.agents.scraper.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.scraper.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.scraper.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.scraper.nodes.ChatOpenAI", return_value=chain_mock),
    ):
        final = graph.invoke({"url": "https://example.com/x"})

    gm.geocode.assert_not_called()  # nem caminho A nem B (sem CEP no B)
    saved = sb.upsert_property.call_args.args[0]
    assert saved["status"] == "geo_unconfirmed"
    assert saved["geocoding_confidence"] == "REJECTED"
    assert "location" not in saved
    assert final["property_id"] == "prop-rejected"


# --------------------------------------------------------------------------- #
# NOVO (DF): endereço de Brasília — sanitize_street remove "QUADRA",
# city normalizada como Brasília e ROUTE+APPROXIMATE classifica MEDIUM.
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_extracted_df_quadra() -> ExtractedAuctionData:
    return ExtractedAuctionData(
        auctioneer_slug="caixa",
        auctioneer_lot_id="df-001",
        title="Apartamento Samambaia Norte",
        property_type="apartamento",
        address=ExtractedAddress(
            street="QUADRA QN 407",  # com prefixo redundante
            number="SN",  # sem número
            complement="Apto 315 Bl A",
            neighborhood="Samambaia Norte",
            city="Brasília",
            state="DF",
            postal_code="72321-505",
        ),
    )


def _df_route_validation() -> dict:
    """Verdict típico de DF: validação razoável (ROUTE), não rejeitada."""
    return {
        "verdict": {
            "validationGranularity": "ROUTE",
            "possibleNextAction": "ACCEPT",
        },
        "address": {
            "formattedAddress": "QN 407 - Samambaia, Brasília - DF, 72321-505, Brasil",
            "addressComponents": [
                {"componentType": "route", "componentName": {"text": "QN 407"}},
                {"componentType": "sublocality", "componentName": {"text": "Samambaia"}},
                {"componentType": "locality", "componentName": {"text": "Brasília"}},
                {"componentType": "administrative_area_level_1", "componentName": {"text": "DF"}},
                {"componentType": "postal_code", "componentName": {"text": "72321-505"}},
            ],
        },
    }


def _approximate_geocode() -> dict:
    """Geocoding APPROXIMATE — típico de quadra do DF (não tem rooftop)."""
    return {
        "place_id": "ChIJfakeDF",
        "geometry": {
            "location": {"lat": -15.8697, "lng": -48.0894},
            "location_type": "APPROXIMATE",
        },
    }


def test_scraper_graph_df_route_approximate_classifies_medium(
    fake_extracted_df_quadra: ExtractedAuctionData,
) -> None:
    """DF: ROUTE + APPROXIMATE deve virar MEDIUM (não LOW), e os
    sanitizadores devem limpar a entrada antes de chamar o Google."""
    from app.agents.scraper.graph import build_scraper_graph

    graph = build_scraper_graph()

    fc = MagicMock()
    fc.scrape_to_markdown.return_value = {"markdown": "# DF lote", "metadata": {}}

    gm = MagicMock()
    gm.validate_address.return_value = _df_route_validation()
    gm.geocode.return_value = _approximate_geocode()
    gm.extract_lat_lng.return_value = (-15.8697, -48.0894)

    sb = MagicMock()
    sb.get_auctioneer_id_by_slug.return_value = None
    sb.upsert_property.return_value = {"id": "prop-df"}

    llm_mock = MagicMock()
    llm_mock.invoke.return_value = fake_extracted_df_quadra
    chain_mock = MagicMock()
    chain_mock.with_structured_output.return_value = llm_mock

    with (
        patch("app.agents.scraper.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.scraper.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.scraper.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.scraper.nodes.ChatOpenAI", return_value=chain_mock),
    ):
        final = graph.invoke({"url": "https://venda-imoveis.caixa.gov.br/df/x"})

    assert final.get("errors") in (None, [])

    # 1) sanitize_street: "QUADRA QN 407" → "QN 407"
    val_kwargs = gm.validate_address.call_args.kwargs
    address_lines = val_kwargs["address_lines"]
    assert all("QUADRA" not in line for line in address_lines), address_lines
    assert any("QN 407" in line for line in address_lines), address_lines

    # 2) sanitize_number: "SN" → null  → não vai pra address_lines
    assert all(line.strip() != "SN" for line in address_lines)

    # 3) Não enviamos complement ao Google
    flat = " ".join(address_lines)
    assert "Apto" not in flat and "Bl A" not in flat

    # 4) Caminho A foi usado (validation NÃO rejeitada)
    assert gm.geocode.call_count == 1

    # 5) Confidence: APPROXIMATE + ROUTE → MEDIUM (refinamento DF)
    saved = sb.upsert_property.call_args.args[0]
    assert saved["geocoding_confidence"] == "MEDIUM", saved["geocoding_confidence"]
    assert saved["status"] == "scraped"


def test_scraper_graph_persists_image_url_and_drops_logo(
    fake_extracted: ExtractedAuctionData,
) -> None:
    """O persist node aceita URLs de fotos válidas e descarta logos do
    leiloeiro mesmo se o LLM passar — defesa em profundidade."""
    from app.agents.scraper.graph import build_scraper_graph

    cases = [
        ("https://cdn.zuk.com.br/imovel/123/foto-large.jpg",
         "https://cdn.zuk.com.br/imovel/123/foto-large.jpg"),
        ("https://www.zuk.com.br/static/logo.png", None),
    ]
    for input_url, expected in cases:
        with_image = fake_extracted.model_copy(update={"image_url": input_url})

        graph = build_scraper_graph()
        fc = MagicMock()
        fc.scrape_to_markdown.return_value = {"markdown": "# x", "metadata": {}}
        gm = MagicMock()
        gm.validate_address.return_value = _good_validation()
        gm.geocode.return_value = _good_geocode()
        gm.extract_lat_lng.return_value = (-23.5505, -46.6333)
        sb = MagicMock()
        sb.get_auctioneer_id_by_slug.return_value = "auc-uuid"
        sb.upsert_property.return_value = {"id": "prop-img"}
        llm_mock = MagicMock()
        llm_mock.invoke.return_value = with_image
        chain_mock = MagicMock()
        chain_mock.with_structured_output.return_value = llm_mock

        with (
            patch("app.agents.scraper.nodes.get_firecrawl_service", return_value=fc),
            patch("app.agents.scraper.nodes.get_google_maps_service", return_value=gm),
            patch("app.agents.scraper.nodes.get_supabase_service", return_value=sb),
            patch("app.agents.scraper.nodes.ChatOpenAI", return_value=chain_mock),
        ):
            graph.invoke({"url": "https://zuk.com.br/leiloes/imoveis/img"})

        saved = sb.upsert_property.call_args.args[0]
        # Persist node remove chaves None — então logos/inválidas não chegam
        # a aparecer no payload (defesa em profundidade).
        assert saved.get("image_url") == expected, (
            f"input={input_url} esperado={expected} got={saved.get('image_url')}"
        )


def test_scraper_graph_persists_arrears_and_auctioneer_fee(
    fake_extracted: ExtractedAuctionData,
) -> None:
    """Garante que o persist node propaga os 3 campos novos (alimentos do
    AGENTE 3) para o payload do `upsert_property`."""
    from app.agents.scraper.graph import build_scraper_graph

    # Acrescenta os 3 campos sobre o fixture base.
    fake_extracted = fake_extracted.model_copy(
        update={
            "iptu_arrears": 1_234.56,
            "condo_arrears": 7_890.12,
            "auctioneer_fee_pct": 0.04,
        }
    )

    graph = build_scraper_graph()

    fc = MagicMock()
    fc.scrape_to_markdown.return_value = {"markdown": "# x", "metadata": {}}

    gm = MagicMock()
    gm.validate_address.return_value = _good_validation()
    gm.geocode.return_value = _good_geocode()
    gm.extract_lat_lng.return_value = (-23.5505, -46.6333)

    sb = MagicMock()
    sb.get_auctioneer_id_by_slug.return_value = "auc-uuid"
    sb.upsert_property.return_value = {"id": "prop-arrears"}

    llm_mock = MagicMock()
    llm_mock.invoke.return_value = fake_extracted
    chain_mock = MagicMock()
    chain_mock.with_structured_output.return_value = llm_mock

    with (
        patch("app.agents.scraper.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.scraper.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.scraper.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.scraper.nodes.ChatOpenAI", return_value=chain_mock),
    ):
        graph.invoke({"url": "https://www.zuk.com.br/leiloes/imoveis/arrears"})

    saved = sb.upsert_property.call_args.args[0]
    assert saved["iptu_arrears"] == 1_234.56
    assert saved["condo_arrears"] == 7_890.12
    assert saved["auctioneer_fee_pct"] == 0.04


def test_scraper_graph_approximate_without_route_stays_low(
    fake_extracted: ExtractedAuctionData,
) -> None:
    """Sanity: APPROXIMATE em granularidade que NÃO é ROUTE/BLOCK
    continua sendo LOW (sem regressão)."""
    from app.agents.scraper.graph import build_scraper_graph

    graph = build_scraper_graph()

    fc = MagicMock()
    fc.scrape_to_markdown.return_value = {"markdown": "# x", "metadata": {}}

    # PREMISE granularity (não-ROUTE) + APPROXIMATE geocoding → LOW
    gm = MagicMock()
    gm.validate_address.return_value = _good_validation()  # PREMISE
    gm.geocode.return_value = _approximate_geocode()
    gm.extract_lat_lng.return_value = (-23.5505, -46.6333)

    sb = MagicMock()
    sb.get_auctioneer_id_by_slug.return_value = "auc-uuid"
    sb.upsert_property.return_value = {"id": "prop-low"}

    llm_mock = MagicMock()
    llm_mock.invoke.return_value = fake_extracted
    chain_mock = MagicMock()
    chain_mock.with_structured_output.return_value = llm_mock

    with (
        patch("app.agents.scraper.nodes.get_firecrawl_service", return_value=fc),
        patch("app.agents.scraper.nodes.get_google_maps_service", return_value=gm),
        patch("app.agents.scraper.nodes.get_supabase_service", return_value=sb),
        patch("app.agents.scraper.nodes.ChatOpenAI", return_value=chain_mock),
    ):
        graph.invoke({"url": "https://www.zuk.com.br/leiloes/imoveis/123"})

    saved = sb.upsert_property.call_args.args[0]
    assert saved["geocoding_confidence"] == "LOW"
