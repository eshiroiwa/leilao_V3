"""Schemas Pydantic do gerenciador de documentos.

CRÍTICO: ``DocumentType`` é espelhado por um CHECK constraint em
``property_documents.doc_type`` (migration 021). Qualquer adição/remoção
de literal aqui PRECISA acompanhar uma migration DROP/ADD CONSTRAINT.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# -----------------------------------------------------------------------------
# Tipos canônicos
# -----------------------------------------------------------------------------

DocumentType = Literal[
    "matricula",
    "edital",
    "laudo_avaliacao",
    "pecas_processuais",
    "outros",
]

DOC_TYPE_LABELS: dict[str, str] = {
    "matricula": "Matrícula",
    "edital": "Edital do leilão",
    "laudo_avaliacao": "Laudo de avaliação",
    "pecas_processuais": "Peças processuais",
    "outros": "Outros",
}

LegalRiskSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

LegalRiskCategory = Literal[
    "onus",
    "processo_ativo",
    "irregularidade_registral",
    "vicio_edital",
    "ocupacao",
    "tributario",
    "outro",
]

# Reaproveita o vocabulário de ônus do Agente Legal — evita duplicação e
# permite mesclar com `matricula_ocr.liens` quando relevante.
ReportLienType = Literal[
    "hipoteca",
    "penhora",
    "usufruto",
    "alienacao_fiduciaria",
    "servidao",
    "indisponibilidade",
    "outro",
]

ReportConfidence = Literal["HIGH", "MEDIUM", "LOW"]


# -----------------------------------------------------------------------------
# Row mirror (property_documents)
# -----------------------------------------------------------------------------


class DocumentRecord(BaseModel):
    """Espelho da row em ``property_documents`` (mais ``signed_url`` opcional)."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    property_id: UUID
    doc_type: DocumentType
    custom_label: str | None = None
    original_filename: str
    storage_path: str
    mime_type: str
    size_bytes: int
    uploaded_by: str | None = None
    created_at: datetime
    signed_url: str | None = None


# -----------------------------------------------------------------------------
# Relatório consolidado
# -----------------------------------------------------------------------------


class DocumentRef(BaseModel):
    """Referência a um doc dentro do report (com label resolvido)."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    doc_type: DocumentType
    label: str  # custom_label OU DOC_TYPE_LABELS[doc_type]


class ReportLien(BaseModel):
    """Um ônus identificado durante a análise consolidada."""

    model_config = ConfigDict(extra="forbid")

    tipo: ReportLienType
    credor: str | None = None
    valor_brl: float | None = None
    data_registro: date | None = None
    source_document_id: UUID
    notes: str | None = Field(default=None, max_length=500)


class LegalRisk(BaseModel):
    """Um risco jurídico/registral identificado no conjunto de docs."""

    model_config = ConfigDict(extra="forbid")

    severity: LegalRiskSeverity
    category: LegalRiskCategory
    description: str = Field(max_length=600)
    source_document_ids: list[UUID] = Field(default_factory=list)


class DocumentAnalysisReport(BaseModel):
    """Saída estruturada da análise consolidada de N documentos.

    Persistido em ``document_analyses.report`` (jsonb). Os campos
    hot-path (``confidence``, ``has_critical_findings``, ``cost_usd``,
    ``model``) também viram colunas na row para listagem rápida.
    """

    model_config = ConfigDict(extra="forbid")

    documents_analyzed: list[DocumentRef] = Field(default_factory=list)
    liens: list[ReportLien] = Field(default_factory=list, max_length=50)
    risks: list[LegalRisk] = Field(default_factory=list, max_length=50)
    critical_findings: bool = False
    critical_findings_summary: list[str] = Field(default_factory=list, max_length=20)
    recommendations: list[str] = Field(default_factory=list, max_length=20)
    confidence: ReportConfidence = "LOW"
    cost_usd: float = 0.0
    extracted_at: datetime | None = None
    model: str = ""
    notes: str | None = Field(default=None, max_length=1000)


# -----------------------------------------------------------------------------
# Schema solicitado ao LLM (sem cost_usd/model/extracted_at — esses são
# preenchidos pelo backend após a chamada).
# -----------------------------------------------------------------------------


class DocumentAnalysisLLMPayload(BaseModel):
    """Mesmo conteúdo de ``DocumentAnalysisReport`` mas sem os metadados
    que o backend (e não o LLM) calcula. Usado em ``with_structured_output``.
    """

    model_config = ConfigDict(extra="forbid")

    liens: list[ReportLien] = Field(default_factory=list, max_length=50)
    risks: list[LegalRisk] = Field(default_factory=list, max_length=50)
    critical_findings: bool = False
    critical_findings_summary: list[str] = Field(default_factory=list, max_length=20)
    recommendations: list[str] = Field(default_factory=list, max_length=20)
    confidence: ReportConfidence = "LOW"
    notes: str | None = Field(default=None, max_length=1000)


__all__ = [
    "DOC_TYPE_LABELS",
    "DocumentAnalysisLLMPayload",
    "DocumentAnalysisReport",
    "DocumentRecord",
    "DocumentRef",
    "DocumentType",
    "LegalRisk",
    "LegalRiskCategory",
    "LegalRiskSeverity",
    "ReportConfidence",
    "ReportLien",
    "ReportLienType",
]
