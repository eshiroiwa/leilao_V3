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
    tribunal = datajud.tribunal_for_state(state)
    if not tribunal:
        return OwnerProcessesResult(
            status="skipped",
            cpf_cnpj=cpf_cnpj,
            skipped_reason=f"UF '{state}' sem TJ mapeado — não há tribunal default para consultar.",
        )

    try:
        query = datajud.search_by_document(cpf_cnpj, tribunal=tribunal, size=20)
    except DataJudServiceError as exc:
        return OwnerProcessesResult(
            status="failed",
            cpf_cnpj=cpf_cnpj,
            tribunal=tribunal,
            skipped_reason=f"DataJud falhou: {exc}",
        )

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
        # Priorizamos os críticos no sample exibido ao usuário.
        for p in sorted(query.processes, key=lambda x: not x.is_critical)[:10]
    ]

    logger.info(
        "legal.check_processes.done",
        cpf_cnpj_digits=len(cpf_cnpj),
        tribunal=tribunal,
        total=query.total_hits,
        critical=query.critical_hits,
    )

    return OwnerProcessesResult(
        status="completed",
        cpf_cnpj=cpf_cnpj,
        tribunal=tribunal,
        total_hits=query.total_hits,
        critical_hits=query.critical_hits,
        critical_labels=list(query.critical_labels),
        sample_processes=sample,
    )


__all__ = ["check_processes"]
