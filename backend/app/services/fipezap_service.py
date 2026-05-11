"""Cliente do índice FipeZAP (residencial venda).

Baixamos o PDF mensal publicado em downloads.fipe.org.br via Firecrawl (já
integrado, suporta PDF→markdown), e fazemos parse via regex para extrair
o preço médio por m² em cada cidade coberta (até 56 capitais).

Uso no balisador:
  * Calibrar σ por cidade no Agente 2 (CMA) com base no preço médio FipeZAP
    vs mediana dos comparáveis raspados.
  * Sanity check: quando a mediana dos comparáveis distoa muito do FipeZAP
    (>30%), gerar warning na CMA.
  * Tendência: ao acumular vários meses, calcular variação anual e marcar
    bairros/cidades em alta ou baixa.

A FipeZAP publica os índices mensalmente em ~5 dias do mês seguinte. Para
manter o sistema atualizado, basta rodar ``scripts/update_fipezap.py`` por
cron uma vez por mês.

URL do PDF: ``https://downloads.fipe.org.br/indices/fipezap/fipezap-YYYYMM-residencial-venda.pdf``
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from app.core.logging import get_logger
from app.services.firecrawl_service import FirecrawlScrapeError, get_firecrawl_service

logger = get_logger(__name__)


class FipeZapServiceError(RuntimeError):
    """Falha ao baixar ou parsear o PDF FipeZAP."""


_BASE_URL: Final[str] = "https://downloads.fipe.org.br/indices/fipezap"


@dataclass(frozen=True, slots=True)
class CityPpm2Reading:
    """Uma leitura de preço médio por cidade no mês de referência."""

    city: str
    state: str | None
    mean_ppm2_brl: float
    year: int
    month: int


def _normalize_city(name: str) -> str:
    """Normaliza cidade para comparação (lower, sem acentos, espaços limpos)."""
    nfkd = unicodedata.normalize("NFKD", name)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(no_accents.lower().split())


# Regex que casa linhas tipo:
#   "Vitória (ES) ... R$ 14.253"
#   "São Paulo (SP) ... R$ 11.915"
# Tolerante a separadores variados ("|", tabulação, sequência de espaços) e
# diferentes posições do (UF). Aceita também o padrão "ranking pos. Cidade".
_PRICE_LINE = re.compile(
    r"""
    (?P<city>[A-ZÀ-Ÿ][\w'\-\sÀ-ÿ]{2,40}?)        # cidade (com acentos, espaços, hífen)
    \s*\(\s*(?P<state>[A-Z]{2})\s*\)             # (UF)
    [^\d\n]{0,80}?                               # qualquer separador (até 80 chars sem dígito)
    R\$\s*(?P<value>\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?)   # valor R$
    \s*(?:/m|\s|$)                               # opcionalmente "/m²" ou fim
    """,
    re.VERBOSE | re.MULTILINE,
)


def _parse_brl_number(raw: str) -> float | None:
    """Converte '14.253,40' / '14 253,40' / '14253' em float."""
    s = raw.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


class FipeZapService:
    """Cliente FipeZAP que delega download ao Firecrawl e parseia o markdown."""

    def fetch_pdf_markdown(self, year: int, month: int) -> str:
        """Baixa o PDF mensal via Firecrawl e devolve o markdown extraído.

        Levanta :class:`FipeZapServiceError` se o Firecrawl falhar ou se a
        URL não estiver disponível (ex.: mês muito recente / muito antigo).
        """
        url = f"{_BASE_URL}/fipezap-{year:04d}{month:02d}-residencial-venda.pdf"
        logger.info("fipezap.fetch.start", url=url, year=year, month=month)
        try:
            doc = get_firecrawl_service().scrape_to_markdown(url)
        except FirecrawlScrapeError as exc:
            raise FipeZapServiceError(
                f"Firecrawl não conseguiu ler FipeZAP {year:04d}-{month:02d}: {exc}"
            ) from exc
        return doc.get("markdown", "") or ""

    def parse_city_prices(
        self,
        markdown: str,
        *,
        year: int,
        month: int,
    ) -> list[CityPpm2Reading]:
        """Extrai preços médios R$/m² por cidade do markdown FipeZAP.

        Deduplica por cidade (algumas linhas aparecem em mais de uma seção:
        ranking absoluto, ranking de variação, etc.) — fica com o maior
        valor encontrado, que costuma ser o R$/m² em vez do índice 100.
        Cidades com valor < R$ 1.000/m² são descartadas (índice numérico).
        """
        seen: dict[str, CityPpm2Reading] = {}
        for m in _PRICE_LINE.finditer(markdown):
            city_raw = m.group("city").strip()
            state = m.group("state").upper()
            value = _parse_brl_number(m.group("value"))
            if value is None or value < 1_000:
                # Provavelmente é variação % ou índice, não R$/m².
                continue
            key = f"{_normalize_city(city_raw)}|{state}"
            existing = seen.get(key)
            if existing is None or value > existing.mean_ppm2_brl:
                seen[key] = CityPpm2Reading(
                    city=city_raw,
                    state=state,
                    mean_ppm2_brl=value,
                    year=year,
                    month=month,
                )
        return sorted(seen.values(), key=lambda r: r.mean_ppm2_brl, reverse=True)

    def fetch_and_parse(self, year: int, month: int) -> list[CityPpm2Reading]:
        """Fluxo completo: download + parse. Vazio quando algo falha
        (sem levantar)."""
        try:
            md = self.fetch_pdf_markdown(year, month)
        except FipeZapServiceError as exc:
            logger.warning("fipezap.fetch.failed", year=year, month=month, error=str(exc))
            return []
        readings = self.parse_city_prices(md, year=year, month=month)
        logger.info(
            "fipezap.parsed",
            year=year,
            month=month,
            n_cities=len(readings),
        )
        return readings


@lru_cache(maxsize=1)
def get_fipezap_service() -> FipeZapService:
    return FipeZapService()


__all__ = [
    "FipeZapService",
    "FipeZapServiceError",
    "CityPpm2Reading",
    "get_fipezap_service",
]
