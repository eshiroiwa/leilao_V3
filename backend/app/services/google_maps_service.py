"""Wrapper para Google Maps Platform: Address Validation + Geocoding.

A Address Validation API normaliza o endereço (corrige erros, completa CEP),
o Geocoding API garante coordenadas e ``place_id`` consistentes.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import googlemaps  # type: ignore[import-untyped]
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

ADDRESS_VALIDATION_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"


class GoogleMapsError(RuntimeError):
    """Erro genérico ao chamar Google Maps Platform."""


class GoogleMapsService:
    """Cliente unificado para Address Validation + Geocoding."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._gmaps = googlemaps.Client(key=api_key)

    # --------------------------------------------------------------------- #
    # Address Validation API
    # --------------------------------------------------------------------- #
    def validate_address(
        self,
        *,
        address_lines: list[str],
        region_code: str = "BR",
        postal_code: str | None = None,
        locality: str | None = None,
        administrative_area: str | None = None,
    ) -> dict[str, Any]:
        """Chama Address Validation e retorna o JSON ``result`` cru."""
        payload: dict[str, Any] = {
            "address": {
                "regionCode": region_code,
                "addressLines": address_lines,
            }
        }
        if postal_code:
            payload["address"]["postalCode"] = postal_code
        if locality:
            payload["address"]["locality"] = locality
        if administrative_area:
            payload["address"]["administrativeArea"] = administrative_area

        logger.info("gmaps.validate.start", address_lines=address_lines)
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    ADDRESS_VALIDATION_URL,
                    params={"key": self._api_key},
                    json=payload,
                )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("gmaps.validate.http_error", error=str(exc))
            raise GoogleMapsError(f"Address Validation falhou: {exc}") from exc

        result = data.get("result", {})
        logger.info(
            "gmaps.validate.ok",
            verdict=result.get("verdict", {}),
        )
        return result

    # --------------------------------------------------------------------- #
    # Geocoding API
    # --------------------------------------------------------------------- #
    def geocode(self, address: str, *, region: str = "br") -> dict[str, Any] | None:
        """Geocodifica ``address`` e retorna o melhor resultado (ou None)."""
        logger.info("gmaps.geocode.start", address=address)
        try:
            results = self._gmaps.geocode(address, region=region)
        except Exception as exc:  # SDK
            logger.error("gmaps.geocode.exception", error=str(exc))
            raise GoogleMapsError(f"Geocoding falhou: {exc}") from exc

        if not results:
            logger.warning("gmaps.geocode.no_results", address=address)
            return None

        best = results[0]
        logger.info(
            "gmaps.geocode.ok",
            place_id=best.get("place_id"),
            location_type=best.get("geometry", {}).get("location_type"),
        )
        return best

    @staticmethod
    def extract_lat_lng(geocode_result: dict[str, Any]) -> tuple[float, float] | None:
        loc = (geocode_result or {}).get("geometry", {}).get("location") or {}
        if "lat" in loc and "lng" in loc:
            return float(loc["lat"]), float(loc["lng"])
        return None

    # --------------------------------------------------------------------- #
    # Places — Nearby Search (usado pelo AGENTE 4 para amenidades)
    # --------------------------------------------------------------------- #
    def nearest_place(
        self,
        *,
        lat: float,
        lng: float,
        place_type: str,
        radius_m: int = 5_000,
    ) -> dict[str, Any] | None:
        """Retorna a amenidade mais próxima do tipo ``place_type``.

        ``place_type`` deve ser um valor da lista oficial de tipos do
        Google Places (ex.: ``subway_station``, ``school``, ``hospital``).

        Faz o ``places_nearby`` ordenado por distância (rank_by="distance"),
        pega o primeiro resultado e calcula a distância até o ponto de
        origem em metros (Haversine).
        """
        logger.info(
            "gmaps.places.nearest.start",
            place_type=place_type,
            lat=lat,
            lng=lng,
        )
        try:
            res = self._gmaps.places_nearby(
                location=(lat, lng),
                rank_by="distance",
                type=place_type,
            )
        except Exception as exc:
            logger.error(
                "gmaps.places.nearest.exception",
                place_type=place_type,
                error=str(exc),
            )
            raise GoogleMapsError(f"Places nearby falhou: {exc}") from exc

        results = res.get("results") or []
        if not results:
            return None

        best = results[0]
        loc = (best.get("geometry") or {}).get("location") or {}
        if "lat" not in loc or "lng" not in loc:
            return None

        from math import asin, cos, radians, sin, sqrt

        plat = float(loc["lat"])
        plng = float(loc["lng"])
        r = 6_371_000.0
        p1 = radians(lat)
        p2 = radians(plat)
        dphi = radians(plat - lat)
        dlam = radians(plng - lng)
        a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlam / 2) ** 2
        distance_m = int(2 * r * asin(sqrt(a)))

        if distance_m > radius_m:
            return None

        return {
            "name": best.get("name"),
            "place_id": best.get("place_id"),
            "lat": plat,
            "lng": plng,
            "distance_m": distance_m,
            "vicinity": best.get("vicinity"),
        }


@lru_cache(maxsize=1)
def get_google_maps_service() -> GoogleMapsService:
    settings = get_settings()
    return GoogleMapsService(api_key=settings.google_maps_api_key.get_secret_value())
