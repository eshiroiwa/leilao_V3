"""Source adapters do AGENTE 2.

Cada portal de anúncio (VivaReal, ZAP, ChavesNaMão...) implementa
:class:`SourceAdapter` e é registrado em ``_ADAPTERS`` abaixo.

Para adicionar um novo portal:
  1. crie ``app/agents/comparables/sources/<portal>.py`` com a subclasse;
  2. importe e adicione a instância em ``_ADAPTERS``;
  3. inclua o domínio em ``app/agents/comparables/search.py::_SITE_FILTER``;
  4. adicione testes em ``tests/test_comparables_sources*.py``.
"""

from __future__ import annotations

from app.agents.comparables.sources.base import PageKind, SourceAdapter
from app.agents.comparables.sources.chavesnamao import ChavesNaMaoAdapter
from app.agents.comparables.sources.imovelweb import ImovelWebAdapter
from app.agents.comparables.sources.vivareal_zap import VivaRealZapAdapter

_ADAPTERS: tuple[SourceAdapter, ...] = (
    VivaRealZapAdapter(),
    ChavesNaMaoAdapter(),
    ImovelWebAdapter(),
)


def find_adapter(url: str) -> SourceAdapter | None:
    """Devolve o adapter compatível com a URL (ou ``None``).

    Itera adapters na ordem registrada — se um futuro portal compartilhar
    sufixo de domínio com outro, o primeiro registrado vence.
    """
    for adapter in _ADAPTERS:
        if adapter.matches(url):
            return adapter
    return None


def all_domains() -> tuple[str, ...]:
    """Lista plana de domínios cobertos por todos os adapters registrados.

    Usada por ``search.py`` para construir o filtro ``site:`` da query.
    """
    out: list[str] = []
    for ad in _ADAPTERS:
        out.extend(ad.domains)
    return tuple(out)


__all__ = [
    "SourceAdapter",
    "PageKind",
    "VivaRealZapAdapter",
    "ChavesNaMaoAdapter",
    "ImovelWebAdapter",
    "find_adapter",
    "all_domains",
]
