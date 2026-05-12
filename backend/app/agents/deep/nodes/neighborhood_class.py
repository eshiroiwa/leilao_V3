"""Nó NEIGHBORHOOD CLASS — classifica o bairro-alvo (tier A/B/C/D) e sugere
3 bairros concorrentes com ppm² semelhante e geograficamente próximos.

Sem rede: usa apenas listings já indexados no Supabase (raio 10 km) e o
FipeZAP mensal da cidade (quando disponível). Custo: ~1 query Supabase
adicional, sem LLM.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any

from app.agents.deep.schemas import (
    NeighborhoodClassResult,
    NeighborhoodCompetitor,
    NeighborhoodTier,
    NeighborhoodTierLabel,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Raio para buscar bairros candidatos a concorrentes. 10km cobre bairros
# vizinhos numa metrópole e o município inteiro em cidades médias.
COMPETITORS_RADIUS_M = 10_000

# Mínimo de listings dentro de um bairro para que sua mediana de ppm² seja
# considerada estável (filtra ruído de bairros com 1-2 anúncios).
MIN_LISTINGS_PER_GROUP = 5

TIER_THRESHOLDS: tuple[tuple[float, NeighborhoodTier, NeighborhoodTierLabel], ...] = (
    (1.3, "A", "premium"),
    (1.0, "B", "médio-alto"),
    (0.7, "C", "médio"),
    (0.0, "D", "popular"),
)


def _ppm2(listing: dict[str, Any]) -> float | None:
    price = listing.get("listed_price")
    area = listing.get("area_total_m2")
    try:
        if price and area and float(area) > 0:
            return float(price) / float(area)
    except (TypeError, ValueError):
        return None
    return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _classify_tier(ratio: float) -> tuple[NeighborhoodTier, NeighborhoodTierLabel]:
    for threshold, tier, label in TIER_THRESHOLDS:
        if ratio >= threshold:
            return tier, label
    return "D", "popular"  # ratio negativo? defensivo


def classify_neighborhood(
    *,
    neighborhood: str | None,
    lat: float,
    lng: float,
    supabase: Any,
    city_ppm2_brl: float | None,
    property_type: str | None = None,
) -> NeighborhoodClassResult:
    """Calcula tier do bairro-alvo + 3 bairros concorrentes.

    ``city_ppm2_brl`` deve vir do FipeZAP (``city_ppm2_stats``). Quando
    ausente, cai para a mediana global dos listings em 10 km (proxy).
    Falha silenciosa: erro de I/O → retorna result com tudo None e
    confidence=LOW.
    """
    if not neighborhood:
        return NeighborhoodClassResult(
            confidence="LOW",
            evidence={"reason": "bairro_alvo_desconhecido"},
        )

    try:
        listings = supabase.find_listings_near(
            lat=lat,
            lng=lng,
            radius_m=COMPETITORS_RADIUS_M,
            property_type=property_type,
            limit=1000,
        )
    except Exception as exc:
        logger.warning("deep.neighborhood_class.fetch_failed", error=str(exc))
        return NeighborhoodClassResult(
            confidence="LOW", evidence={"reason": "fetch_failed"},
        )

    target_name_norm = neighborhood.strip().lower()
    groups: dict[str, list[dict[str, Any]]] = {}
    ppm2_all: list[float] = []
    for listing in listings:
        bairro = (listing.get("neighborhood") or "").strip()
        if not bairro:
            continue
        ppm2 = _ppm2(listing)
        if ppm2 is None:
            continue
        groups.setdefault(bairro, []).append({**listing, "_ppm2": ppm2})
        ppm2_all.append(ppm2)

    # Mediana global dos listings = fallback quando FipeZAP ausente.
    fallback_city_ppm2 = median(ppm2_all) if ppm2_all else None
    reference_city_ppm2 = city_ppm2_brl if city_ppm2_brl else fallback_city_ppm2

    # Estatísticas do bairro-alvo (case-insensitive match).
    target_group: list[dict[str, Any]] | None = None
    target_key: str | None = None
    for key, group in groups.items():
        if key.strip().lower() == target_name_norm:
            target_group = group
            target_key = key
            break

    if target_group is None or len(target_group) < MIN_LISTINGS_PER_GROUP:
        n_target = len(target_group) if target_group else 0
        logger.info(
            "deep.neighborhood_class.insufficient_target",
            neighborhood=neighborhood,
            n_listings=n_target,
        )
        return NeighborhoodClassResult(
            target_ppm2_median=None,
            city_ppm2_brl=reference_city_ppm2,
            confidence="LOW",
            evidence={
                "reason": "amostra_rasa_no_bairro_alvo",
                "n_listings_in_target": n_target,
                "min_required": MIN_LISTINGS_PER_GROUP,
            },
        )

    target_ppm2_median = median(item["_ppm2"] for item in target_group)
    ratio = (
        target_ppm2_median / reference_city_ppm2
        if reference_city_ppm2 and reference_city_ppm2 > 0
        else None
    )
    tier, tier_label = _classify_tier(ratio) if ratio else (None, None)

    # Centróide do bairro-alvo para medir distância aos concorrentes.
    def _centroid(group: list[dict[str, Any]]) -> tuple[float, float] | None:
        coords = [
            (float(g["latitude"]), float(g["longitude"]))
            for g in group
            if g.get("latitude") is not None and g.get("longitude") is not None
        ]
        if not coords:
            return None
        return (
            sum(c[0] for c in coords) / len(coords),
            sum(c[1] for c in coords) / len(coords),
        )

    target_centroid = _centroid(target_group)

    competitors: list[NeighborhoodCompetitor] = []
    for key, group in groups.items():
        if key == target_key:
            continue
        if len(group) < MIN_LISTINGS_PER_GROUP:
            continue
        group_ppm2 = median(item["_ppm2"] for item in group)
        cent = _centroid(group)
        if cent and target_centroid:
            dist_km = _haversine_km(
                target_centroid[0], target_centroid[1], cent[0], cent[1]
            )
        else:
            dist_km = 0.0
        competitors.append(
            NeighborhoodCompetitor(
                name=key,
                distance_km=round(dist_km, 2),
                ppm2_median=round(group_ppm2, 2),
                n_listings=len(group),
            )
        )

    # Top 3 com ppm² mais próximo do bairro-alvo.
    competitors.sort(key=lambda c: abs(c.ppm2_median - target_ppm2_median))
    top_competitors = competitors[:3]

    # Confidence: HIGH com FipeZAP + amostra robusta; MEDIUM caindo para
    # fallback de mediana global; LOW só nos casos degenerados acima.
    if city_ppm2_brl and len(target_group) >= MIN_LISTINGS_PER_GROUP * 2:
        confidence = "HIGH"
    elif reference_city_ppm2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    result = NeighborhoodClassResult(
        tier=tier,
        tier_label=tier_label,
        target_ppm2_median=round(target_ppm2_median, 2),
        city_ppm2_brl=round(reference_city_ppm2, 2) if reference_city_ppm2 else None,
        ratio=round(ratio, 3) if ratio else None,
        competing_neighborhoods=top_competitors,
        confidence=confidence,
        evidence={
            "n_listings_total": sum(len(g) for g in groups.values()),
            "n_bairros_amostrados": len(
                [g for g in groups.values() if len(g) >= MIN_LISTINGS_PER_GROUP]
            ),
            "n_listings_in_target": len(target_group),
            "city_ppm2_source": "fipezap" if city_ppm2_brl else "fallback_global",
            "radius_m": COMPETITORS_RADIUS_M,
        },
    )
    logger.info(
        "deep.neighborhood_class.done",
        neighborhood=neighborhood,
        tier=result.tier,
        ratio=result.ratio,
        n_competitors=len(top_competitors),
    )
    return result


__all__ = ["classify_neighborhood", "COMPETITORS_RADIUS_M"]
