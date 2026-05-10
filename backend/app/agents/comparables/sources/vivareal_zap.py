"""Adapter para VivaReal e ZAP Imóveis (mesmo grupo OLX/ZAP).

Padrões observados (a estrutura de URL pode mudar — manter este arquivo
como o único lugar a ajustar quando os portais mudarem layout):

Anúncio individual (RARAMENTE retornado pelo Google):
  VivaReal: https://www.vivareal.com.br/imovel/.../{slug}-id-{externalId}/
  ZAP:      https://www.zapimoveis.com.br/imovel/.../{...}-id-{externalId}/

Páginas de busca/listagem ricas (o que o Google retorna na maioria das vezes —
contêm vários cards de anúncio e são EXCELENTES fontes para batch extraction):
  https://www.vivareal.com.br/venda/sp/sao-paulo/zona-sul/jardim-guedala/avenida-morumbi/casa_residencial/
  https://www.zapimoveis.com.br/venda/casas-de-condominio/sp+sao-paulo+zona-sul+jd-guedala/

Páginas de busca rasas (cidade/estado) — POUCO úteis: muito heterogêneas,
desperdiçam crédito de scrape e LLM:
  https://www.vivareal.com.br/venda/sp/
  https://www.vivareal.com.br/venda/sp/sao-paulo/
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.agents.comparables.sources.base import SourceAdapter

# Captura "id-1234567" no final do path do anúncio.
_ID_RE = re.compile(r"-id-(\d+)/?$", re.IGNORECASE)

# URLs canônicas de anúncio individual no markdown — usado pelo fallback
# determinístico para reconciliar cards quando o LLM devolve só a parent.
# Padrão: ``https://www.{vivareal,zapimoveis}.com.br/imovel/...-id-{N}/``.
_LISTING_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:vivareal|zapimoveis)\.com\.br/imovel/"
    r"[^\s\"'<>)\]]+?-id-\d+/?",
    re.IGNORECASE,
)

# Só queremos VENDA. /aluguel/ e /lancamentos/ não são comparáveis para
# preço de mercado de venda.
_VENDA_PATH = "/venda/"
_BLOCKED_PATHS = ("/aluguel/", "/lancamentos/")


def _path_segments(url: str) -> list[str]:
    return [s for s in urlparse(url).path.split("/") if s]


def _depth_score(url: str) -> int:
    """Conta a 'profundidade' geográfica/categórica da URL.

    VivaReal usa segmentos separados por `/`:
      /venda/sp/sao-paulo/zona-sul/jardim-guedala/avenida-morumbi/casa_residencial/

    ZAP empacota tudo num segmento separado por `+`:
      /venda/casas-de-condominio/sp+sao-paulo+zona-sul+jd-guedala/

    Para tratar os dois portais com a MESMA threshold, somamos
    `len(segments)` + total de `+` presentes em qualquer segmento.
    """
    segs = _path_segments(url)
    plus_total = sum(s.count("+") for s in segs)
    return len(segs) + plus_total


class VivaRealZapAdapter(SourceAdapter):
    """Adapter unificado para VivaReal/ZAP (mesma engine de URLs)."""

    name = "vivareal_zap"
    domains = ("vivareal.com.br", "zapimoveis.com.br")
    listing_url_pattern = _LISTING_URL_RE

    # ---- Anúncio individual ------------------------------------------- #
    def is_listing_url(self, url: str) -> bool:
        """True se a URL aponta para a página de UM imóvel específico
        (com `-id-{N}` no final do path)."""
        if not self.matches(url):
            return False
        path = urlparse(url).path
        if "/imovel/" not in path:
            return False
        return _ID_RE.search(path) is not None

    # ---- Página de listagem (search results) -------------------------- #
    def is_search_results_url(self, url: str) -> bool:
        """True se a URL aponta para uma página de RESULTADOS DE BUSCA
        suficientemente específica — contém vários cards de imóveis na
        mesma região, o que é ouro para nosso batch-extractor.

        Heurística:
          1. precisa começar com /venda/ (não /aluguel/, não /lancamentos/);
          2. depth score >= 5 (chegou ao nível de bairro/rua/categoria);
          3. não é página de anúncio individual.
        """
        if not self.matches(url):
            return False
        path = urlparse(url).path
        # Bloqueio explícito: aluguel e lançamentos não são comparáveis de venda.
        if any(blocked in path for blocked in _BLOCKED_PATHS):
            return False
        if not path.startswith(_VENDA_PATH):
            return False
        if "/imovel/" in path:
            return False
        # depth score >= 5 ≈ chegou ao nível de bairro (ou mais específico).
        # ViaReal /venda/sp/sao-paulo/zona-sul/jardim-guedala/  → 5 segs = 5
        # ZAP /venda/casas-de-condominio/sp+sao-paulo+zona-sul+jd-guedala/
        #     → 3 segs + 3 `+` = 6 → aceita
        return _depth_score(url) >= 5

    def is_scrapable(self, url: str) -> bool:
        """True se vale a pena raspar — anúncio individual OU listagem
        específica."""
        return self.is_listing_url(url) or self.is_search_results_url(url)

    # ---- Identificação ------------------------------------------------- #
    def extract_external_id(self, url: str) -> str | None:
        m = _ID_RE.search(urlparse(url).path)
        return m.group(1) if m else None


__all__ = ["VivaRealZapAdapter"]
