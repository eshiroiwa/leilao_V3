"""Scoring de comparáveis: similaridade (peso) e confiabilidade (filtro).

Funções puras, sem I/O. Receba dicts/floats e devolva floats — testáveis sem
nenhum mock. Pesos default são razoáveis para o mercado brasileiro mediano;
podem ser tunados em ``Settings`` no futuro.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

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
# Sigma da gaussiana de área, em fração (15% = 0.15).
_AREA_SIGMA = 0.15


def _distance_score(distance_m: float | None) -> float:
    if distance_m is None or distance_m < 0:
        return 0.0
    return math.exp(-distance_m / _DISTANCE_TAU_M)


def _area_score(target_area: float | None, comp_area: float | None) -> float:
    if not target_area or not comp_area or target_area <= 0 or comp_area <= 0:
        return 0.0
    diff = abs(comp_area - target_area) / target_area
    return math.exp(-((diff / _AREA_SIGMA) ** 2) / 2)


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


def similarity_score(target: dict[str, Any], comp: dict[str, Any]) -> float:
    """Calcula similaridade 0–1 entre o imóvel-alvo e um candidato.

    Espera dicts com chaves ``latitude``, ``longitude``, ``area_total_m2``,
    ``bedrooms``, ``parking_spaces``, ``condo_name`` (todas opcionais).
    """
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

    parts: dict[str, float] = {
        "distance": _distance_score(distance_m),
        "area": _area_score(target.get("area_total_m2"), comp.get("area_total_m2")),
        "condo": condo_match_score(target.get("condo_name"), comp.get("condo_name")),
        "bedrooms": _count_score(target.get("bedrooms"), comp.get("bedrooms")),
        "parking": _count_score(target.get("parking_spaces"), comp.get("parking_spaces")),
    }
    score = sum(SIMILARITY_WEIGHTS[k] * v for k, v in parts.items())
    return max(0.0, min(1.0, score))


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
    "RELIABILITY_THRESHOLD",
    "SIMILARITY_WEIGHTS",
]
