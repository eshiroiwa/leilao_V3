"""Schemas Pydantic do Agente Legal."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LegalCheckStatus = Literal["completed", "skipped", "failed"]

# Categoria legível derivada de classe processual + heurística textual.
# Usada pelo frontend para colorir / filtrar a lista de processos.
ProcessCategory = Literal[
    "anulatoria",
    "embargos_arrematacao",
    "execucao_fiscal",
    "cumprimento_sentenca",
    "execucao_titulo",
    "penhora",
    "despejo",
    "busca_apreensao",
    "trabalhista",
    "outro",
]


class ProcessSummary(BaseModel):
    """Resumo de um processo encontrado no DataJud."""

    model_config = ConfigDict(extra="forbid")

    numero_processo: str
    classe_codigo: int | None = None
    classe_nome: str | None = None
    orgao_julgador: str | None = None
    data_ajuizamento: str | None = None
    tribunal: str
    is_critical: bool = False
    category: ProcessCategory = "outro"


class OwnerProcessesResult(BaseModel):
    """Saída do nó CHECK_PROCESSES (CNJ DataJud por CPF/CNPJ).

    ``tribunals_queried`` / ``tribunals_failed`` substituem o campo
    singular ``tribunal`` em consultas multi-tribunais (TJ + TRT). O campo
    ``tribunal`` é mantido como **principal** (primeiro consultado com
    sucesso) por retrocompat com rows persistidas antes desta mudança.
    """

    model_config = ConfigDict(extra="forbid")

    status: LegalCheckStatus
    skipped_reason: str | None = None
    cpf_cnpj: str | None = None
    tribunal: str | None = None
    tribunals_queried: list[str] = Field(default_factory=list)
    tribunals_failed: list[str] = Field(default_factory=list)
    total_hits: int = 0
    critical_hits: int = 0
    critical_labels: list[str] = Field(default_factory=list)
    sample_processes: list[ProcessSummary] = Field(default_factory=list, max_length=20)
    # Lista COMPLETA dos processos encontrados (até 100 por tribunal),
    # ordenados por data desc. ``sample_processes`` permanece como
    # compactação para retrocompat com o frontend antigo.
    processes_full: list[ProcessSummary] = Field(default_factory=list)


class MatriculaCheckResult(BaseModel):
    """Saída do nó CHECK_MATRICULA (ONR — sob demanda, pago).

    Por ora um STUB: o sistema reconhece a matrícula no property, mas
    não consulta o ONR automaticamente (custo R$30-100/certidão). A
    decisão final fica para o usuário disparar via endpoint dedicado
    ou quando o ROI estimado for ≥25% (gate documentado em memória).
    """

    model_config = ConfigDict(extra="forbid")

    status: LegalCheckStatus
    skipped_reason: str | None = None
    matricula: str | None = None
    registry_office: str | None = None
    # Quando integração ONR for ativada, populamos aqui:
    onus_summary: list[str] = Field(default_factory=list)
    fetched_at: datetime | None = None


LienType = Literal[
    "hipoteca",
    "penhora",
    "usufruto",
    "alienacao_fiduciaria",
    "servidao",
    "indisponibilidade",
    "outro",
]

VisionConfidence = Literal["HIGH", "MEDIUM", "LOW"]


class MatriculaLien(BaseModel):
    """Um ônus ativo identificado na matrícula."""

    model_config = ConfigDict(extra="forbid")

    tipo: LienType
    credor: str | None = None
    valor_brl: float | None = None
    data_registro: date | None = None
    av_numero: str | None = None
    notes: str | None = Field(default=None, max_length=500)


class MatriculaOcrResult(BaseModel):
    """Saída do OCR/Vision sobre o PDF da matrícula enviado pelo usuário."""

    model_config = ConfigDict(extra="forbid")

    owner_name: str | None = None
    owner_cpf_cnpj: str | None = None
    matricula_number: str | None = None
    registry_office: str | None = None
    liens: list[MatriculaLien] = Field(default_factory=list)
    is_clear: bool = True
    confidence: VisionConfidence = "LOW"
    notes: str | None = Field(default=None, max_length=600)
    cost_estimate_usd: float | None = None
    pdf_path: str | None = None
    """Caminho relativo no bucket privado ``legal-documents``. Frontend
    usa ``GET /legal/matricula`` para receber signed URL temporária."""
    extracted_at: datetime | None = None


class WebFinding(BaseModel):
    """Resultado de busca web (Firecrawl) por termos jurídicos ligados ao proprietário."""

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    snippet: str | None = None
    query: str
    score: float = Field(ge=0.0, le=1.0)


class LegalCheckResult(BaseModel):
    """Resultado consolidado do Agente Legal."""

    model_config = ConfigDict(extra="forbid")

    property_id: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None

    owner_processes: OwnerProcessesResult
    matricula_check: MatriculaCheckResult

    # Bandeira agregada — quando True, o frontend / Agente 3 deve destacar
    # com red flag crítico no verdict.
    has_critical_findings: bool = False
    critical_findings: list[str] = Field(default_factory=list)

    # Novos canais (rodada de ampliação jurídica)
    web_findings: list[WebFinding] = Field(default_factory=list)
    matricula_ocr: MatriculaOcrResult | None = None
