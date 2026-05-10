"""Configuração paramétrica por tipo de imóvel para o AGENTE 2.

Por que existe (alternativa a "um agente por tipo"):

  Apartamentos, casas, lojas, terrenos e rurais precisam de regras
  ligeiramente diferentes para CMA, mas o pipeline (search → scrape →
  extract → enrich → score → price) é o mesmo. Em vez de duplicar 5
  pipelines (custo de manutenção alto, divergência inevitável), isolamos
  AS DECISÕES QUE VARIAM aqui:

    * qual campo de área usar para comparar tamanhos (built/useful/total);
    * quão tolerante é a similaridade de área (sigma) e o hard filter
      (rejeita se |Δ área| > N%);
    * quais estratégias de busca priorizar (apartamento começa em
      ``condo``, casa de rua direto em ``street``, etc.);
    * tolerâncias de "auto-self" (anúncio do próprio imóvel do leilão
      num portal de mercado, comum em lotes Caixa).

  O grafo lê :func:`get_type_config` antes do scoring e usa a config
  resultante para todos os filtros/scores. Tunar o comportamento de um
  tipo é mexer numa LINHA aqui — todo o resto fica intacto.

Convenções:

  ``area_field="auto"`` delega para
  :func:`pricing.effective_target_area_m2`, que já decide built/total/
  útil pelo property_type seguindo a mesma política do precificador
  (E5). Em "casa", isso significa ``area_built_m2`` (não terreno).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

# ``Literal`` ao invés de ``SearchStrategy`` (de ``search.py``) para evitar
# import circular: ``search.py`` consome este módulo no futuro próximo.
SearchStrategyName = Literal["condo", "street", "neighborhood", "radius"]

AreaField = Literal["built", "useful", "total", "auto"]


@dataclass(frozen=True, slots=True)
class TypeConfig:
    """Configuração paramétrica para um tipo de imóvel.

    Cada campo é documentado individualmente. Os defaults vêm do tipo
    "outro" (:data:`_DEFAULT`) — conservadores o suficiente pra não
    explodir, mas não tão precisos quanto os tipos específicos.
    """

    # ---- Similaridade de área ------------------------------------- #
    # Campo de área a usar para comparar tamanhos (target vs comp).
    # ``"auto"`` delega para :func:`pricing.effective_target_area_m2`.
    area_field: AreaField

    # Sigma da gaussiana de similaridade de área. Decay para |Δ área|
    # relativa: score ≈ exp(-(diff/sigma)²/2). Apartamentos são
    # uniformes (sigma=0.15), rurais bem heterogêneos (sigma=0.50).
    area_sigma: float

    # ---- Hard filter de área -------------------------------------- #
    # Rejeita comparáveis com |Δ área|/area_target > area_hard_max.
    # Aplicado em CIMA do sigma — comparável fora dessa faixa NUNCA
    # entra na CMA, independentemente da similaridade composta.
    area_hard_max: float

    # Versão relaxada, ativada quando o pipeline esgota busca em raio
    # e estratégia mas ainda tem < min_comparables_acceptable. Custo
    # zero (apenas re-roda o score com tolerância maior). Mais barato
    # que aumentar raio (que dispara nova busca/scrape/LLM).
    area_hard_max_relaxed: float

    # ---- Estratégias de busca ------------------------------------- #
    # Ordem de preferência. ``apartamento`` começa em ``condo`` se
    # tiver nome do condomínio; ``casa`` direto em ``street``; etc.
    preferred_strategies: tuple[SearchStrategyName, ...]

    # ---- Auto-self detection -------------------------------------- #
    # "Próprio imóvel do leilão anunciado em portal de mercado":
    #   distância < ``auto_self_distance_m`` E
    #   |Δ área|/area < ``auto_self_area_pct`` E
    #   |Δ preço|/preço_alvo < ``auto_self_price_pct``
    #     (preço_alvo = minimum_bid_first | minimum_bid_second | appraisal_value)
    auto_self_distance_m: float = 50.0
    auto_self_area_pct: float = 0.02
    auto_self_price_pct: float = 0.02


# Default razoável para tipos não cobertos / desconhecidos.
_DEFAULT = TypeConfig(
    area_field="auto",
    area_sigma=0.20,
    area_hard_max=0.50,
    area_hard_max_relaxed=0.75,
    preferred_strategies=("street", "neighborhood"),
)


# Tabela de tipos. Mexer aqui é o único lugar quando quisermos ajustar
# comportamento por tipo. Mudanças TÊM teste — ver
# ``tests/test_comparables_type_config.py``.
_BY_TYPE: dict[str, TypeConfig] = {
    # Apartamentos: oferta uniforme dentro do prédio. Estratégia "condo"
    # (mesmo edifício) é o sinal mais forte que existe — vence tudo.
    "apartamento": TypeConfig(
        area_field="auto",
        area_sigma=0.15,
        area_hard_max=0.35,
        area_hard_max_relaxed=0.55,
        preferred_strategies=("condo", "street", "neighborhood"),
    ),
    # Casa de rua: heterogeneidade muito alta (popular vs alto padrão
    # no mesmo bairro). Sem âncora de prédio, dependemos de rua/bairro.
    "casa": TypeConfig(
        area_field="auto",
        area_sigma=0.30,
        area_hard_max=0.50,
        area_hard_max_relaxed=0.75,
        preferred_strategies=("street", "neighborhood"),
    ),
    "sobrado": TypeConfig(
        area_field="auto",
        area_sigma=0.30,
        area_hard_max=0.50,
        area_hard_max_relaxed=0.75,
        preferred_strategies=("street", "neighborhood"),
    ),
    # Casa de condomínio fechado: padronização parecida com apartamento.
    # Resolvido via ``effective_property_type_for_cma`` quando
    # ``is_gated_community_house`` retorna True.
    "casa_condominio": TypeConfig(
        area_field="auto",
        area_sigma=0.20,
        area_hard_max=0.40,
        area_hard_max_relaxed=0.60,
        preferred_strategies=("condo", "street", "neighborhood"),
    ),
    # Comercial: m² útil é o que importa (área de loja efetivamente
    # alugável). Sigma maior porque há muita variedade (sala vs loja
    # térrea vs galpão pequeno).
    "comercial": TypeConfig(
        area_field="useful",
        area_sigma=0.25,
        area_hard_max=0.50,
        area_hard_max_relaxed=0.75,
        preferred_strategies=("street", "neighborhood"),
    ),
    # Galpão: ainda mais heterogêneo (industrial vs logístico vs estoque).
    # Bairro é o melhor signal disponível.
    "galpao": TypeConfig(
        area_field="useful",
        area_sigma=0.30,
        area_hard_max=0.60,
        area_hard_max_relaxed=0.85,
        preferred_strategies=("neighborhood",),
    ),
    # Terreno: comparação por m² de TERRENO (não construído).
    "terreno": TypeConfig(
        area_field="total",
        area_sigma=0.30,
        area_hard_max=0.50,
        area_hard_max_relaxed=0.75,
        preferred_strategies=("street", "neighborhood"),
    ),
    # Rural: variabilidade enorme (sítio vs fazenda vs chácara).
    # Sigma alto, hard filter generoso.
    "rural": TypeConfig(
        area_field="total",
        area_sigma=0.50,
        area_hard_max=1.00,
        area_hard_max_relaxed=2.00,
        preferred_strategies=("neighborhood",),
    ),
}


# Padrões de texto que sinalizam casa em condomínio fechado.
# Lista deliberadamente curta — falso positivo aqui significa aplicar
# config de "apartamento" numa casa de rua, gerando filtros mais
# rígidos e potencialmente menos comparáveis.
_GATED_COMMUNITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"condom[ií]nio\s+fechado", re.IGNORECASE),
    re.compile(r"condom[ií]nio\s+horizontal", re.IGNORECASE),
    re.compile(r"loteamento\s+fechado", re.IGNORECASE),
    # Marcas conhecidas de condomínios fechados (casos óbvios).
    re.compile(r"\balphaville\b", re.IGNORECASE),
    re.compile(r"\btambor[eé]\b", re.IGNORECASE),
)


def is_gated_community_house(target: dict[str, Any]) -> bool:
    """Detecta se o target é uma casa em condomínio fechado.

    Heurística textual em ``title`` + ``complement`` + ``description``:
    casamento com qualquer um de :data:`_GATED_COMMUNITY_PATTERNS`.
    Quando a tabela ``properties`` ganhar um ``monthly_condo_fee``,
    incluir aqui (``fee > 0`` para tipo casa/sobrado é sinal forte).
    """
    ptype = (target.get("property_type") or "").strip().lower()
    if ptype not in {"casa", "sobrado"}:
        return False

    haystacks = " ".join(
        str(target.get(k) or "")
        for k in ("title", "complement", "description")
    )
    if not haystacks.strip():
        return False
    return any(p.search(haystacks) for p in _GATED_COMMUNITY_PATTERNS)


def effective_property_type_for_cma(target: dict[str, Any]) -> str:
    """Devolve o ``property_type`` "efetivo" usado para escolher
    config — pode promover ``casa`` para ``casa_condominio`` quando
    detecta condomínio fechado, mantendo todos os outros tipos como
    estão.

    Não persiste nada — só decide a config. O ``property_type`` na
    tabela ``properties`` segue sendo o original ("casa") por
    consistência semântica.
    """
    raw = (target.get("property_type") or "").strip().lower()
    if raw in {"casa", "sobrado"} and is_gated_community_house(target):
        return "casa_condominio"
    return raw


def get_type_config(target: dict[str, Any]) -> tuple[str, TypeConfig]:
    """Resolve a :class:`TypeConfig` para o target.

    Retorna ``(effective_type, config)``:

      * ``effective_type`` = saída de :func:`effective_property_type_for_cma`,
        útil para logs e exposição em ``OpportunityAssumptions`` /
        ``ValuationAssumptions`` no futuro.
      * ``config`` = entrada da tabela :data:`_BY_TYPE` ou :data:`_DEFAULT`.
    """
    eff = effective_property_type_for_cma(target)
    return eff, _BY_TYPE.get(eff, _DEFAULT)


__all__ = [
    "TypeConfig",
    "AreaField",
    "SearchStrategyName",
    "get_type_config",
    "effective_property_type_for_cma",
    "is_gated_community_house",
]
