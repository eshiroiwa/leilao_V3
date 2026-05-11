"""Testes do FipeZapService — parsing do markdown gerado pelo Firecrawl."""

from __future__ import annotations

from app.services.fipezap_service import FipeZapService


# Markdown sintético inspirado no layout real dos PDFs FipeZAP. O parser não
# precisa do PDF inteiro — só do bloco "ranking de preços médios". Aqui
# misturamos ranking absoluto + ranking de variação no mesmo texto para
# garantir que a deduplicação por cidade funcione e que valores baixos
# (índices, variações %) sejam ignorados.
SAMPLE_MARKDOWN = """
# Índice FipeZAP — Residencial Venda

## Ranking de preço médio (R$/m²)

1.  Vitória (ES) ............................. R$ 14.253
2.  Florianópolis (SC) ....................... R$ 12.864
3.  São Paulo (SP) ........................... R$ 11.915,40
4.  Curitiba (PR) ............................ R$ 11.646
5.  Rio de Janeiro (RJ) ...................... R$ 10.850
6.  Belo Horizonte (MG) ...................... R$ 10.640
7.  Brasília (DF) ............................ R$ 9.857
8.  Porto Alegre (RS) ........................ R$ 8.530

## Variação 12 meses (%)

Vitória (ES) ... R$ 6,50
Florianópolis (SC) ... R$ 5,30
São Paulo (SP) ... R$ 4,10
Brasília (DF) ... R$ 2,00
"""


def test_parse_city_prices_extracts_main_capitals() -> None:
    svc = FipeZapService()
    readings = svc.parse_city_prices(SAMPLE_MARKDOWN, year=2026, month=1)
    by_city = {(r.city.strip(), r.state): r.mean_ppm2_brl for r in readings}
    # Capitais conhecidas devem aparecer.
    assert ("Vitória", "ES") in by_city
    assert ("São Paulo", "SP") in by_city
    assert ("Rio de Janeiro", "RJ") in by_city


def test_parse_city_prices_returns_absolute_brl_values() -> None:
    svc = FipeZapService()
    readings = svc.parse_city_prices(SAMPLE_MARKDOWN, year=2026, month=1)
    by_city = {(r.city.strip(), r.state): r.mean_ppm2_brl for r in readings}
    # Valores absolutos, não índices ou variações %.
    assert by_city[("Vitória", "ES")] == 14_253.0
    assert by_city[("São Paulo", "SP")] == 11_915.40
    # Variações (R$ 6,50 etc.) NÃO devem entrar — filtradas por < R$ 1.000.
    assert all(r.mean_ppm2_brl >= 1_000 for r in readings)


def test_parse_city_prices_dedupes_by_city_keeping_max() -> None:
    """Mesmo município em duas seções → guarda só uma entrada com o MAIOR valor."""
    md = """
        São Paulo (SP) R$ 11.915
        São Paulo (SP) R$ 12.000  -- valor mais alto que deveria ganhar
        São Paulo (SP) R$ 4,10    -- variação % filtrada
    """
    readings = FipeZapService().parse_city_prices(md, year=2026, month=1)
    sps = [r for r in readings if r.city.strip() == "São Paulo"]
    assert len(sps) == 1
    assert sps[0].mean_ppm2_brl == 12_000.0


def test_parse_city_prices_distinguishes_state_for_homonyms() -> None:
    """Campinas SP vs Campinas RJ devem ser leituras distintas."""
    md = """
        Campinas (SP) R$ 8.500
        Campinas (RJ) R$ 4.200
    """
    readings = FipeZapService().parse_city_prices(md, year=2026, month=1)
    by_state = {r.state: r.mean_ppm2_brl for r in readings if r.city.strip() == "Campinas"}
    assert by_state.get("SP") == 8_500.0
    assert by_state.get("RJ") == 4_200.0


def test_parse_city_prices_returns_sorted_desc_by_value() -> None:
    readings = FipeZapService().parse_city_prices(SAMPLE_MARKDOWN, year=2026, month=1)
    values = [r.mean_ppm2_brl for r in readings]
    assert values == sorted(values, reverse=True)


def test_parse_city_prices_empty_markdown_returns_empty_list() -> None:
    assert FipeZapService().parse_city_prices("", year=2026, month=1) == []


def test_reading_carries_year_and_month() -> None:
    readings = FipeZapService().parse_city_prices(SAMPLE_MARKDOWN, year=2026, month=3)
    assert all(r.year == 2026 and r.month == 3 for r in readings)
