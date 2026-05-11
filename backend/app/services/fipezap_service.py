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


# Estratégia 1 — TABELA markdown (mais confiável). O PDF da FipeZAP tem
# uma tabela "Comportamento recente dos preços" no formato:
#
#   | São Paulo | SP | +0,19% | +0,42% | +1,02% | +4,28% | 12.019 |
#
# Última coluna é o preço médio em R$/m² (sem prefixo "R$"). Cidade na 1ª
# célula, UF na 2ª, depois variações percentuais, preço na última.
_TABLE_ROW = re.compile(
    r"""
    ^\|\s*
    (?P<city>[A-ZÀ-Ÿ][\w'\-\sÀ-ÿ]{2,40}?)        # cidade
    \s*\|\s*
    (?P<state>[A-Z]{2})                          # UF
    \s*\|
    (?:[^|]*\|){3,5}                              # 3-5 colunas de variação %
    \s*(?P<value>\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?) # valor da última coluna
    \s*\|?\s*$
    """,
    re.VERBOSE | re.MULTILINE,
)

# Estratégia 2 — fallback no parágrafo do "ranking" textual. Útil quando
# a tabela está corrompida no markdown:
#   "Vitória (ES) ... maior preço médio no mês (R$ 14.818/m²),
#    seguida por: Florianópolis (R$ 13.208/m²); São Paulo (R$ 12.019/m²); ..."
# Aqui só a PRIMEIRA cidade tem (UF) explícito — extraímos a sequência
# casando "Cidade (R$ X/m²)" e mantendo o estado="" para reconciliação
# posterior contra a tabela.
_RANK_ENTRY = re.compile(
    r"""
    (?:^|[;:,])\s*                                # delimitador ou início
    (?P<city>[A-ZÀ-Ÿ][\w'\-\sÀ-ÿ]{2,40}?)        # cidade
    \s*\(\s*R\$\s*
    (?P<value>\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?)
    \s*/m
    """,
    re.VERBOSE,
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

        PDFs do FipeZAP costumam ser densos (~50KB de markdown) e meses
        mais antigos podem demorar bem mais do que o default de scrape;
        usamos timeout generoso (60s) e wait extra para o servidor da
        Fipe renderizar.

        Levanta :class:`FipeZapServiceError` se o Firecrawl falhar ou se a
        URL não estiver disponível (ex.: mês muito recente / muito antigo).
        """
        url = f"{_BASE_URL}/fipezap-{year:04d}{month:02d}-residencial-venda.pdf"
        logger.info("fipezap.fetch.start", url=url, year=year, month=month)
        try:
            doc = get_firecrawl_service().scrape_to_markdown(
                url, timeout_ms=60_000, wait_for_ms=3_000,
            )
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

        Estratégia em duas fases:
          1. Tabela markdown ``| Cidade | UF | …% | …% | preço |`` — fonte
             primária, com UF explícita por linha.
          2. Parágrafo do ranking textual (``Vitória (ES) … (R$ 14.818/m²);
             Florianópolis (R$ 13.208/m²); …``) — backup. Como apenas a
             primeira cidade tem (UF) ali, reconciliamos cada cidade textual
             com a tabela por nome normalizado para herdar a UF correta.

        Deduplica por (cidade normalizada, UF), preservando o maior valor
        quando há colisão entre tabela e ranking. Filtra valores < R$ 1.000
        (variações % e índices base 100 não passam).
        """
        seen: dict[str, CityPpm2Reading] = {}

        # ---- Fase 1: tabela ------------------------------------------- #
        for m in _TABLE_ROW.finditer(markdown):
            city_raw = m.group("city").strip()
            state = m.group("state").upper()
            value = _parse_brl_number(m.group("value"))
            if value is None or value < 1_000:
                continue
            key = f"{_normalize_city(city_raw)}|{state}"
            existing = seen.get(key)
            if existing is None or value > existing.mean_ppm2_brl:
                seen[key] = CityPpm2Reading(
                    city=city_raw, state=state, mean_ppm2_brl=value,
                    year=year, month=month,
                )

        # ---- Fase 2: parágrafo do ranking ----------------------------- #
        # Mapa cidade_normalizada → UF (da tabela). Permite herdar UF
        # quando o ranking textual menciona a cidade sem (UF).
        city_to_state = {
            _normalize_city(r.city): r.state for r in seen.values() if r.state
        }
        for m in _RANK_ENTRY.finditer(markdown):
            city_raw = m.group("city").strip()
            value = _parse_brl_number(m.group("value"))
            if value is None or value < 1_000:
                continue
            normalized = _normalize_city(city_raw)
            state = city_to_state.get(normalized)
            if not state:
                # Cidade só apareceu no ranking textual sem casar com a
                # tabela — preserva ainda assim (UF=None), permite ao
                # caller filtrar/avisar.
                key = f"{normalized}|"
                existing = seen.get(key)
                if existing is None or value > existing.mean_ppm2_brl:
                    seen[key] = CityPpm2Reading(
                        city=city_raw, state=None, mean_ppm2_brl=value,
                        year=year, month=month,
                    )
                continue
            key = f"{normalized}|{state}"
            existing = seen.get(key)
            if existing is None or value > existing.mean_ppm2_brl:
                seen[key] = CityPpm2Reading(
                    city=city_raw, state=state, mean_ppm2_brl=value,
                    year=year, month=month,
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
