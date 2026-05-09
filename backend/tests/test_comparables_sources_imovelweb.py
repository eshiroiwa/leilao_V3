"""Testes do adapter ImovelWeb e da entrada no registry."""

from __future__ import annotations

import pytest

from app.agents.comparables.sources import all_domains, find_adapter
from app.agents.comparables.sources.imovelweb import ImovelWebAdapter

ADAPTER = ImovelWebAdapter()


# =============================================================================
# is_listing_url — só URLs de anúncio individual de VENDA em /propriedades/
# =============================================================================
@pytest.mark.parametrize(
    "url",
    [
        "https://www.imovelweb.com.br/propriedades/apartamento-a-venda-com-otima-localizacao-no-3028238732.html",
        "https://www.imovelweb.com.br/propriedades/duplex-mont-tannat-no-centro-com-uma-excelente-2999680136.html",
        # ID com 10 dígitos.
        "https://www.imovelweb.com.br/propriedades/casa-3-quartos-jardim-x-2987654321.html",
    ],
)
def test_is_listing_url_true(url: str) -> None:
    assert ADAPTER.is_listing_url(url) is True
    assert ADAPTER.is_scrapable(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # Aluguel é bloqueado mesmo dentro de /propriedades/.
        "https://www.imovelweb.com.br/propriedades/apto-aluguel-2-quartos-3028238732.html",
        # Página de busca (não /propriedades/).
        "https://www.imovelweb.com.br/apartamentos-venda-pindamonhangaba-sp-2-quartos.html",
        # Domínio errado.
        "https://www.outroportal.com.br/propriedades/apto-12345678.html",
        # ID curto demais (< 8 dígitos): provavelmente é só número de rua.
        "https://www.imovelweb.com.br/propriedades/apto-rua-123.html",
        # Sem .html
        "https://www.imovelweb.com.br/propriedades/apto-3028238732/",
    ],
)
def test_is_listing_url_false(url: str) -> None:
    assert ADAPTER.is_listing_url(url) is False


def test_extract_external_id() -> None:
    url = "https://www.imovelweb.com.br/propriedades/apartamento-a-venda-com-otima-localizacao-no-3028238732.html"
    assert ADAPTER.extract_external_id(url) == "3028238732"


def test_extract_external_id_returns_none_when_absent() -> None:
    url = "https://www.imovelweb.com.br/apartamentos-venda-pindamonhangaba-sp-2-quartos.html"
    assert ADAPTER.extract_external_id(url) is None


def test_extract_external_id_ignores_short_numbers() -> None:
    """Páginas como ``...rua-francisco-leitao-577.html`` não são listings —
    o número 577 é referência de rua, não id externo."""
    url = "https://www.imovelweb.com.br/apartamentos-venda-pinheiros-sao-paulo-perto-de-iw-gamba-rua-francisco-leitao-577.html"
    assert ADAPTER.extract_external_id(url) is None


def test_canonicalize_strips_query() -> None:
    url = "https://www.imovelweb.com.br/propriedades/apto-3028238732.html?utm_source=google&precio=200000"
    assert (
        ADAPTER.canonicalize_url(url)
        == "https://www.imovelweb.com.br/propriedades/apto-3028238732.html"
    )


