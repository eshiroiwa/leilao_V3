"""Nó CHECK_PROCESSES — descoberta de processos do proprietário.

Estratégia (descoberta em 2026-05-12):

  A API pública do CNJ DataJud **não indexa o campo `partes`** (LGPD).
  Buscar por CPF/CNPJ ou nome direto no DataJud sempre retorna 0 hits.
  Por isso o caminho real de descoberta é via web (Firecrawl):

    1. Firecrawl search com o NOME do proprietário em variantes
       direcionadas (processo / penhora / anulatória / leilão).
    2. Regex extrai NÚMEROS CNJ (formato unificado) dos snippets.
    3. ``tribunal_from_cnj_number`` decodifica o tribunal do próprio
       número (sem precisar adivinhar UF).
    4. Para cada (número, tribunal), ``DataJud.search_by_number``
       enriquece com classe, órgão julgador, data de ajuizamento e
       categoria crítica.

  O fluxo está em :mod:`app.agents.legal.nodes.discover_processes_web`.
  Este nó orquestra o status final e os labels de critical findings.

  Sem ``owner_name`` válido (≥ 2 palavras) → status SKIPPED com motivo.
  DataJud só é consultado quando um número é descoberto.
"""

from __future__ import annotations

from app.agents.legal.nodes.discover_processes_web import (
    critical_labels_from,
    discover_processes_web,
)
from app.agents.legal.schemas import OwnerProcessesResult, SearchedScope
from app.core.logging import get_logger
from app.services.cnj_datajud_service import DataJudService
from app.services.firecrawl_service import FirecrawlService

logger = get_logger(__name__)


def check_processes(
    *,
    property_row: dict,
    datajud: DataJudService,
    firecrawl: FirecrawlService | None = None,
    scope: SearchedScope = "national",
    force_refresh: bool = False,
) -> OwnerProcessesResult:
    """Roda a descoberta de processos do proprietário e devolve o resultado.

    Os parâmetros ``scope`` e ``force_refresh`` ficam na assinatura por
    retrocompat — são no-op enquanto a descoberta é só por nome via web.
    """
    del scope, force_refresh  # Reservados para evolução futura.

    raw_doc = (property_row.get("owner_cpf_cnpj") or "").strip()
    cpf_cnpj = "".join(c for c in raw_doc if c.isdigit())
    owner_name = (property_row.get("owner_name") or "").strip() or None
    city = (property_row.get("city") or "").strip() or None

    if raw_doc and len(cpf_cnpj) not in (11, 14):
        return OwnerProcessesResult(
            status="skipped",
            cpf_cnpj=cpf_cnpj or None,
            skipped_reason=(
                f"CPF/CNPJ com {len(cpf_cnpj)} dígito(s) — "
                "esperado 11 (CPF) ou 14 (CNPJ)."
            ),
        )

    if not owner_name or len(owner_name.split()) < 2:
        return OwnerProcessesResult(
            status="skipped",
            cpf_cnpj=cpf_cnpj or None,
            searched_by_name=False,
            skipped_reason=(
                "Sem nome do proprietário (≥ 2 palavras) — a descoberta "
                "de processos só é viável por nome (a API DataJud pública "
                "não indexa CPF/CNPJ por força da LGPD)."
            ),
        )

    if firecrawl is None:
        return OwnerProcessesResult(
            status="skipped",
            cpf_cnpj=cpf_cnpj or None,
            searched_by_name=True,
            skipped_reason="Firecrawl indisponível — busca web não pode ser executada.",
        )

    processes, _sources = discover_processes_web(
        owner_name=owner_name,
        owner_cpf_cnpj=cpf_cnpj or None,
        city=city,
        firecrawl=firecrawl,
        datajud=datajud,
    )

    total_hits = len(processes)
    critical_hits = sum(1 for p in processes if p.is_critical)
    sample = processes[:20]
    tribunals_queried = sorted({p.tribunal for p in processes})

    logger.info(
        "legal.check_processes.done",
        owner_name=owner_name,
        cpf_present=bool(cpf_cnpj),
        total=total_hits,
        critical=critical_hits,
        tribunals_touched=len(tribunals_queried),
    )

    return OwnerProcessesResult(
        status="completed",
        cpf_cnpj=cpf_cnpj or None,
        tribunal=tribunals_queried[0] if tribunals_queried else None,
        tribunals_queried=tribunals_queried,
        tribunals_failed=[],
        hits_per_tribunal={
            t: sum(1 for p in processes if p.tribunal == t)
            for t in tribunals_queried
        },
        searched_scope="national",
        searched_by_name=True,
        total_hits=total_hits,
        critical_hits=critical_hits,
        critical_labels=critical_labels_from(processes),
        sample_processes=sample,
        processes_full=processes,
    )


__all__ = ["check_processes"]
