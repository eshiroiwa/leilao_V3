"""Nó WEB_SEARCH_ANULATORIAS — busca dirigida via Firecrawl por processos
contra o proprietário, com foco em ações ANULATÓRIAS de leilão e EMBARGOS
à arrematação que ainda não estejam indexados no CNJ DataJud.

Estratégia: 3 queries com aspas em torno do nome (forçar match exato),
limitando a 5 resultados cada. Hosts proibidos (jusbrasil, redes sociais)
são filtrados — Jusbrasil tem TOS que vedam uso comercial; LinkedIn etc.
geram ruído.

Falha silenciosa: erro de rede / sem nome → ``[]``. Custo por chamada
Firecrawl ≈ 1 crédito; 3 queries = ~$0.01-0.02 por análise.
"""

from __future__ import annotations

from app.agents.legal.schemas import WebFinding
from app.core.logging import get_logger
from app.services.firecrawl_service import FirecrawlService

logger = get_logger(__name__)

# Hosts bloqueados (TOS / ruído).
_BLOCKED_HOSTS = (
    "jusbrasil.com.br",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
)

# Termos que indicam alta relevância no título/snippet (cada um soma 0.3).
_RELEVANCE_TERMS = (
    "anulator",  # cobre "anulatória", "anulatório", "anulatória de leilão"
    "embargo",   # embargos à arrematação
    "arremat",   # arrematação
    "leilao",    # leilão (sem acento, comum em URLs/títulos)
    "leilão",
)


def _score(title: str, snippet: str | None) -> float:
    """Score heurístico [0..1] pela presença dos termos relevantes."""
    text = ((title or "") + " " + (snippet or "")).lower()
    hits = sum(1 for t in _RELEVANCE_TERMS if t in text)
    return min(1.0, 0.3 * hits)


def _blocked(url: str) -> bool:
    u = (url or "").lower()
    return any(host in u for host in _BLOCKED_HOSTS)


def web_search_anulatorias(
    *,
    owner_name: str | None,
    city: str | None,
    firecrawl: FirecrawlService,
) -> list[WebFinding]:
    """Devolve achados na web ligados ao proprietário. Pode estar vazio."""
    name = (owner_name or "").strip()
    if not name or len(name.split()) < 2:
        # Nome com 1 palavra gera ruído insuportável (homônimos).
        return []

    queries: list[str] = [
        f'"{name}" anulatória leilão',
        f'"{name}" embargos arrematação',
    ]
    if city:
        queries.append(f'"{name}" {city.strip()} processo')

    findings: list[WebFinding] = []
    for q in queries:
        try:
            results = firecrawl.search(q, limit=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "legal.web_search.query_failed", query=q, error=str(exc),
            )
            continue
        for r in results:
            url = (r.get("url") or "").strip()
            if not url or _blocked(url):
                continue
            title = (r.get("title") or "").strip() or url
            snippet = r.get("description")
            score = _score(title, snippet)
            if score <= 0.0:
                continue
            findings.append(
                WebFinding(
                    title=title[:300],
                    url=url,
                    snippet=(snippet or "")[:500] or None,
                    query=q,
                    score=round(score, 3),
                )
            )

    # Deduplica por URL preservando o maior score; top 10 por score.
    by_url: dict[str, WebFinding] = {}
    for f in findings:
        existing = by_url.get(f.url)
        if existing is None or f.score > existing.score:
            by_url[f.url] = f
    top = sorted(by_url.values(), key=lambda x: x.score, reverse=True)[:10]
    logger.info(
        "legal.web_search.done",
        owner=name,
        n_queries=len(queries),
        n_findings=len(top),
    )
    return top


__all__ = ["web_search_anulatorias"]
