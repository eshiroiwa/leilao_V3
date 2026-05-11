"""Schemas Pydantic do Agente Legal."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LegalCheckStatus = Literal["completed", "skipped", "failed"]


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


class OwnerProcessesResult(BaseModel):
    """Saída do nó CHECK_PROCESSES (CNJ DataJud por CPF/CNPJ)."""

    model_config = ConfigDict(extra="forbid")

    status: LegalCheckStatus
    skipped_reason: str | None = None
    cpf_cnpj: str | None = None
    tribunal: str | None = None
    total_hits: int = 0
    critical_hits: int = 0
    critical_labels: list[str] = Field(default_factory=list)
    sample_processes: list[ProcessSummary] = Field(default_factory=list, max_length=10)


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
