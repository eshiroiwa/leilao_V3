"""Agente Legal — verifica risco jurídico/registral por property.

Consulta:
  * CNJ DataJud (gratuito): processos contra o proprietário/executado;
  * ONR (futuro, sob demanda): matrícula online — só quando ROI estimado
    >= 25% (regra registrada em memória do projeto).

Pipeline orquestrado por ``service.run_legal_check`` (síncrono — DataJud
é rápido, ONR é manual). Resultado persiste em ``legal_checks``.
"""

from app.agents.legal.schemas import (
    LegalCheckResult,
    OwnerProcessesResult,
    MatriculaCheckResult,
)
from app.agents.legal.service import run_legal_check

__all__ = [
    "LegalCheckResult",
    "OwnerProcessesResult",
    "MatriculaCheckResult",
    "run_legal_check",
]
