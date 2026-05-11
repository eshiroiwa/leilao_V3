"""Orquestrador do Agente Legal.

Pipeline mínimo:
    1. CHECK_PROCESSES (CNJ DataJud — gratuito);
    2. CHECK_MATRICULA (ONR — stub por ora).

Cada nó é defensivo (não levanta), então o orquestrador é só "consolida
os dois resultados, define ``has_critical_findings`` e persiste".
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.agents.legal.nodes.check_matricula import check_matricula
from app.agents.legal.nodes.check_processes import check_processes
from app.agents.legal.schemas import LegalCheckResult
from app.core.logging import get_logger
from app.services.cnj_datajud_service import DataJudService, get_datajud_service

logger = get_logger(__name__)


def run_legal_check(
    *,
    property_row: dict,
    datajud: DataJudService | None = None,
) -> LegalCheckResult:
    """Executa o pipeline legal sobre o property dado.

    ``datajud`` opcional — útil para testes injetarem mock; default usa
    o singleton de ``get_datajud_service()``.
    """
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    dj = datajud or get_datajud_service()

    owner = check_processes(property_row=property_row, datajud=dj)
    matricula = check_matricula(property_row=property_row)

    critical_findings: list[str] = []
    if owner.status == "completed" and owner.critical_hits > 0:
        labels = ", ".join(owner.critical_labels) or "processos críticos"
        critical_findings.append(
            f"{owner.critical_hits} processo(s) crítico(s) contra o proprietário "
            f"({labels}) no {owner.tribunal}."
        )
    if owner.status == "failed":
        critical_findings.append(
            f"CNJ DataJud falhou — risco jurídico não foi verificado: {owner.skipped_reason}"
        )

    duration_ms = int((time.perf_counter() - t0) * 1000)

    result = LegalCheckResult(
        property_id=str(property_row.get("id") or ""),
        started_at=started,
        completed_at=datetime.now(timezone.utc),
        duration_ms=duration_ms,
        owner_processes=owner,
        matricula_check=matricula,
        has_critical_findings=len(critical_findings) > 0,
        critical_findings=critical_findings,
    )

    logger.info(
        "legal.run_legal_check.done",
        property_id=result.property_id,
        owner_status=owner.status,
        critical_findings=len(critical_findings),
        duration_ms=duration_ms,
    )

    return result


__all__ = ["run_legal_check"]
