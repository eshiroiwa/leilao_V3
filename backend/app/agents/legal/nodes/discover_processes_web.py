"""Nó DISCOVER_PROCESSES_WEB — descobre processos do proprietário via Firecrawl.

Substituto pragmático para a busca direta no DataJud por CPF/nome (que não
funciona — ver docstring de ``cnj_datajud_service``). Fluxo:

  1. Firecrawl search com queries direcionadas ao **nome** do proprietário.
  2. Regex extrai NÚMEROS CNJ (``NNNNNNN-DD.AAAA.J.TR.OOOO``) dos títulos +
     snippets dos resultados.
  3. Para cada número, ``tribunal_from_cnj_number`` decodifica o tribunal
     embutido no próprio número.
  4. Para cada par (número, tribunal), ``DataJud.search_by_number`` enriquece
     com classe, órgão julgador, data de ajuizamento e is_critical.

O resultado é uma lista de ``ProcessSummary`` que entra direto em
``OwnerProcessesResult.processes_full``.

Falha silenciosa em todas as etapas (rede, regex sem match, DataJud sem hit
para o número descoberto). Custo aproximado: 3-5 chamadas Firecrawl + N
calls DataJud (cacheadas 7 dias).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from app.agents.legal.schemas import ProcessSummary
from app.core.logging import get_logger
from app.services.cnj_datajud_service import (
    DataJudService,
    DataJudServiceError,
    tribunal_from_cnj_number,
)
from app.services.firecrawl_service import FirecrawlService

logger = get_logger(__name__)

# Regex CNJ unificado (Resolução 65/2008). Aceita variações de pontuação
# que aparecem em portais de tribunais (alguns omitem pontos/traço).
_CNJ_RE: re.Pattern[str] = re.compile(
    r"\b(\d{7})[-.]?(\d{2})[.\s]?(\d{4})[.\s]?(\d)[.\s]?(\d{2})[.\s]?(\d{4})\b"
)

# Hosts que se sabe que **bloqueiam** Firecrawl ou tem TOS restritivos para
# leitura comercial. Mantemos os snippets do Google que mencionam o host
# (não scrapeamos a página), mas filtramos URLs que claramente não dariam
# proveito ou geram ruído.
_BLOCKED_HOSTS: tuple[str, ...] = (
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
)


def _blocked(url: str) -> bool:
    u = (url or "").lower()
    return any(host in u for host in _BLOCKED_HOSTS)


def _normalize_cnj(match: re.Match[str]) -> str:
    """Reconstrói o número CNJ canônico (20 dígitos) a partir do match."""
    return "".join(match.groups())


def _extract_cnj_numbers(text: str) -> list[str]:
    """Retorna todos os números CNJ encontrados no texto, sem duplicar."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _CNJ_RE.finditer(text):
        canonical = _normalize_cnj(m)
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def _build_queries(*, name: str, city: str | None) -> list[str]:
    """Queries Firecrawl direcionadas para descobrir processos do proprietário.

    Aspas força match exato do nome — homônimos seguem possíveis mas o ruído
    cai drasticamente. Variantes cobrem cenários diferentes (penhora, leilão
    em geral, anulatória/embargos).
    """
    queries = [
        f'"{name}" processo',
        f'"{name}" execução penhora',
        f'"{name}" anulatória leilão',
        f'"{name}" embargos arrematação',
    ]
    if city:
        queries.append(f'"{name}" {city.strip()} processo')
    return queries