# =============================================================================
# is_search_results_url — listagem específica (categoria + venda + cidade
# + ao menos 1 filtro adicional)
# =============================================================================
@pytest.mark.parametrize(
    "url",
    [
        # apartamentos-venda + cidade + UF + quartos.
        "https://www.imovelweb.com.br/apartamentos-venda-pindamonhangaba-sp-2-quartos.html",
        # apartamentos-venda + bairro + cidade + quartos.
        "https://www.imovelweb.com.br/apartamentos-venda-feital-pindamonhangaba-2-quartos.html",
        # com ordenação como filtro adicional.
        "https://www.imovelweb.com.br/apartamentos-venda-pindamonhangaba-sp-2-quartos-ordem-precio-menor.html",
        # cobertura.
        "https://www.imovelweb.com.br/apartamentos-cobertura-venda-sao-paulo-sp-2-quartos.html",
        # duplex.
        "https://www.imovelweb.com.br/apartamentos-duplex-venda-pinheiros-sao-paulo-2-quartos.html",
        # casas.
        "https://www.imovelweb.com.br/casas-venda-jardim-sao-paulo-zona-norte-q-terrea.html",
        # imoveis (categoria genérica).
        "https://www.imovelweb.com.br/imoveis-venda-pindamonhangaba-sp-2-quartos.html",
        # com filtro de área + varanda.
        "https://www.imovelweb.com.br/apartamentos-venda-feital-pindamonhangaba-areap-varanda-2-quartos-ordem-precio-menor.html",
    ],
)
def test_is_search_results_url_true(url: str) -> None:
    assert ADAPTER.is_search_results_url(url) is True
    assert ADAPTER.is_scrapable(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # Listagem RASA — só estado.
        "https://www.imovelweb.com.br/apartamentos-venda-sp.html",
        # Listagem RASA — só cidade-UF (categoria + venda + cidade + UF = 4 tokens).
        "https://www.imovelweb.com.br/apartamentos-venda-pindamonhangaba-sp.html",
        # ALUGUEL é bloqueado em todas as suas formas.
        "https://www.imovelweb.com.br/apartamentos-aluguel-portao-curitiba-2-quartos.html",
        "https://www.imovelweb.com.br/imoveis-aluguel-sp-sao-paulo.html",
        # TEMPORADA bloqueada.
        "https://www.imovelweb.com.br/apartamentos-temporada-praia-grande-sp.html",
        # Lançamentos bloqueados.
        "https://www.imovelweb.com.br/lancamentos/sao-paulo-sp.html",
        # /propriedades/ é anúncio individual, não listagem.
        "https://www.imovelweb.com.br/propriedades/apto-3028238732.html",
        # Outro domínio.
        "https://www.outroportal.com.br/apartamentos-venda-pindamonhangaba-sp-2-quartos.html",
        # Path institucional (não começa com prefixo válido de venda).
        "https://www.imovelweb.com.br/sobre-nos.html",
    ],
)
def test_is_search_results_url_false(url: str) -> None:
    assert ADAPTER.is_search_results_url(url) is False


# =============================================================================
# Bloqueio de aluguel/temporada/lançamentos — guard rails críticos
# =============================================================================
@pytest.mark.parametrize(
    "url",
    [
        "https://www.imovelweb.com.br/apartamentos-aluguel-portao-curitiba-2-quartos.html",
        "https://www.imovelweb.com.br/apartamentos-temporada-praia-grande-sp.html",
        "https://www.imovelweb.com.br/propriedades/apto-aluguel-2-quartos-3028238732.html",
        "https://www.imovelweb.com.br/lancamentos/jardins-sao-paulo.html",
    ],
)
def test_aluguel_temporada_lancamento_nunca_scrapable(url: str) -> None:
    assert ADAPTER.is_scrapable(url) is False


# =============================================================================
# classify
# =============================================================================
def test_classify() -> None:
    assert (
        ADAPTER.classify(
            "https://www.imovelweb.com.br/propriedades/apto-3028238732.html"
        )
        == "listing"
    )
    assert (
        ADAPTER.classify(
            "https://www.imovelweb.com.br/apartamentos-venda-pindamonhangaba-sp-2-quartos.html"
        )
        == "search"
    )
    assert ADAPTER.classify("https://www.google.com/") == "other"


# =============================================================================
# Registry: find_adapter / all_domains
# =============================================================================
def test_find_adapter_routes_imovelweb_url() -> None:
    ad = find_adapter(
        "https://www.imovelweb.com.br/propriedades/apto-3028238732.html"
    )
    assert isinstance(ad, ImovelWebAdapter)


def test_find_adapter_routes_imovelweb_search_url() -> None:
    ad = find_adapter(
        "https://www.imovelweb.com.br/apartamentos-venda-pindamonhangaba-sp-2-quartos.html"
    )
    assert isinstance(ad, ImovelWebAdapter)


def test_all_domains_includes_imovelweb() -> None:
    assert "imovelweb.com.br" in all_domains()
