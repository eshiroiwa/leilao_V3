"""Nó CHECK_MATRICULA — ONR (Operador Nacional do Registro de Imóveis).

ATUAL: STUB. Reconhece a matrícula no property mas NÃO consulta o ONR
automaticamente. A integração paga (~R$30-100/certidão) é decisão do
usuário registrada em memória — ativar quando o ROI estimado ≥ 25%.

Por ora, devolve um resultado que sinaliza "matrícula disponível mas
não consultada", deixando o caminho aberto para integração futura sem
mexer no schema.
"""

from __future__ import annotations

from app.agents.legal.schemas import MatriculaCheckResult
from app.core.logging import get_logger

logger = get_logger(__name__)


def check_matricula(*, property_row: dict) -> MatriculaCheckResult:
    """STUB do nó ONR — não bate na rede.

    Devolve ``status=skipped`` com ``skipped_reason`` indicando o motivo.
    Quando a integração ONR for ativada, basta plugar o cliente aqui.
    """
    matricula = (property_row.get("matricula") or "").strip()
    registry_office = (property_row.get("registry_office") or "").strip() or None

    if not matricula:
        return MatriculaCheckResult(
            status="skipped",
            skipped_reason="property sem `matricula` — scraper não extraiu.",
        )

    logger.info(
        "legal.check_matricula.deferred",
        matricula=matricula,
        registry_office=registry_office,
    )
    return MatriculaCheckResult(
        status="skipped",
        matricula=matricula,
        registry_office=registry_office,
        skipped_reason=(
            "ONR não integrado nesta versão — consulta paga sob demanda "
            "(gated por ROI ≥ 25% conforme preferência registrada)."
        ),
    )


__all__ = ["check_matricula"]