def discover_processes_web(
    *,
    owner_name: str | None,
    owner_cpf_cnpj: str | None,
    city: str | None,
    firecrawl: FirecrawlService,
    datajud: DataJudService,
    max_queries: int = 5,
    max_numbers_to_enrich: int = 30,
    enrich_workers: int = 8,
) -> tuple[list[ProcessSummary], list[str]]:
    """Descobre processos do proprietário via web.

    Args:
      owner_name: nome do proprietário (obrigatório para a busca web).
      owner_cpf_cnpj: CPF/CNPJ apenas para registro no log (Google não casa
        bem CPF mascarado; o nome é o sinal real).
      city: cidade do imóvel — adicionada como filtro em uma das queries.
      firecrawl: cliente injetado.
      datajud: cliente injetado para enriquecer.
      max_queries: limita a 5 por padrão (custo ~1 crédito Firecrawl cada).
      max_numbers_to_enrich: cap superior em quantos números únicos chamamos
        no DataJud (evita explosão se a busca retornar centenas).

    Returns:
      ``(processes, sources)`` onde ``processes`` é a lista enriquecida e
      ``sources`` é a lista de URLs onde os números apareceram (para o user
      conferir o contexto).
    """
    name = (owner_name or "").strip()
    if not name or len(name.split()) < 2:
        return [], []

    queries = _build_queries(name=name, city=city)[:max_queries]
    candidates: dict[str, str] = {}  # numero_cnj → primeira URL onde apareceu
    seen_urls: set[str] = set()

    for q in queries:
        try:
            results = firecrawl.search(q, limit=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("legal.discover.search_failed", query=q, error=str(exc))
            continue
        for r in results:
            url = (r.get("url") or "").strip()
            if not url or _blocked(url):
                continue
            title = (r.get("title") or "").strip()
            snippet = (r.get("description") or "").strip()
            blob = " ".join([title, snippet])
            for numero in _extract_cnj_numbers(blob):
                if numero not in candidates:
                    candidates[numero] = url
            seen_urls.add(url)

    logger.info(
        "legal.discover.candidates",
        name=name,
        cpf_cnpj_present=bool(owner_cpf_cnpj),
        n_queries=len(queries),
        n_candidates=len(candidates),
    )

    if not candidates:
        return [], list(seen_urls)

    # Enriquece via DataJud em paralelo (cap em max_numbers_to_enrich).
    limited = list(candidates.items())[:max_numbers_to_enrich]

    def _enrich(numero: str) -> ProcessSummary | None:
        tribunal = tribunal_from_cnj_number(numero)
        if not tribunal:
            return None
        try:
            hit = datajud.search_by_number(numero, tribunal=tribunal)
        except DataJudServiceError as exc:
            logger.warning(
                "legal.discover.datajud_failed",
                numero=numero,
                tribunal=tribunal,
                error=str(exc),
            )
            return None
        if hit is None:
            # Número apareceu na web mas DataJud não tem a row indexada.
            # Ainda assim guardamos como ProcessSummary com dados mínimos —
            # útil para o usuário investigar manualmente.
            return ProcessSummary(
                numero_processo=numero,
                classe_codigo=None,
                classe_nome=None,
                orgao_julgador=None,
                data_ajuizamento=None,
                tribunal=tribunal,
                is_critical=False,
                category="outro",
                matched_by="nome",
            )
        return ProcessSummary(
            numero_processo=hit.numero_processo,
            classe_codigo=hit.classe_codigo,
            classe_nome=hit.classe_nome,
            orgao_julgador=hit.orgao_julgador,
            data_ajuizamento=hit.data_ajuizamento,
            tribunal=hit.tribunal,
            is_critical=hit.is_critical,
            category=hit.category,  # type: ignore[arg-type]
            matched_by="nome",
        )

    processes: list[ProcessSummary] = []
    with ThreadPoolExecutor(max_workers=enrich_workers) as pool:
        futures = [pool.submit(_enrich, num) for num, _ in limited]
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None:
                processes.append(res)

    # Sort: críticos primeiro, depois data desc, depois número.
    processes.sort(
        key=lambda p: (
            not p.is_critical,
            -(_date_key(p.data_ajuizamento)),
            p.numero_processo,
        )
    )

    logger.info(
        "legal.discover.enriched",
        n_enriched=len(processes),
        n_critical=sum(1 for p in processes if p.is_critical),
    )

    return processes, list(seen_urls)


def _date_key(s: str | None) -> int:
    if not s:
        return -1
    try:
        return int(s[:10].replace("-", ""))
    except (ValueError, TypeError):
        return -1


def critical_labels_from(processes: Iterable[ProcessSummary]) -> list[str]:
    """Reutilizável: extrai labels críticos para o front."""
    from app.services.cnj_datajud_service import _CRITICAL_CLASS_LABELS

    labels_set: set[str] = set()
    for p in processes:
        if not p.is_critical:
            continue
        if p.category == "anulatoria":
            labels_set.add("Ação anulatória de leilão")
        elif p.category == "embargos_arrematacao":
            labels_set.add("Embargos à arrematação")
        elif p.category == "trabalhista":
            labels_set.add("Processo trabalhista")
        else:
            lbl = _CRITICAL_CLASS_LABELS.get(p.classe_codigo or 0)
            if lbl:
                labels_set.add(lbl)
    return sorted(labels_set)


__all__ = [
    "critical_labels_from",
    "discover_processes_web",
]
