"""Testes do adapter ChavesNaMão e do registry centralizado."""

from __future__ import annotations

import pytest

from app.agents.comparables.sources import all_domains, find_adapter
from app.agents.comparables.sources.chavesnamao import ChavesNaMaoAdapter
from app.agents.comparables.sources.vivareal_zap import VivaRealZapAdapter

ADAPTER = ChavesNaMaoAdapter()


# =============================================================================
# is_listing_url — só URLs de anúncio individual de VENDA terminadas em /id-N/
# =============================================================================
@pytest.mark.parametrize(
    "url",
    [
        "https://www.chavesnamao.com.br/imovel/apartamento-a-venda-2-quartos-com-garagem-sp-pindamonhangaba-centro-RS395000/id-31871873/",
        "https://www.chavesnamao.com.br/imovel/casa-a-venda-3-quartos-pr-curitiba-juveve-RS850000/id-12345678/",
        # Sem trailing slash final — também deve casar.
        "https://www.chavesnamao.com.br/imovel/apartamento-a-venda-2-quartos-sp-sao-paulo-pinheiros-115m2-RS1650000/id-28125543",
    ],
)
def test_is_listing_url_true(url: str) -> None:
    assert ADAPTER.is_listing_url(url) is True
    assert ADAPTER.is_scrapable(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # Aluguel é bloqueado mesmo com /imovel/ + id no final.
        "https://www.chavesnamao.com.br/imovel/apartamento-para-alugar-2-quartos-sp-pindamonhangaba-andrade-72m2-RS1700/id-42050590/",
        # Sem id-NNN no final.
        "https://www.chavesnamao.com.br/imovel/apartamento-a-venda-sem-id/",
        # Domínio errado.
        "https://www.outroportal.com.br/imovel/apartamento-id-12345/",
        # Listagem de busca, não anúncio individual.
        "https://www.chavesnamao.com.br/apartamentos-a-venda/sp-pindamonhangaba/2-quartos/",
    ],
)
def test_is_listing_url_false(url: str) -> None:
    assert ADAPTER.is_listing_url(url) is False


def test_extract_external_id() -> None:
    url = "https://www.chavesnamao.com.br/imovel/apto-RS395000/id-31871873/"
    assert ADAPTER.extract_external_id(url) == "31871873"


def test_extract_external_id_handles_no_trailing_slash() -> None:
    url = "https://www.chavesnamao.com.br/imovel/apto-RS395000/id-31871873"
    assert ADAPTER.extract_external_id(url) == "31871873"


def test_extract_external_id_returns_none_when_absent() -> None:
    url = "https://www.chavesnamao.com.br/apartamentos-a-venda/sp-pindamonhangaba/2-quartos/"
    assert ADAPTER.extract_external_id(url) is None


def test_canonicalize_strips_query() -> None:
    url = "https://www.chavesnamao.com.br/imovel/apto-RS395000/id-31871873/?utm_source=google&fbclid=abc"
    assert (
        ADAPTER.canonicalize_url(url)
        == "https://www.chavesnamao.com.br/imovel/apto-RS395000/id-31871873"
    )


