"""Adapter para ChavesNaMão (chavesnamao.com.br).

Padrões observados (a estrutura de URL pode mudar — manter este arquivo
como o único lugar a ajustar quando o portal mudar layout):

Anúncio individual (todos terminam com ``/id-{NNN}/``):
  https://www.chavesnamao.com.br/imovel/apartamento-a-venda-2-quartos-com-garagem-sp-pindamonhangaba-centro-RS395000/id-31871873/
  https://www.chavesnamao.com.br/imovel/casa-a-venda-3-quartos-pr-curitiba-juveve-RS850000/id-12345678/

Páginas de busca/listagem (com vários cards — boas para batch extraction):
  /apartamentos-a-venda/sp-pindamonhangaba/2-quartos/
  /apartamentos-a-venda/sp-sao-paulo/jardins/2-quartos/
  /apartamentos-a-venda/sp-sao-paulo/bairros/avenida-paulista/2-quartos/
  /apartamentos/sp-pindamonhangaba/parque-das-nacoes/2-quartos/   ← variante curta
  /imoveis/sp-pindamonhangaba/centro/2-quartos/

Páginas rasas (POUCO úteis — muito heterogêneas, só UF ou UF+cidade):
  /apartamentos-a-venda/sp-pindamonhangaba/   ← só cidade
  /apartamentos-a-venda/sp/

ALUGUEL/LANÇAMENTOS são bloqueados (não são comparáveis de venda):
  /apartamentos-para-alugar/...
  /imoveis-para-alugar/...
  /lancamentos/...
  /imovel/.../para-alugar-...
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.agents.comparables.sources.base import SourceAdapter

# ``/imovel/.../id-{NNN}/?`` — captura o id externo no final do path.
_ID_RE = re.compile(r"/id-(\d+)/?$", re.IGNORECASE)

# URLs canônicas de anúncio individual no markdown — usado pelo fallback
# determinístico de reconciliação. Padrão:
# ``https://www.chavesnamao.com.br/imovel/...{slug}/id-{N}/``.
_LISTING_URL_RE = re.compile(
    r"https?://(?:www\.)?chavesnamao\.com\.br/imovel/"
    r"[^\s\"'<>)\]]+?/id-\d+/?",
    re.IGNORECASE,
)

# Categorias VÁLIDAS para venda (primeiro segmento do path).
# Aceitamos tanto a forma "-a-venda" explícita quanto a curta (sem sufixo),
# que o ChavesNaMão usa como atalho para listagens de venda.
_VENDA_CATEGORIES: tuple[str, ...] = (
    "apartamentos-a-venda",
    "apartamentos",
    "casas-a-venda",
    "casas",
    "coberturas-a-venda",
    "coberturas",
    "salas-a-venda",
    "salas-comerciais-a-venda",
    "lojas-a-venda",
    "galpoes-a-venda",
    "terrenos-a-venda",
    "terrenos",
    "imoveis-a-venda",
    "imoveis",
)

# Tokens proibidos em qualquer parte do path/slug — a presença desses
# elementos sinaliza aluguel ou lançamento, que não são comparáveis
# de preço de venda.
_BLOCKED_TOKENS: tuple[str, ...] = (
    "para-alugar",
    "-aluguel-",
    "para-temporada",
    "lancamentos",
    "/lancamento/",
)


def _path_segments(url: str) -> list[str]:
    return [s for s in urlparse(url).path.split("/") if s]


class ChavesNaMaoAdapter(SourceAdapter):
    """Adapter do ChavesNaMão (cobertura forte em SP/PR/SC).

    Conservador: páginas de aluguel/lançamento são explicitamente bloqueadas
    e listagens rasas (cidade-only) são consideradas pouco específicas.
    """

    name = "chavesnamao"
    domains = ("chavesnamao.com.br",)
    listing_url_pattern = _LISTING_URL_RE

    # ---- Anúncio individual ------------------------------------------- #
    def is_listing_url(self, url: str) -> bool:
        if not self.matches(url):
            return False
        path = urlparse(url).path
        if "/imovel/" not in path:
            return False
        # Bloqueia explicitamente anúncios de aluguel/temporada.
        if any(tok in path for tok in _BLOCKED_TOKENS):
            return False
        return _ID_RE.search(path) is not None

    # ---- Página de listagem (search results) -------------------------- #
    def is_search_results_url(self, url: str) -> bool:
        """True se a URL aponta para uma página de RESULTADOS DE BUSCA
        suficientemente específica (com filtro de bairro/rua/quartos),
        que é o tipo de página rica para nosso batch-extractor.

        Heurística:
          1. primeiro segmento ∈ ``_VENDA_CATEGORIES`` (não é aluguel);
          2. nenhum token bloqueado no path inteiro;
          3. não é uma URL de anúncio individual (``/imovel/``);
          4. ``len(segments) >= 3`` — pelo menos categoria + cidade + UM
             filtro adicional (bairro, rua, quartos, área…).
        """
        if not self.matches(url):
            return False
        path = urlparse(url).path
        if "/imovel/" in path:
            return False
        if any(tok in path for tok in _BLOCKED_TOKENS):
            return False

        segs = _path_segments(url)
        if not segs:
            return False
        if segs[0].lower() not in _VENDA_CATEGORIES:
            return False
        # Categoria + uf-cidade + (bairro|rua|quartos…) → mínimo 3 segs.
        return len(segs) >= 3

    def is_scrapable(self, url: str) -> bool:
        """True se vale raspar — anúncio individual OU listagem específica."""
        return self.is_listing_url(url) or self.is_search_results_url(url)

    # ---- Identificação ------------------------------------------------- #
    def extract_external_id(self, url: str) -> str | None:
        m = _ID_RE.search(urlparse(url).path)
        return m.group(1) if m else None


__all__ = ["ChavesNaMaoAdapter"]
