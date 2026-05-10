"""Testes da configuração paramétrica por tipo de imóvel
(``type_config.py``).

Garante que:

  * cada tipo conhecido devolve uma config consistente (área_field
    correto, sigma e thresholds não-negativos, ``area_hard_max <
    area_hard_max_relaxed``);
  * tipos desconhecidos caem no default sem explodir;
  * a heurística de "casa de condomínio fechado" detecta os padrões
    textuais óbvios E NÃO marca falso positivo em apartamentos ou
    casas de rua sem texto;
  * ``effective_property_type_for_cma`` promove ``casa`` →
    ``casa_condominio`` quando aplicável.
"""

from __future__ import annotations

import pytest

from app.agents.comparables.type_config import (
    _BY_TYPE,
    _DEFAULT,
    TypeConfig,
    effective_property_type_for_cma,
    get_type_config,
    is_gated_community_house,
)


# =============================================================================
# Tabela de tipos: invariantes estruturais
# =============================================================================
@pytest.mark.parametrize("ptype, config", list(_BY_TYPE.items()))
def test_each_type_config_is_internally_consistent(
    ptype: str, config: TypeConfig
) -> None:
    """sigma > 0; hard_max > 0; relaxed > strict; preferred não vazio."""
    assert config.area_sigma > 0, ptype
    assert config.area_hard_max > 0, ptype
    assert config.area_hard_max_relaxed >= config.area_hard_max, (
        f"{ptype}: relaxed deve ser >= strict"
    )
    assert config.preferred_strategies, ptype
    # Todas estratégias listadas são valores válidos.
    valid = {"condo", "street", "neighborhood", "radius"}
    assert all(s in valid for s in config.preferred_strategies), ptype


def test_apartamento_is_more_strict_than_casa_on_area() -> None:
    """Apartamento: oferta uniforme dentro do prédio → sigma menor +
    hard filter mais apertado. Casa de rua: heterogênea → sigma maior."""
    apto = _BY_TYPE["apartamento"]
    casa = _BY_TYPE["casa"]
    assert apto.area_sigma < casa.area_sigma
    assert apto.area_hard_max < casa.area_hard_max


def test_terreno_uses_total_field() -> None:
    """Terreno é precificado por m² de TERRENO — comparar built faz
    zero sentido."""
    assert _BY_TYPE["terreno"].area_field == "total"


def test_comercial_uses_useful_field() -> None:
    """Comercial: m² locável (área útil de loja/sala). Built engloba
    áreas comuns que distorcem comparação."""
    assert _BY_TYPE["comercial"].area_field == "useful"


# =============================================================================
# get_type_config: roteamento
# =============================================================================
def test_unknown_type_falls_back_to_default() -> None:
    """Tipo desconhecido → ``_DEFAULT``, sem explodir."""
    eff, cfg = get_type_config({"property_type": "marciano"})
    assert eff == "marciano"  # nome preservado para logs
    assert cfg is _DEFAULT


def test_known_type_returns_specific_config() -> None:
    eff, cfg = get_type_config({"property_type": "apartamento"})
    assert eff == "apartamento"
    assert cfg is _BY_TYPE["apartamento"]


def test_get_type_config_is_case_insensitive() -> None:
    eff, cfg = get_type_config({"property_type": "APARTAMENTO"})
    assert eff == "apartamento"
    assert cfg is _BY_TYPE["apartamento"]


def test_empty_target_falls_back_to_default() -> None:
    eff, cfg = get_type_config({})
    assert eff == ""
    assert cfg is _DEFAULT


# =============================================================================
# Detecção de casa de condomínio fechado
# =============================================================================
def test_house_with_fenced_community_text_is_detected() -> None:
    target = {
        "property_type": "casa",
        "title": "Casa em condomínio fechado com piscina",
        "complement": "",
    }
    assert is_gated_community_house(target) is True


def test_house_horizontal_condo_pattern() -> None:
    target = {
        "property_type": "casa",
        "complement": "Condomínio Horizontal Ville Lumiére",
    }
    assert is_gated_community_house(target) is True


def test_loteamento_fechado_pattern() -> None:
    target = {"property_type": "casa", "title": "Loteamento Fechado Ipês"}
    assert is_gated_community_house(target) is True


def test_alphaville_brand_match() -> None:
    target = {"property_type": "sobrado", "complement": "Alphaville Lagoa dos Ingleses"}
    assert is_gated_community_house(target) is True


def test_house_without_pattern_is_not_gated() -> None:
    """Casa sem texto sugestivo: NÃO marca como gated (falso positivo
    seria pior que falso negativo aqui — geraria filtros mais rígidos
    onde não cabem)."""
    target = {
        "property_type": "casa",
        "title": "Casa 3 quartos no centro",
        "complement": "Próximo à Av. Brasil",
    }
    assert is_gated_community_house(target) is False


def test_apartamento_never_marked_as_gated_community() -> None:
    """Apartamento com texto contendo "condomínio fechado" continua
    apartamento — a promoção só vale para casa/sobrado."""
    target = {
        "property_type": "apartamento",
        "title": "Apto em condomínio fechado, 60m²",
    }
    assert is_gated_community_house(target) is False


# =============================================================================
# effective_property_type_for_cma
# =============================================================================
def test_promotes_casa_to_casa_condominio_when_gated() -> None:
    target = {
        "property_type": "casa",
        "title": "Casa em condomínio fechado",
    }
    assert effective_property_type_for_cma(target) == "casa_condominio"

    eff, cfg = get_type_config(target)
    assert eff == "casa_condominio"
    assert cfg is _BY_TYPE["casa_condominio"]


def test_does_not_promote_casa_without_gated_signal() -> None:
    target = {"property_type": "casa", "title": "Casa de esquina"}
    assert effective_property_type_for_cma(target) == "casa"
