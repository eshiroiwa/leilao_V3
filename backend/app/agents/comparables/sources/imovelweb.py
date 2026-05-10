"""Adapter para ImovelWeb (imovelweb.com.br).

Padrões observados (a estrutura de URL pode mudar — manter este arquivo
como o único lugar a ajustar quando o portal mudar layout):

Anúncio individual (sempre em ``/propriedades/`` com id no final do filename):
  https://www.imovelweb.com.br/propriedades/apartamento-a-venda-com-otima-localizacao-no-3028238732.html
  https://www.imovelweb.com.br/propriedades/duplex-mont-tannat-no-centro-com-uma-excelente-2999680136.html

Páginas de busca/listagem (UMA página `.html` agrega muitos cards — ouro
para batch extraction):
  /apartamentos-venda-pindamonhangaba-sp-2-quartos.html
  /apartamentos-venda-feital-pindamonhangaba-2-quartos.html
  /apartamentos-venda-pindamonhangaba-sp-2-quartos-ordem-precio-menor.html
  /apartamentos-cobertura-venda-sao-paulo-sp-2-quartos.html
  /apartamentos-duplex-venda-pinheiros-sao-paulo-2-quartos.html
  /casas-venda-sao-paulo-q-zona-norte.html
  /imoveis-venda-pindamonhangaba-sp-2-quartos.html

Páginas rasas (POUCO úteis — só estado/cidade, sem filtro de bairro/quartos):
  /apartamentos-venda-sp.html
  /apartamentos-venda-sao-paulo-sp.html

ALUGUEL/LANÇAMENTOS são bloqueados (não são comparáveis de preço de venda):
  /apartamentos-aluguel-...
  /imoveis-aluguel-...
  /apartamentos-temporada-...
  /lancamentos/...
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.agents.comparables.sources.base import SourceAdapter

# ``/propriedades/{slug}-{NNNNNNNN}.html`` — id externo no final.
# Exigimos pelo menos 8 dígitos para não colidir com pequenos números que
# aparecem no slug de POIs (ex.: "rua-francisco-leitao-577.html").
_LISTING_ID_RE = re.compile(r"-(\d{8,})\.html$", re.IGNORECASE)

# URLs canônicas de anúncio individual no markdown — usado pelo fallback
# determinístico para reconciliar cards quando o LLM devolve só a parent.
_LISTING_URL_RE = re.compile(
    r"https?://(?:www\.)?imovelweb\.com\.br/propriedades/"
    r"[^\s\"'<>)\]]+?-\d{8,}\.html",
    re.IGNORECASE,
)

# Categorias VÁLIDAS para venda no nome do arquivo da listagem.
# O ImovelWeb codifica `categoria-venda-...-` como prefixo. Mantemos uma
# whitelist explícita para evitar capturar páginas institucionais.
_VENDA_PREFIX_RE = re.compile(
    r"^(apartamentos|apartamentos-cobertura|apartamentos-duplex|"
    r"apartamentos-kitnet|"
    r"casas|casas-de-condominio|sobrados|"
    r"coberturas|"
    r"terrenos|terrenos-em-condominio|"
    r"salas-comerciais|conjuntos-comerciais|lojas|galpoes|predios-comerciais|"
    r"imoveis|chacaras|sitios|fazendas|haras)-venda-",
    flags=re.IGNORECASE,
)

# Tokens proibidos no path/filename — sinalizam aluguel ou lançamento.
_BLOCKED_TOKENS: tuple[str, ...] = (
    "-aluguel-",
    "-temporada-",
    "-permuta-",
    "lancamentos",
    "/lancamento/",
)

# Profundidade mínima do filename de listagem (em "tokens" separados por `-`)
# para considerá-la específica o bastante. ``apartamentos-venda-sp.html`` tem
# 3 tokens (categoria + venda + UF) — raso. ``apartamentos-venda-sao-paulo-
# sp-2-quartos.html`` tem 7 — específico. Ponto de corte conservador: ≥ 5.
_MIN_FILENAME_TOKENS = 5


def _path_segments(url: str) -> list[str]:
    return [s for s in urlparse(url).path.split("/") if s]


class ImovelWebAdapter(SourceAdapter):
    """Adapter do ImovelWeb (cobertura forte em interior de SP, RJ, PR).

    Conservador: aluguel/temporada/lançamento explicitamente bloqueados;
    listagens de cidade-only são rejeitadas (muito ruidosas).
    """

    name = "imovelweb"
    domains = ("imovelweb.com.br",)
    listing_url_pattern = _LISTING_URL_RE

    # ---- Anúncio individual ------------------------------------------- #
    def is_listing_url(self, url: str) -> bool:
        if not self.matches(url):
            return False
        path = urlparse(url).path
        if "/propriedades/" not in path:
            return False
        if any(tok in path for tok in _BLOCKED_TOKENS):
            return False
        return _LISTING_ID_RE.search(path) is not None

    # ---- Página de listagem (search results) -------------------------- #
    def is_search_results_url(self, url: str) -> bool:
        """True se a URL aponta para uma listagem de venda específica
        (pelo menos categoria + venda + cidade + 1 filtro adicional).

        Heurística:
          1. domínio bate;
          2. caminho NÃO é um anúncio individual (``/propriedades/``);
          3. nenhum token bloqueado (aluguel/temporada/lançamento);
          4. único segmento do path termina em ``.html``;
          5. filename começa com ``{categoria}-venda-`` (whitelist);
          6. filename tem >= ``_MIN_FILENAME_TOKENS`` tokens entre hífens.
        """
        if not self.matches(url):
            return False
        path = urlparse(url).path
        if "/propriedades/" in path:
            return False
        if any(tok in path for tok in _BLOCKED_TOKENS):
            return False

        segs = _path_segments(url)
        if len(segs) != 1:
            return False
        filename = segs[0].lower()
        if not filename.endswith(".html"):
            return False
        if not _VENDA_PREFIX_RE.match(filename):
            return False
        # Conta tokens (descartando o sufixo .html) — proxy de especificidade.
        stem = filename[:-len(".html")]
        if stem.count("-") + 1 < _MIN_FILENAME_TOKENS:
            return False
        return True

    def is_scrapable(self, url: str) -> bool:
        """True se vale raspar — anúncio individual OU listagem específica."""
        return self.is_listing_url(url) or self.is_search_results_url(url)

    # ---- Identificação ------------------------------------------------- #
    def extract_external_id(self, url: str) -> str | None:
        m = _LISTING_ID_RE.search(urlparse(url).path)
        return m.group(1) if m else None


__all__ = ["ImovelWebAdapter"]
