"""Testes do adapter VivaReal/ZAP."""

from __future__ import annotations

import pytest

from app.agents.comparables.sources import find_adapter
from app.agents.comparables.sources.vivareal_zap import VivaRealZapAdapter

ADAPTER = VivaRealZapAdapter()


@pytest.mark.parametrize(
    "url",
    [
        "https://www.vivareal.com.br/imovel/apartamento-2-quartos-vila-mariana-id-2546789012/",
        "https://www.zapimoveis.com.br/imovel/apartamento-3-dormitorios-id-2718281828/",
    ],
)
def test_is_listing_url_true(url: str) -> None:
    assert ADAPTER.is_listing_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.vivareal.com.br/venda/sp/sao-paulo/",
        "https://www.zapimoveis.com.br/venda/imoveis/sp+sao-paulo/",
        "https://www.outraimobiliaria.com.br/imovel/x-id-123/",
        "https://www.vivareal.com.br/imovel/sem-id-no-final/",
    ],
)
def test_is_listing_url_false(url: str) -> None:
    assert ADAPTER.is_listing_url(url) is False


def test_extract_external_id() -> None:
    url = "https://www.vivareal.com.br/imovel/apto-id-123456/"
    assert ADAPTER.extract_external_id(url) == "123456"


def test_canonicalize_strips_query() -> None:
    url = "https://www.vivareal.com.br/imovel/x-id-7/?utm_source=google&fbclid=abc"
    assert ADAPTER.canonicalize_url(url) == "https://www.vivareal.com.br/imovel/x-id-7"


def test_classify() -> None:
    assert ADAPTER.classify("https://www.vivareal.com.br/imovel/x-id-1/") == "listing"
    assert ADAPTER.classify("https://www.vivareal.com.br/venda/sp/") == "search"
    assert ADAPTER.classify("https://www.google.com/") == "other"


def test_find_adapter_dispatches() -> None:
    assert isinstance(
        find_adapter("https://www.zapimoveis.com.br/imovel/x-id-1/"),
        VivaRealZapAdapter,
    )
    assert find_adapter("https://www.outroportal.com.br/anuncio/123") is None


# =============================================================================
# is_search_results_url / is_scrapable
#   Páginas de listagem profundas (com filtro por bairro/rua) são candidatas
#   válidas para batch extraction. Páginas rasas (UF/cidade só) NÃO.
# =============================================================================
@pytest.mark.parametrize(
    "url",
    [
        # VivaReal: bairro
        "https://www.vivareal.com.br/venda/sp/sao-paulo/zona-sul/jardim-guedala/",
        # VivaReal: bairro + rua + categoria
        "https://www.vivareal.com.br/venda/sp/sao-paulo/zona-sul/jardim-guedala/avenida-morumbi/casa_residencial/",
        # ZAP: filtro composto com `+` (depth via `+` count)
        "https://www.zapimoveis.com.br/venda/casas-de-condominio/sp+sao-paulo+zona-sul+jd-guedala/",
    ],
)
def test_is_search_results_url_true(url: str) -> None:
    assert ADAPTER.is_search_results_url(url) is True
    assert ADAPTER.is_scrapable(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.vivareal.com.br/venda/sp/",  # raso demais
        "https://www.vivareal.com.br/venda/sp/sao-paulo/",  # cidade só
        "https://www.outroportal.com.br/venda/sp/x/y/z/w/v/",  # outro domínio
        # ALUGUEL e LANÇAMENTOS são bloqueados — não são comparáveis de venda.
        "https://www.zapimoveis.com.br/aluguel/apartamentos/sp+pindamonhangaba/rua-imperatriz-leopoldina",
        "https://www.vivareal.com.br/aluguel/sp/sao-paulo/zona-sul/jardim-guedala/",
        "https://www.vivareal.com.br/lancamentos/sp/sao-paulo/zona-sul/",
    ],
)
def test_is_search_results_url_false(url: str) -> None:
    assert ADAPTER.is_search_results_url(url) is False
    assert ADAPTER.is_scrapable(url) is False


def test_anuncio_individual_continua_scrapable() -> None:
    """Garantia de regressão: páginas /imovel/.../-id-N/ continuam aceitas."""
    url = "https://www.vivareal.com.br/imovel/casa-3q-jardim-bosques-id-2723912534/"
    assert ADAPTER.is_listing_url(url) is True
    assert ADAPTER.is_scrapable(url) is True