# =============================================================================
# is_search_results_url — listagem profunda (categoria + cidade + filtro)
# =============================================================================
@pytest.mark.parametrize(
    "url",
    [
        # apartamentos-a-venda + cidade + filtro de quartos.
        "https://www.chavesnamao.com.br/apartamentos-a-venda/sp-pindamonhangaba/2-quartos/",
        # apartamentos-a-venda + cidade + bairro + quartos.
        "https://www.chavesnamao.com.br/apartamentos-a-venda/sp-pindamonhangaba/jardim-boa-vista/2-quartos/",
        # apartamentos-a-venda + cidade + /bairros/ + rua + quartos.
        "https://www.chavesnamao.com.br/apartamentos-a-venda/sp-pindamonhangaba/bairros/avenida-jose-maria-guimaraes-alves/2-quartos/",
        # Variante curta sem "-a-venda" — mesmo destino, lista de venda.
        "https://www.chavesnamao.com.br/apartamentos/sp-pindamonhangaba/parque-das-nacoes/2-quartos/",
        # Categoria genérica /imoveis/.
        "https://www.chavesnamao.com.br/imoveis/sp-pindamonhangaba/centro/2-quartos/",
        "https://www.chavesnamao.com.br/imoveis-a-venda/sp-pindamonhangaba/bairros/travessa-onze/2-quartos/",
        # São Paulo zona-sul — categoria + cidade + zona.
        "https://www.chavesnamao.com.br/apartamentos-a-venda/sp-sao-paulo/zona-sul/2-quartos/",
        # casas-a-venda
        "https://www.chavesnamao.com.br/casas-a-venda/pr-curitiba/juveve/3-quartos/",
    ],
)
def test_is_search_results_url_true(url: str) -> None:
    assert ADAPTER.is_search_results_url(url) is True
    assert ADAPTER.is_scrapable(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # Categoria + UF apenas (raso demais — só 2 segs).
        "https://www.chavesnamao.com.br/apartamentos-a-venda/sp/",
        # ALUGUEL é bloqueado em todas as suas formas.
        "https://www.chavesnamao.com.br/apartamentos-para-alugar/sp-pindamonhangaba/2-quartos/",
        "https://www.chavesnamao.com.br/imoveis-para-alugar/sp-sao-paulo/zona-sul/",
        # Lançamentos — não comparáveis de venda usada.
        "https://www.chavesnamao.com.br/lancamentos/sp-sao-paulo/jardins/",
        # Anúncio individual (cabe em is_listing_url, não em search_results).
        "https://www.chavesnamao.com.br/imovel/apto-RS395000/id-31871873/",
        # Outro domínio.
        "https://www.outroportal.com.br/apartamentos-a-venda/sp-pindamonhangaba/2-quartos/",
    ],
)
def test_is_search_results_url_false(url: str) -> None:
    assert ADAPTER.is_search_results_url(url) is False


# =============================================================================
# Bloqueio de aluguel/lançamentos — guard rails críticos para não contaminar
# a CMA com preços de mercado de aluguel ou de imóveis na planta.
# =============================================================================
@pytest.mark.parametrize(
    "url",
    [
        "https://www.chavesnamao.com.br/imovel/apartamento-para-alugar-2-quartos-sp-pindamonhangaba-andrade-72m2-RS1700/id-42050590/",
        "https://www.chavesnamao.com.br/apartamentos-para-alugar/sp-pindamonhangaba/2-quartos/",
        "https://www.chavesnamao.com.br/lancamentos/sp-sao-paulo/jardins/",
    ],
)
def test_aluguel_e_lancamento_nunca_scrapable(url: str) -> None:
    assert ADAPTER.is_scrapable(url) is False


# =============================================================================
# classify
# =============================================================================
def test_classify() -> None:
    assert (
        ADAPTER.classify(
            "https://www.chavesnamao.com.br/imovel/apto-RS395000/id-31871873/"
        )
        == "listing"
    )
    assert (
        ADAPTER.classify(
            "https://www.chavesnamao.com.br/apartamentos-a-venda/sp-pindamonhangaba/2-quartos/"
        )
        == "search"
    )
    assert ADAPTER.classify("https://www.google.com/") == "other"


# =============================================================================
# Registry: find_adapter / all_domains
# =============================================================================
def test_find_adapter_routes_chavesnamao_url() -> None:
    ad = find_adapter("https://www.chavesnamao.com.br/imovel/apto-RS395000/id-31871873/")
    assert isinstance(ad, ChavesNaMaoAdapter)


def test_find_adapter_still_routes_vivareal_zap() -> None:
    """Garantia de que registrar o ChavesNaMão não quebrou o despacho dos
    domínios já existentes."""
    ad = find_adapter("https://www.zapimoveis.com.br/imovel/x-id-1/")
    assert isinstance(ad, VivaRealZapAdapter)
    ad2 = find_adapter("https://www.vivareal.com.br/imovel/x-id-1/")
    assert isinstance(ad2, VivaRealZapAdapter)


def test_find_adapter_returns_none_for_unknown() -> None:
    assert find_adapter("https://www.outroportal.com.br/imovel/x") is None


def test_all_domains_includes_chavesnamao_and_vivareal_zap() -> None:
    domains = all_domains()
    assert "vivareal.com.br" in domains
    assert "zapimoveis.com.br" in domains
    assert "chavesnamao.com.br" in domains
