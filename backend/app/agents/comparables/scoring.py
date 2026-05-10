"""Scoring de comparáveis: similaridade (peso) e confiabilidade (filtro).

Funções puras, sem I/O. Receba dicts/floats e devolva floats — testáveis sem
nenhum mock. Pesos default são razoáveis para o mercado brasileiro mediano;
podem ser tunados via :class:`TypeConfig` (``type_config.py``) por tipo de
imóvel.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from app.agents.comparables.pricing import effective_target_area_m2
from app.agents.comparables.type_config import TypeConfig, get_type_config

# ---------------------------------------------------------------------------
# Distância (Haversine) — sem dependências externas.
# ---------------------------------------------------------------------------
_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância em metros entre dois pontos (lat/lng em graus)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_M * c


# ---------------------------------------------------------------------------
# Similaridade (0–1): peso do comparável no cálculo final.
# ---------------------------------------------------------------------------
# Pesos. ``condo`` (mesmo prédio) é o sinal mais forte que existe — ganha
# 0.25 e desloca peso de distância/área (estes ainda dominam quando não há
# condo_name). Soma == 1.0.
#
# Tipo (apartamento/casa/etc.) entra como hard-filter no ``node_score_similarity``;
# não duplica peso aqui.
SIMILARITY_WEIGHTS: dict[str, float] = {
    "distance": 0.30,
    "area": 0.25,
    "condo": 0.25,
    "bedrooms": 0.10,
    "parking": 0.10,
}

# Distância "característica" para o decay exponencial (~63% em 1.5 km).
_DISTANCE_TAU_M = 1500.0
# Sigma default da gaussiana de área (apartamento). Outros tipos vêm
# da :class:`TypeConfig` — este valor é usado só quando não há config.
_AREA_SIGMA_DEFAULT = 0.15


def _distance_score(distance_m: float | None) -> float:
    if distance_m is None or distance_m < 0:
        return 0.0
    return math.exp(-distance_m / _DISTANCE_TAU_M)


def _area_score(
    target_area: float | None,
    comp_area: float | None,
    *,
    sigma: float = _AREA_SIGMA_DEFAULT,
) -> float:
    if not target_area or not comp_area or target_area <= 0 or comp_area <= 0:
        return 0.0
    diff = abs(comp_area - target_area) / target_area
    return math.exp(-((diff / sigma) ** 2) / 2)


def _resolve_concrete_area_field(
    target: dict[str, Any], area_field: str
) -> str:
    """Resolve ``"auto"`` → "built" | "useful" | "total" usando o
    ``property_type`` do TARGET. Outros valores passam direto.

    Por que olhar só o target: em produção, ``node_score_similarity``
    descarta comparáveis de tipo diferente, então target e comp são
    do mesmo tipo. Mas a comparação de ÁREA é a mesma "âncora
    conceitual" — comparar `built` do target com `total` do comp
    misturaria coisas. Resolver a chave UMA vez a partir do target e
    aplicá-la dos dois lados é mais robusto."""
    if area_field != "auto":
        return area_field
    _, source = effective_target_area_m2(target)
    if source == "area_built_m2":
        return "built"
    if source == "area_useful_m2":
        return "useful"
    if source == "area_total_m2":
        return "total"
    return "total"  # último recurso conservador


def _read_area(row: dict[str, Any], concrete_field: str) -> float | None:
    """Lê a área do ``row`` no campo concreto ("built"/"useful"/"total"),
    com fallback agressivo (built → useful → total) para evitar que o
    filtro fique inerte quando portais reportam só ``area_total_m2``.

    Por que cair em ``total`` como último recurso: chavesnamao,
    vivareal e outros frequentemente expõem só UM número de área no
    anúncio (ex.: "casa 200m²"). Nosso parser coloca em
    ``area_total_m2``. Sem fallback, o filtro de área estaria comparando
    ``None`` (built do listing) com 145 (built do target) e retornaria
    ``None`` — efetivamente ignorando o filtro. Pior, listings
    "casa 50m²" passariam silenciosamente.

    Trade-off: pode comparar "construído do target" com "terreno do
    comp" se o portal reportar terreno como área. Mas isso é raro
    (anúncios de CASA reportam construído; anúncios de TERRENO são
    explicitamente terrenos, e o filtro de tipo já descarta) e
    melhor que a alternativa (filtro inerte).
    """

    def _f(key: str) -> float | None:
        v = row.get(key)
        try:
            fv = float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return None
        return fv if fv > 0 else None

    if concrete_field == "built":
        return _f("area_built_m2") or _f("area_useful_m2") or _f("area_total_m2")
    if concrete_field == "useful":
        return _f("area_useful_m2") or _f("area_built_m2") or _f("area_total_m2")
    if concrete_field == "total":
        return _f("area_total_m2") or _f("area_built_m2") or _f("area_useful_m2")
    return effective_target_area_m2(row)[0]


def _count_score(target: int | None, comp: int | None) -> float:
    if target is None or comp is None:
        return 0.5  # neutralidade quando faltar dado
    return 1.0 / (1.0 + abs(comp - target))


def _type_score(target_type: str | None, comp_type: str | None) -> float:
    if not target_type or not comp_type:
        return 0.0
    return 1.0 if target_type.strip().lower() == comp_type.strip().lower() else 0.0


def normalize_condo_name(name: str | None) -> str:
    """Normaliza nome de condomínio para comparação tolerante.

    Remove acentos, pontuação, prefixos genéricos ("edificio", "residencial",
    "condominio"), lowercase e colapsa espaços. Ex.::

        "Residencial Vila Verde"  → "vila verde"
        "EDIFÍCIO PARK Crispim"   → "park crispim"
        "Cond. Cristal das Águas" → "cristal das aguas"
    """
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", no_accents).strip().lower()
    tokens = cleaned.split()
    while tokens and tokens[0] in _CONDO_PREFIXES:
        tokens = tokens[1:]
    return " ".join(tokens)


_CONDO_PREFIXES: frozenset[str] = frozenset(
    {
        "edificio", "edif", "ed",
        "residencial", "res",
        "condominio", "cond",
        "conjunto",
    }
)


def condo_match_score(
    target_condo: str | None, listing_condo: str | None
) -> float:
    """Retorna 1.0 se os nomes batem (após normalização), 0.0 senão.

    Match é simétrico e tolerante a:

      * acentos, pontuação, capitalização;
      * prefixos genéricos ("Edifício", "Residencial", "Cond.", etc.);
      * tokens extras em uma das pontas (ex.: ``"Park Crispim Apto 12"``
        casa com ``"Park Crispim"`` quando todos os tokens da menor estão
        contidos na maior).

    Quando um dos lados está vazio, retorna 0.0 (nunca puxa o peso pra
    cima sem evidência).
    """
    a = normalize_condo_name(target_condo)
    b = normalize_condo_name(listing_condo)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    # Match "contido": todos os tokens do menor estão no maior. Exige
    # pelo menos 2 tokens para evitar falsos positivos com nomes de 1
    # palavra ("Park", "Solar") que aparecem em vários prédios.
    smaller, larger = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(smaller) >= 2 and smaller.issubset(larger):
        return 1.0
    return 0.0


def similarity_score(
    target: dict[str, Any],
    comp: dict[str, Any],
    *,
    config: TypeConfig | None = None,
) -> float:
    """Calcula similaridade 0–1 entre o imóvel-alvo e um candidato.

    A precisão da componente de ÁREA depende do ``area_field`` da
    :class:`TypeConfig`:

      * casa: usa ``area_built_m2`` (E5) — comparar terreno entre casas
        é errado, mansão de 1.000m² de terreno NÃO é comparável a casa
        de 250m² de terreno só porque "ambas tem 150m² construídos".
      * apartamento: built primeiro (matrícula sem frações comuns).
      * terreno: ``area_total_m2`` (m² de terreno é a unidade do
        mercado).
      * comercial/galpão: ``area_useful_m2`` (área locável).

    Sigma da gaussiana também vem da config — apartamentos são
    uniformes (0.15), rurais bem heterogêneos (0.50). Quando ``config``
    não é passado, a config é resolvida do ``target.property_type``.
    """
    if config is None:
        _, config = get_type_config(target)

    distance_m = None
    if (
        target.get("latitude") is not None
        and target.get("longitude") is not None
        and comp.get("latitude") is not None
        and comp.get("longitude") is not None
    ):
        distance_m = haversine_m(
            float(target["latitude"]),
            float(target["longitude"]),
            float(comp["latitude"]),
            float(comp["longitude"]),
        )

    concrete_field = _resolve_concrete_area_field(target, config.area_field)
    target_area = _read_area(target, concrete_field)
    comp_area = _read_area(comp, concrete_field)

    parts: dict[str, float] = {
        "distance": _distance_score(distance_m),
        "area": _area_score(target_area, comp_area, sigma=config.area_sigma),
        "condo": condo_match_score(target.get("condo_name"), comp.get("condo_name")),
        "bedrooms": _count_score(target.get("bedrooms"), comp.get("bedrooms")),
        "parking": _count_score(target.get("parking_spaces"), comp.get("parking_spaces")),
    }
    score = sum(SIMILARITY_WEIGHTS[k] * v for k, v in parts.items())
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Auto-self detection: o "comparável" é, na verdade, o ANÚNCIO DO PRÓPRIO
# IMÓVEL DO LEILÃO num portal de mercado.
#
# Cenário comum: lotes Caixa eventualmente são listados em portais
# (chavesnamao, vivareal etc.) com o preço do leilão. Quando o pipeline
# acha esse anúncio durante a busca, ele entra na CMA com similaridade
# alta (mesmo endereço, mesma área, mesmo imóvel) — e PUXA o R$/m² do
# bairro PARA BAIXO porque o lance Caixa é abaixo do mercado.
#
# Heurística: três sinais simultâneos.
#   1. Distância < ``auto_self_distance_m`` (típico ~50m: o geocoding
#      por rua bate com erro de algumas dezenas de metros).
#   2. |Δ área|/area_target < ``auto_self_area_pct`` (~2%: tolerância
#      pra arredondamento — duas casas idênticas no mesmo terreno é raro).
#   3. |Δ preço|/preço_referência < ``auto_self_price_pct`` (~2%) onde
#      o preço de referência é ``minimum_bid_first``, ``minimum_bid_second``
#      ou ``appraisal_value``.
#
# Os três sinais simultâneos têm taxa de falso positivo essencialmente
# zero — são literalmente "mesmo imóvel anunciado".
# ---------------------------------------------------------------------------
def is_likely_target_self(
    target: dict[str, Any],
    comp: dict[str, Any],
    *,
    config: TypeConfig | None = None,
) -> bool:
    """True se o ``comp`` é, com alta probabilidade, o anúncio do
    próprio imóvel do leilão.

    Quando True, o caller deve marcar o comparável com
    ``rejection_reason="auto_self: anúncio do próprio imóvel do leilão"``
    e excluí-lo da CMA. NÃO use os dados desse listing — o "preço" dele
    é o preço do leilão (abaixo de mercado por design).
    """
    if config is None:
        _, config = get_type_config(target)

    # 1) distância
    if not (
        target.get("latitude") is not None
        and target.get("longitude") is not None
        and comp.get("latitude") is not None
        and comp.get("longitude") is not None
    ):
        # Sem geo, não há base pra afirmar self. Conservador: False.
        return False
    d = haversine_m(
        float(target["latitude"]),
        float(target["longitude"]),
        float(comp["latitude"]),
        float(comp["longitude"]),
    )
    if d > config.auto_self_distance_m:
        return False

    # 2) área (usa o mesmo campo decidido pela config — built p/ casa, etc.)
    concrete_field = _resolve_concrete_area_field(target, config.area_field)
    target_area = _read_area(target, concrete_field)
    comp_area = _read_area(comp, concrete_field)
    if not target_area or not comp_area:
        return False
    if abs(comp_area - target_area) / target_area > config.auto_self_area_pct:
        return False

    # 3) preço bate com algum dos valores do leilão?
    try:
        comp_price = float(comp.get("listed_price") or 0.0)
    except (TypeError, ValueError):
        return False
    if comp_price <= 0:
        return False

    refs = (
        target.get("minimum_bid_first"),
        target.get("minimum_bid_second"),
        target.get("appraisal_value"),
    )
    for ref in refs:
        if ref is None:
            continue
        try:
            ref_f = float(ref)
        except (TypeError, ValueError):
            continue
        if ref_f <= 0:
            continue
        if abs(comp_price - ref_f) / ref_f <= config.auto_self_price_pct:
            return True
    return False


# ---------------------------------------------------------------------------
# Hard filter de área: rejeita comparáveis fora da faixa de tolerância
# definida em :class:`TypeConfig`. Retorna ``None`` quando OK ou uma
# string com a razão de rejeição.
# ---------------------------------------------------------------------------
def area_outside_tolerance(
    target: dict[str, Any],
    comp: dict[str, Any],
    *,
    config: TypeConfig | None = None,
    relaxed: bool = False,
) -> str | None:
    """Verifica se a |Δ área| relativa ultrapassa o limite da config.

    Retorna ``None`` se OK, ou uma frase explicativa pra ir como
    ``rejection_reason``. Se faltar área em qualquer um dos dois lados,
    retorna ``None`` (não rejeita por falta de dado — o filtro de
    "sem preço/área" do score cobre o caso totalmente vazio).

    ``relaxed=True`` usa ``area_hard_max_relaxed`` em vez de
    ``area_hard_max`` — disparado pelo ``check_minimum`` quando o
    pipeline esgotou raio/estratégia mas ainda tem comparáveis demais.
    """
    if config is None:
        _, config = get_type_config(target)

    concrete_field = _resolve_concrete_area_field(target, config.area_field)
    target_area = _read_area(target, concrete_field)
    comp_area = _read_area(comp, concrete_field)
    if not target_area or not comp_area:
        return None

    diff_pct = abs(comp_area - target_area) / target_area
    threshold = config.area_hard_max_relaxed if relaxed else config.area_hard_max
    if diff_pct > threshold:
        return (
            f"area_outside_tolerance: |Δ|={diff_pct:.1%} > "
            f"{threshold:.0%} ({concrete_field})"
        )
    return None


# ---------------------------------------------------------------------------
# Confiabilidade do anúncio (0–1): se < threshold, descartamos.
# ---------------------------------------------------------------------------
RELIABILITY_THRESHOLD = 0.50

_GEO_CONFIDENCE_BONUS: dict[str, float] = {
    "HIGH": 0.20,
    "MEDIUM": 0.10,
    "LOW": 0.00,
    "POSTAL_CODE": 0.00,
    "REJECTED": 0.00,  # cap rígido aplicado abaixo (anúncio sem geo confiável
                       # NUNCA pode atravessar o threshold).
}

# Caps duros: anúncio com geo ruim NÃO pode ter alta confiabilidade,
# mesmo tendo todos os outros sinais positivos.
_GEO_CONFIDENCE_CAP: dict[str, float] = {
    "REJECTED": 0.30,
    "POSTAL_CODE": 0.55,
}

_ADVERTISER_BONUS: dict[str, float] = {
    "imobiliaria": 0.05,
    "construtora": 0.05,
    "autonomo": 0.0,
    "desconhecido": 0.0,
}


def reliability_score(listing: dict[str, Any]) -> float:
    """Sinaliza quão confiável é um anúncio para virar comparável.

    Retorna 0–1 (clamp). Use ``listing["reliability_score"] >= RELIABILITY_THRESHOLD``
    como filtro.
    """
    score = 0.0

    # Endereço com rua identificável (não vazio, não 'sem informação')
    street = (listing.get("street") or "").strip().lower()
    if street and street not in {"sem informação", "n/d", "nd"}:
        score += 0.25

    score += _GEO_CONFIDENCE_BONUS.get(listing.get("geocoding_confidence") or "", 0.0)

    if listing.get("area_total_m2"):
        score += 0.15
    if listing.get("bedrooms") is not None and listing.get("bathrooms") is not None:
        score += 0.10
    if (listing.get("photos_count") or 0) >= 3:
        score += 0.10
    if listing.get("listed_price"):
        score += 0.10  # tem que ter preço, óbvio, mas o sinal positivo entra

    score += _ADVERTISER_BONUS.get(listing.get("advertiser_type") or "", 0.0)

    score = max(0.0, min(1.0, score))

    cap = _GEO_CONFIDENCE_CAP.get(listing.get("geocoding_confidence") or "")
    if cap is not None:
        score = min(score, cap)

    return score


__all__ = [
    "haversine_m",
    "similarity_score",
    "reliability_score",
    "condo_match_score",
    "normalize_condo_name",
    "is_likely_target_self",
    "area_outside_tolerance",
    "RELIABILITY_THRESHOLD",
    "SIMILARITY_WEIGHTS",
]
