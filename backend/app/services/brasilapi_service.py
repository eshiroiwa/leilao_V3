"""Cliente para BrasilAPI (CEP v2) + fallback ViaCEP.

Ambas APIs são gratuitas, sem auth. BrasilAPI v2 é preferida porque retorna
coordenadas (lat/lng via OpenStreetMap) além dos campos de endereço; ViaCEP
fica como fallback (só campos de endereço, sem coordenadas).

Uso no AGENTE 1: caminho C de geocoding quando o Google Maps falha em A e B
(validation rejeitada + fallback por CEP no Google também). Devolve uma
"melhor estimativa" para o pipeline conseguir prosseguir com city/state
mesmo sem rooftop accuracy.

Endpoints:
    https://brasilapi.com.br/api/cep/v2/{cep}
    https://viacep.com.br/ws/{cep}/json/
"""

from __future__ import annotations

import re
import time
from functools import lru_cache
from typing import Final

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class BrasilApiError(RuntimeError):
    """Falha ao consultar BrasilAPI / ViaCEP."""


_BRASILAPI_URL: Final[str] = "https://brasilapi.com.br/api/cep/v2"
_VIACEP_URL: Final[str] = "https://viacep.com.br/ws"
_CACHE_TTL_SECONDS: Final[int] = 24 * 3600  # 1 dia — CEPs raramente mudam


def _digits_only(cep: str) -> str:
    """Normaliza CEP para 8 dígitos (sem hífen/espaços)."""
    return re.sub(r"\D", "", cep or "")


class BrasilApiService:
    """Resolução de CEP com hierarquia BrasilAPI → ViaCEP.

    O resultado normalizado é um dict com chaves:
      * ``cep``           (str — 8 dígitos)
      * ``street``        (str | None)
      * ``neighborhood``  (str | None)
      * ``city``          (str | None)
      * ``state``         (str | None — UF 2 letras maiúsculas)
      * ``lat``           (float | None — só com BrasilAPI v2)
      * ``lng``           (float | None — idem)
      * ``source``        ("brasilapi" | "viacep")
    """

    def __init__(self, *, timeout_s: float = 5.0) -> None:
        self._timeout_s = timeout_s
        # Cache: {cep_digits: (timestamp_unix, dict | None)}
        self._cache: dict[str, tuple[float, dict | None]] = {}

    # ------------------------------------------------------------------ #
    def fetch_cep(self, cep: str) -> dict | None:
        """Resolve um CEP. Tenta BrasilAPI; se falhar/timeout, tenta ViaCEP.
        Devolve dict normalizado ou None quando ambas as fontes falharem
        (NÃO levanta — chamador trata como "fallback indisponível")."""
        digits = _digits_only(cep)
        if len(digits) != 8:
            return None

        cached = self._cache.get(digits)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        result = self._fetch_brasilapi(digits)
        if result is None:
            result = self._fetch_viacep(digits)

        self._cache[digits] = (time.time(), result)
        return result

    # ------------------------------------------------------------------ #
    def _fetch_brasilapi(self, digits: str) -> dict | None:
        url = f"{_BRASILAPI_URL}/{digits}"
        logger.info("brasilapi.cep.fetch", cep=digits)
        try:
            r = httpx.get(url, timeout=self._timeout_s)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("brasilapi.cep.error", cep=digits, error=str(exc))
            return None

        # Schema v2 inclui ``location.coordinates.latitude/longitude``
        # quando BrasilAPI conseguiu resolver via OpenStreetMap.
        coords = ((data.get("location") or {}).get("coordinates") or {})
        lat = _parse_float(coords.get("latitude"))
        lng = _parse_float(coords.get("longitude"))
        state = (data.get("state") or "").strip().upper()
        return {
            "cep": digits,
            "street": (data.get("street") or "").strip() or None,
            "neighborhood": (data.get("neighborhood") or "").strip() or None,
            "city": (data.get("city") or "").strip() or None,
            "state": state[:2] or None,
            "lat": lat,
            "lng": lng,
            "source": "brasilapi",
        }

    # ------------------------------------------------------------------ #
    def _fetch_viacep(self, digits: str) -> dict | None:
        url = f"{_VIACEP_URL}/{digits}/json"
        logger.info("viacep.cep.fetch", cep=digits)
        try:
            r = httpx.get(url, timeout=self._timeout_s)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("viacep.cep.error", cep=digits, error=str(exc))
            return None

        if not isinstance(data, dict) or data.get("erro"):
            return None

        state = (data.get("uf") or "").strip().upper()
        return {
            "cep": digits,
            "street": (data.get("logradouro") or "").strip() or None,
            "neighborhood": (data.get("bairro") or "").strip() or None,
            "city": (data.get("localidade") or "").strip() or None,
            "state": state[:2] or None,
            "lat": None,  # ViaCEP não fornece coordenadas
            "lng": None,
            "source": "viacep",
        }


def _parse_float(value) -> float | None:  # type: ignore[no-untyped-def]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def get_brasilapi_service() -> BrasilApiService:
    return BrasilApiService()


__all__ = [
    "BrasilApiService",
    "BrasilApiError",
    "get_brasilapi_service",
]
