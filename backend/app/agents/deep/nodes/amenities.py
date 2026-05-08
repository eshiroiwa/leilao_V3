"""Nó AMENITIES — distância à amenidade mais próxima.

Usa Google Places Nearby (gratuito até a quota mensal) para encontrar a
estação de metrô, escola e hospital mais próximas. Cada um é uma chamada
independente — rodamos em paralelo com ``asyncio.gather``.

Por que essas 3 categorias? São proxies sólidos de qualidade urbana
imediata e influenciam diretamente liquidez e teto de preço:

* metrô/transporte → mobilidade
* escola → demanda familiar
* hospital → serviços essenciais

Limite de raio: 5 km. Se a amenidade mais próxima estiver mais longe,
devolvemos ``None`` (importante: ``None`` ≠ 0; significa "não há nada
relevante perto").
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.agents.deep.schemas import AmenitiesResult
from app.core.logging import get_logger
from app.services.google_maps_service import GoogleMapsError, GoogleMapsService

logger = get_logger(__name__)

# Mapeamento amigável → tipos oficiais do Google Places API.
_PLACE_TYPES = {
    "metro": "subway_station",
    "school": "school",
    "hospital": "hospital",
}

DEFAULT_RADIUS_M = 5_000


async def _nearest(
    gmaps: GoogleMapsService,
    *,
    lat: float,
    lng: float,
    place_type: str,
    radius_m: int,
) -> dict[str, Any] | None:
    try:
        return await asyncio.to_thread(
            gmaps.nearest_place,
            lat=lat,
            lng=lng,
            place_type=place_type,
            radius_m=radius_m,
        )
    except GoogleMapsError as exc:
        logger.warning("deep.amenities.failed", type=place_type, error=str(exc))
        return None


async def fetch_amenities(
    *,
    gmaps: GoogleMapsService,
    lat: float,
    lng: float,
    radius_m: int = DEFAULT_RADIUS_M,
) -> AmenitiesResult:
    metro, school, hospital = await asyncio.gather(
        _nearest(gmaps, lat=lat, lng=lng, place_type=_PLACE_TYPES["metro"], radius_m=radius_m),
        _nearest(gmaps, lat=lat, lng=lng, place_type=_PLACE_TYPES["school"], radius_m=radius_m),
        _nearest(gmaps, lat=lat, lng=lng, place_type=_PLACE_TYPES["hospital"], radius_m=radius_m),
    )

    return AmenitiesResult(
        nearest_metro_m=metro["distance_m"] if metro else None,
        nearest_school_m=school["distance_m"] if school else None,
        nearest_hospital_m=hospital["distance_m"] if hospital else None,
        evidence={
            "radius_m": radius_m,
            "metro": metro,
            "school": school,
            "hospital": hospital,
        },
    )
