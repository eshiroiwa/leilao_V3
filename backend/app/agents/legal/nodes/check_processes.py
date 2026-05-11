"""Nó CHECK_PROCESSES — consulta o CNJ DataJud por CPF/CNPJ do proprietário.

Sem ``owner_cpf_cnpj`` no property → status SKIPPED com motivo (não há
o que consultar). Sem ``state`` válido para mapear o tribunal default
→ também SKIPPED. Falhas do DataJud (rede, quota) → status FAILED com
mensagem em ``skipped_reason``.

Função pura na borda — recebe o property como dict e o cliente do service
por injeção, devolve o ``OwnerProcessesResult`` normalizado.
"""

from __future__ import annotations

from app.agents.legal.schemas import OwnerProcessesResult, ProcessSummary
from app.core.logging import get_logger
from app.services.cnj_datajud_service import (
    DataJudService,
    DataJudServiceError,
)

logger = get_logger(__name__)


def check_processes(
    *,
    property_row: dict,
    datajud: DataJudService,
) -> OwnerProcessesResult:
    """Roda a consulta CNJ DataJud para o property informado.

    Não levanta — qualquer falha vira ``OwnerProcessesResult`` com
    ``status`` explícito + ``skipped_reason``.
    """
    raw = (property_row.get("owner_cpf_cnpj") or "").strip()
    # Normaliza cedo — o valor pode vir tanto do Scraper (já limpo) quanto
    # de um override do usuário digitado no frontend (com pontuação).
    cpf_cnpj = "".join(c for c in raw if c.isdigit())
    if not raw:
        return OwnerProcessesResult(
            status="skipped",
            skipped_reason="property sem owner_cpf_cnpj — scraper não extraiu (informe manualmente).",
        )
    if len(cpf_cnpj) not in (11, 14):
        return OwnerProcessesResult(
            status="skipped",
            cpf_cnpj=cpf_cnpj or None,
            skipped_reason=(
                f"CPF/CNPJ com {len(cpf_cnpj)} dígito(s) — esperado 11 (CPF) ou 14 (CNPJ)."
            ),
        )

    state = (property_row.get("state") or "").strip().upper()
    tribunals = datajud.tribunals_for_state(state)
    if not tribunals:
        return OwnerProcessesResult(
            status="skipped",
            cpf_cnpj=cpf_cnpj,
            skipped_reason=(
                f"UF '{state}' sem tribunais mapeados — não há TJ/TRT default para consultar."
            ),
        )

    # Itera pelos tribunais (TJ + TRT(s)). Erros parciais não derrubam o
    # resultado — sinalizamos no `tribunals_failed`. Só viramos FAILED se
    # NENHUM tribunal respondeu.
    all_processes = []
    queried: list[str] = []
    failed: list[str] = []
    total_hits = 0
    critical_hits = 0
    critical_labels_set: set[str] = set()

    for tribunal in tribunals:
        try:
            q = datajud.search_by_document(cpf_cnpj, tribunal=tribunal, size=20)
        except DataJudServiceError as exc:
            logger.warning(
                "legal.check_processes.tribunal_failed",
                tribunal=tribunal,
                error=str(exc),
            )
            failed.append(tribunal)
            continue
        queried.append(tribunal)
        all_processes.extend(q.processes)
        total_hits += q.total_hits
        critical_hits += q.critical_hits
        critical_labels_set.update(q.critical_labels)

    if not queried:
        return OwnerProcessesResult(
            status="failed",
            cpf_cnpj=cpf_cnpj,
            tribunal=tribunals[0],
            tribunals_failed=failed,
            skipped_reason=(
                f"DataJud falhou em todos os tribunais consultados: {', '.join(failed)}"
            ),
        )

    # Sample: críticos primeiro, depois por data desc.
    sample = [
        ProcessSummary(
            numero_processo=p.numero_processo,
            classe_codigo=p.classe_codigo,
            classe_nome=p.classe_nome,
            orgao_julgador=p.orgao_julgador,
            data_ajuizamento=p.data_ajuizamento,
            tribunal=p.tribunal,
            is_critical=p.is_critical,
        )
        for p in sorted(
            all_processes,
            key=lambda x: (not x.is_critical, x.data_ajuizamento or ""),
        )[:20]
    ]

    logger.info(
        "legal.check_processes.done",
        cpf_cnpj_digits=len(cpf_cnpj),
        tribunals_queried=queried,
        tribunals_failed=failed,
        total=total_hits,
        critical=critical_hits,
    )

    return OwnerProcessesResult(
        status="completed",
        cpf_cnpj=cpf_cnpj,
        tribunal=queried[0],
        tribunals_queried=queried,
        tribunals_failed=failed,
        total_hits=total_hits,
        critical_hits=critical_hits,
        critical_labels=sorted(critical_labels_set),
        sample_processes=sample,
    )


__all__ = ["check_processes"]
