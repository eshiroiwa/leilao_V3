"""Gerenciador de documentos da property.

Documentos (matrícula, edital, laudo, peças processuais, outros) são
anexados a uma property sem disparar análise. A análise consolidada
(`DocumentAnalysisReport`) acontece sob demanda quando o usuário
seleciona um subconjunto e dispara via POST /documents/analyze.
"""

from app.agents.documents.schemas import (
    DOC_TYPE_LABELS,
    DocumentAnalysisReport,
    DocumentRecord,
    DocumentRef,
    DocumentType,
    LegalRisk,
    LegalRiskCategory,
    LegalRiskSeverity,
    ReportLien,
)

__all__ = [
    "DOC_TYPE_LABELS",
    "DocumentAnalysisReport",
    "DocumentRecord",
    "DocumentRef",
    "DocumentType",
    "LegalRisk",
    "LegalRiskCategory",
    "LegalRiskSeverity",
    "ReportLien",
]
