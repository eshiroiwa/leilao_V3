"""Testes do FipeZapService — parsing do markdown gerado pelo Firecrawl.

O parser opera em duas fases:
  1. Tabela markdown ``| Cidade | UF | …% | …% | preço |``;
  2. Parágrafo do ranking textual como fallback (herda UF da tabela).

As fixtures replicam o layout real observado em
``downloads.fipe.org.br/indices/fipezap/fipezap-202604-residencial-venda.pdf``.
"""

from __future__ import annotations

from app.services.fipezap_service import FipeZapService


# Trecho da tabela real (abril/2026): "Comportamento recente dos preços"
SAMPLE_TABLE = """
| Índice/Cidade |  | Variação Mensal |  | Variação em 2026 | Variação Anual | Preço médio(R$/m²) |
| --- | --- | --- | --- | --- | --- | --- |
| Índice FipeZAP |  | +0,51% | +0,48% | +1,53% | +5,63% | 9.769 |
| São Paulo | SP | +0,19% | +0,42% | +1,02% | +4,28% | 12.019 |
| Rio de Janeiro | RJ | +0,34% | +0,33% | +0,99% | +4,00% | 10.939 |
| Belo Horizonte | MG | +0,39% | +0,25% | -0,03% | +6,73% | 10.663 |
| Brasília | DF | +0,87% | +0,25% | +3,03% | +4,54% | 10.090 |
| Salvador | BA | +1,22% | +0,55% | +3,94% | +12,75% | 8.385 |
| Curitiba | PR | +0,62% | +0,45% | -0,26% | +5,31% | 11.694 |
| Florianópolis | SC | +0,78% | +0,73% | +3,52% | +9,80% | 13.208 |
"""

# Trecho do ranking textual (mesmo mês — só primeira cidade tem (UF)):
SAMPLE_RANKING = """
no cálculo do Índice FipeZAP, Vitória (ES) apresentou o maior preço médio no mês
(R$ 14.818/m²), seguida por: Florianópolis (R$ 13.208/m²); São Paulo (R$ 12.019/m²);
Curitiba (R$ 11.694/m²); Rio de Janeiro (R$ 10.939/m²); Belo Horizonte (R$ 10.663/m²);
Brasília (R$ 10.090/m²); Salvador (R$ 8.385/m²).
"""

SAMPLE_FULL = SAMPLE_TABLE + "\n" + SAMPLE_RANKING


def test_parse_city_prices_extracts_capitals_from_table() -> None:
    """Capitais com (UF) na tabela viram leituras com state preenchido."""
    svc = FipeZapService()
    readings = svc.parse_city_prices(SAMPLE_TABLE, year=2026, month=4)
    by_city = {(r.city.strip(), r.state): r.mean_ppm2_brl for r in readings}
    assert ("São Paulo", "SP") in by_city
    assert ("Rio de Janeiro", "RJ") in by_city
    assert ("Belo Horizonte", "MG") in by_city
    assert ("Florianópolis", "SC") in by_city
    assert by_city[("São Paulo", "SP")] == 12_019.0
    assert by_city[("Rio de Janeiro", "RJ")] == 10_939.0


def test_parse_city_prices_filters_index_row() -> None:
    """Linha 'Índice FipeZAP' não tem UF de 2 letras na 2ª célula — descartada."""
    readings = FipeZapService().parse_city_prices(SAMPLE_TABLE, year=2026, month=4)
    cities = {r.city.strip() for r in readings}
    assert "Índice FipeZAP" not in cities


def test_parse_city_prices_ranking_inherits_state_from_table() -> None:
    """Cidade só aparece no ranking textual mas está na tabela → herda UF."""
    readings = FipeZapService().parse_city_prices(SAMPLE_FULL, year=2026, month=4)
    by_city = {(r.city.strip(), r.state): r.mean_ppm2_brl for r in readings}
    # Curitiba está na tabela com PR → ranking textual também herda PR (sem duplicar).
    assert ("Curitiba", "PR") in by_city
    assert by_city[("Curitiba", "PR")] == 11_694.0


def test_parse_city_prices_ranking_only_city_keeps_state_none() -> None:
    """Cidade só no ranking textual (Florianópolis aqui — sem tabela) fica
    com state=None porque não há reconciliação possível."""
    # Usa só o RANKING (sem tabela). O regex casa "Cidade (R$ X/m²)" — a
    # primeira cidade (Vitória) tem "apresentou o maior preço médio no
    # mês" entre o nome e o (R$…), então NÃO é capturada. Já Florianópolis,
    # São Paulo etc. aparecem no formato esperado.
    readings = FipeZapService().parse_city_prices(SAMPLE_RANKING, year=2026, month=4)
    cities = {r.city.strip(): r for r in readings}
    floripa = cities.get("Florianópolis")
    assert floripa is not None
    # Sem tabela para reconciliar, state fica None.
    assert floripa.state is None
    assert floripa.mean_ppm2_brl == 13_208.0


def test_parse_city_prices_distinguishes_state_for_homonyms() -> None:
    """Cidades homônimas com UFs diferentes na tabela coexistem."""
    md = """
| Campinas | SP | +0,1% | +0,1% | +1% | +5% | 8.500 |
| Campinas | RJ | +0,1% | +0,1% | +1% | +5% | 4.200 |
"""
    readings = FipeZapService().parse_city_prices(md, year=2026, month=4)
    by_state = {r.state: r.mean_ppm2_brl for r in readings if r.city.strip() == "Campinas"}
    assert by_state.get("SP") == 8_500.0
    assert by_state.get("RJ") == 4_200.0


def test_parse_city_prices_returns_sorted_desc_by_value() -> None:
    readings = FipeZapService().parse_city_prices(SAMPLE_TABLE, year=2026, month=4)
    values = [r.mean_ppm2_brl for r in readings]
    assert values == sorted(values, reverse=True)


def test_parse_city_prices_empty_markdown_returns_empty_list() -> None:
    assert FipeZapService().parse_city_prices("", year=2026, month=4) == []


def test_reading_carries_year_and_month() -> None:
    readings = FipeZapService().parse_city_prices(SAMPLE_TABLE, year=2026, month=4)
    assert all(r.year == 2026 and r.month == 4 for r in readings)


def test_parse_city_prices_skips_low_values_as_index_noise() -> None:
    """Valores < R$ 1.000 (variações %, índices base 100) são descartados."""
    md = """
| Algum índice | SP | +1% | +2% | +3% | +4% | 150 |
"""
    readings = FipeZapService().parse_city_prices(md, year=2026, month=4)
    assert readings == []
