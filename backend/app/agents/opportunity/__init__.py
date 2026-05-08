"""AGENTE 3 — Análise de Oportunidade.

API pública:
    * :class:`AnalysisInput`, :class:`AnalysisResult`, :class:`Scenario` — schemas.
    * :func:`run_analysis` — cálculo puro (sem efeitos).
    * :func:`analyse_and_save` — calcula + persiste.
"""

from app.agents.opportunity.schemas import (
    AnalysisInput,
    AnalysisResult,
    AssumptionsSnapshot,
    Scenario,
)
from app.agents.opportunity.service import analyse_and_save, run_analysis

__all__ = [
    "AnalysisInput",
    "AnalysisResult",
    "AssumptionsSnapshot",
    "Scenario",
    "analyse_and_save",
    "run_analysis",
]
