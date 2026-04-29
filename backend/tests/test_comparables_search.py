"""Testes do módulo de busca do AGENTE 2."""

from __future__ import annotations

import pytest

from app.agents.comparables.search import (
    build_queries,
    detect_condo_name,
    is_dense_city,
    next_strategy,
    radius_plan,
)


# =============================================================================
# is_dense_city / radius_plan
# =============================================================================
@pytest.mark.parametrize(
    ("city", "state", "expected"),
    [
        ("São Paulo", "SP", True),
        ("Rio de Janeiro", "RJ", True),
        ("BRASÍLIA", "DF", True),
        ("são bernardo do campo", "SP", True),
        ("Pindamonhangaba", "SP", False),
        ("Itu", "SP", False),
        ("São Paulo", "RJ", False),  # cidade certa, UF errada
        (None, "SP", False),
        ("São Paulo", None, False),
    ],
)
def test_is_dense_city(city: str | None, state: str | None, expected: bool) -> None:
    assert is_dense_city(city, state) is expected


def test_radius_plan_dense_starts_small() -> None:
    plan = radius_plan("São Paulo", "SP")
    assert plan[0] == 1000
    assert plan == (1000, 2000, 3000)


def test_radius_plan_sparse_starts_larger() -> None:
    plan = radius_plan("Pindamonhangaba", "SP")
    assert plan[0] == 2500
    assert plan[-1] == 10000


# =============================================================================
# detect_condo_name
# =============================================================================
@pytest.mark.parametrize(
    ("title", "complement", "expected"),
    [
        ("Apartamento no Edifício Jardim das Acácias", None, "Jardim das Acácias"),
        ("Casa térrea", "Residencial Vila Verde, casa 12", "Vila Verde"),
        ("EDIFÍCIO RUI BARBOSA - Apartamento 503", None, "RUI BARBOSA"),
        # ---- casos negativos ----
        ("Apartamento 2 dorms", None, None),       # nada de prefixo
        ("Lote no bairro X", "S/N", None),         # complement curto/inválido
        (None, None, None),
        # Texto contratual de edital — antes virava nome de condomínio!
        (
            "Apartamento. Condomínio e Tributos sob responsabilidade do comprador",
            None,
            None,
        ),
        # Match longo demais (>5 palavras) — também rejeita
        (
            "Edifício este nome aqui é muito longo para ser real demais",
            None,
            None,
        ),
        # Prefixo abreviado "Cond." sozinho não dispara mais (gerava muito ruído)
        ("Apto", "Cond. Solar dos Pássaros, bloco A", None),
    ],
)
def test_detect_condo_name(
    title: str | None,
    complement: str | None,
    expected: str | None,
) -> None:
    target = {"title": title, "complement": complement}
    got = detect_condo_name(target)
    if expected is None:
        assert got is None, got
    else:
        assert got is not None
        assert expected.lower() in got.lower()


# =============================================================================
# build_queries
# =============================================================================
def _base_target() -> dict:
    return {
        "city": "São Paulo",
        "state": "SP",
        "neighborhood": "Vila Mariana",
        "street": "Rua Domingos de Morais",
        "property_type": "apartamento",
        "bedrooms": 2,
        "title": "Apartamento Edifício Jardim das Acácias",
    }


def test_build_queries_condo_uses_name_and_city() -> None:
    qs = build_queries(_base_target(), strategy="condo")
    assert len(qs) == 1
    q = qs[0]
    assert "Jardim das Acácias" in q
    assert "São Paulo" in q
    assert "vivareal" in q.lower() or "zapimoveis" in q.lower()


def test_build_queries_street_uses_street_and_neighborhood() -> None:
    qs = build_queries(_base_target(), strategy="street")
    assert qs and "Domingos de Morais" in qs[0]
    assert "Vila Mariana" in qs[0]


def test_build_queries_neighborhood_includes_type_and_beds() -> None:
    qs = build_queries(_base_target(), strategy="neighborhood")
    assert qs
    q = qs[0]
    assert "apartamento" in q
    assert "2 quartos" in q
    assert "Vila Mariana" in q


def test_build_queries_radius_returns_empty() -> None:
    # 'radius' usa PostGIS, não Firecrawl. build_queries não deve montar nada.
    assert build_queries(_base_target(), strategy="radius") == []


def test_build_queries_condo_without_name_is_empty() -> None:
    target = {**_base_target(), "title": "apenas título genérico", "complement": None}
    assert build_queries(target, strategy="condo") == []


def test_build_queries_no_city_or_state_is_empty() -> None:
    assert build_queries({"city": "", "state": ""}, strategy="neighborhood") == []


def test_build_queries_preserves_site_filter_completely() -> None:
    """Regressão: antes a query era cortada em 80 chars e o filtro virava
    `(site:vivareal'`, fazendo o Firecrawl voltar 0 resultados sempre.
    Agora o filtro precisa estar SEMPRE íntegro no fim da query."""
    target = {
        **_base_target(),
        "street": "Avenida João Francisco da Silva Sobrinho",
        "neighborhood": "Bairro do Feital Jardim Belo Horizonte",
    }
    for strategy in ("street", "neighborhood", "condo"):
        for q in build_queries(target, strategy=strategy):  # type: ignore[arg-type]
            assert "site:vivareal.com.br" in q, q
            assert "site:zapimoveis.com.br" in q, q
            assert q.rstrip().endswith(")"), q  # filtro encerra com `)`


# =============================================================================
# next_strategy
# =============================================================================
@pytest.mark.parametrize(
    ("cur", "nxt"),
    [
        ("condo", "street"),
        ("street", "neighborhood"),
        ("neighborhood", "radius"),
        ("radius", None),
    ],
)
def test_next_strategy(cur: str, nxt: str | None) -> None:
    assert next_strategy(cur) == nxt  # type: ignore[arg-type]
