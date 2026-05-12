"""Cliente do Sistema Gerenciador de Séries Temporais (SGS) do BACEN.

API gratuita, sem autenticação. Endpoint público:

    https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados[/ultimos/{n}]?formato=json

Códigos relevantes para o balisador:

  * 11   — Selic taxa diária (% ao dia) → anualizamos
  * 12   — CDI taxa diária (% ao dia)   → anualizamos (referência primária)
  * 4189 — Selic acumulada no ano (% a.a.)
  * 433  — IPCA mensal (% no mês)       → acumulamos 12 meses
  * 192  — INCC-M mensal
  * 188  — IGP-M mensal

Uso no AGENTE 3: comparar o ROI anualizado com o CDI atual e gerar warning
quando o retorno do imóvel não bate sequer a renda fixa. Cache em memória
com TTL configurável — o BACEN publica diariamente, mas para anualização
o valor de qualquer dia recente vale.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Final

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class BacenServiceError(RuntimeError):
    """Falha ao consultar a API do BACEN SGS."""


# Códigos SGS expostos como constantes para evitar typos espalhados.
SGS_SELIC_DAILY: Final[int] = 11
SGS_CDI_DAILY: Final[int] = 12
SGS_IPCA_MONTHLY: Final[int] = 433
SGS_INCC_M_MONTHLY: Final[int] = 192
SGS_IGPM_MONTHLY: Final[int] = 188
# 25497: Taxa média mensal de juros — operações de crédito - Aquisição de
# imóveis - PF - SBPE - prefixado. Publicada mensalmente pelo BACEN.
SGS_REAL_ESTATE_LOAN_PF_MONTHLY: Final[int] = 25497

# 252 dias úteis num ano fiscal — convenção de mercado para anualizar
# taxas overnight (Selic/CDI). NÃO use 365 — daria taxa errada para
# instrumentos de renda fixa.
BUSINESS_DAYS_PER_YEAR: Final[int] = 252

# TTL do cache em segundos. CDI/Selic mudam só por decisão do Copom (~45
# dias); 6h é seguro mesmo no dia da reunião (publicação noturna).
_CACHE_TTL_SECONDS: Final[int] = 6 * 3600

_BASE_URL: Final[str] = "https://api.bcb.gov.br/dados/serie"


class BacenService:
    """Cliente síncrono para o SGS. Use ``get_cdi_annual()`` no caminho quente."""

    def __init__(self, *, timeout_s: float = 10.0) -> None:
        self._timeout_s = timeout_s
        # Cache: {(codigo, n_recent): (timestamp_unix, valor)}
        self._cache: dict[tuple[int, int], tuple[float, float]] = {}

    # ------------------------------------------------------------------ #
    # Camada baixa: requisição HTTP + cache por (código, n_recent).
    # ------------------------------------------------------------------ #
    def _fetch_last_value(self, codigo: int, *, n_recent: int = 1) -> float:
        """Retorna o último ``valor`` (float) da série ``codigo``.

        Cacheado por ``_CACHE_TTL_SECONDS``. Levanta :class:`BacenServiceError`
        em erro de rede, resposta vazia ou JSON malformado.
        """
        key = (codigo, n_recent)
        cached = self._cache.get(key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        url = f"{_BASE_URL}/bcdata.sgs.{codigo}/dados/ultimos/{n_recent}"
        params = {"formato": "json"}
        logger.info("bacen.sgs.fetch", codigo=codigo, n=n_recent)
        try:
            r = httpx.get(url, params=params, timeout=self._timeout_s)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            logger.error("bacen.sgs.http_error", codigo=codigo, error=str(exc))
            raise BacenServiceError(f"BACEN SGS HTTP erro: {exc}") from exc
        except ValueError as exc:
            logger.error("bacen.sgs.json_error", codigo=codigo, error=str(exc))
            raise BacenServiceError(f"BACEN SGS JSON inválido: {exc}") from exc

        if not isinstance(data, list) or not data:
            raise BacenServiceError(f"BACEN SGS {codigo}: resposta vazia")

        last = data[-1]
        try:
            # API devolve "1,234567" (vírgula decimal pt-BR).
            valor = float(str(last["valor"]).replace(",", "."))
        except (KeyError, TypeError, ValueError) as exc:
            raise BacenServiceError(
                f"BACEN SGS {codigo}: valor não parseável ({last})"
            ) from exc

        self._cache[key] = (time.time(), valor)
        return valor

    # ------------------------------------------------------------------ #
    # API pública — sempre devolve em FRAÇÃO ANUAL (0.135 = 13,5% a.a.).
    # ------------------------------------------------------------------ #
    def get_cdi_annual(self) -> float:
        """CDI anualizado (fração). Convenção 252 dias úteis.

        O SGS publica o CDI como taxa overnight em % ao dia. Para o usuário
        final faz sentido só a versão anualizada (compara com ROI a.a.).
        """
        daily_pct = self._fetch_last_value(SGS_CDI_DAILY)
        daily_frac = daily_pct / 100.0
        return (1.0 + daily_frac) ** BUSINESS_DAYS_PER_YEAR - 1.0

    def get_selic_annual(self) -> float:
        """Selic Over anualizada (fração). Costuma ser muito próxima do CDI."""
        daily_pct = self._fetch_last_value(SGS_SELIC_DAILY)
        daily_frac = daily_pct / 100.0
        return (1.0 + daily_frac) ** BUSINESS_DAYS_PER_YEAR - 1.0

    def get_avg_real_estate_loan_annual(self) -> float | None:
        """Taxa média anual de financiamento imobiliário PF (fração).

        Consulta a série 25497 (taxa média mensal de juros, aquisição de
        imóveis, PF, SBPE, prefixado) e anualiza via ``(1 + i_m)^12 − 1``.
        Devolve ``None`` em qualquer falha (BACEN fora do ar, JSON inválido,
        etc.) — o caller deve aplicar fallback (ex.: 11% a.a.).
        """
        try:
            monthly_pct = self._fetch_last_value(SGS_REAL_ESTATE_LOAN_PF_MONTHLY)
        except BacenServiceError as exc:
            logger.warning("bacen.real_estate_loan.fetch_failed", error=str(exc))
            return None
        monthly_frac = monthly_pct / 100.0
        if monthly_frac <= 0:
            return None
        return (1.0 + monthly_frac) ** 12 - 1.0

    def get_ipca_12m(self) -> float:
        """IPCA acumulado nos últimos 12 meses (fração).

        IPCA é publicado MENSALMENTE. Compomos as últimas 12 leituras:
        Π(1 + IPCA_mensal) − 1. Cada leitura mensal é cacheada em ``_cache``
        com TTL de 6h — o BACEN só atualiza a série uma vez por mês.
        """
        # 12 leituras mensais — composto.
        # NB: o endpoint ``/ultimos/12`` retorna 12 valores mas só
        # cacheamos por (codigo, n_recent), então uma chamada por mês basta.
        url = f"{_BASE_URL}/bcdata.sgs.{SGS_IPCA_MONTHLY}/dados/ultimos/12"
        cache_key = (SGS_IPCA_MONTHLY, 12)
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]
        try:
            r = httpx.get(url, params={"formato": "json"}, timeout=self._timeout_s)
            r.raise_for_status()
            rows = r.json()
        except httpx.HTTPError as exc:
            raise BacenServiceError(f"BACEN SGS IPCA HTTP erro: {exc}") from exc
        if not isinstance(rows, list) or len(rows) < 12:
            raise BacenServiceError("BACEN SGS IPCA: < 12 leituras retornadas")
        product = 1.0
        for row in rows:
            try:
                m_pct = float(str(row["valor"]).replace(",", "."))
            except (KeyError, TypeError, ValueError) as exc:
                raise BacenServiceError(
                    f"BACEN SGS IPCA: leitura inválida ({row})"
                ) from exc
            product *= 1.0 + m_pct / 100.0
        accumulated = product - 1.0
        self._cache[cache_key] = (time.time(), accumulated)
        return accumulated


@lru_cache(maxsize=1)
def get_bacen_service() -> BacenService:
    """Singleton do BacenService. Cache de TTL fica DENTRO do service, não aqui."""
    return BacenService()


__all__ = [
    "BacenService",
    "BacenServiceError",
    "get_bacen_service",
    "SGS_CDI_DAILY",
    "SGS_SELIC_DAILY",
    "SGS_IPCA_MONTHLY",
    "SGS_INCC_M_MONTHLY",
    "SGS_IGPM_MONTHLY",
    "SGS_REAL_ESTATE_LOAN_PF_MONTHLY",
    "BUSINESS_DAYS_PER_YEAR",
]
