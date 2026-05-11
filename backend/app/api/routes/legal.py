"""Rotas do Agente Legal.

Endpoints:

* ``POST /properties/{id}/legal-checks``         — dispara verificação (síncrono,
  ~1-3s consultando DataJud do TJ da UF). Persiste e devolve o resultado.
* ``GET  /properties/{id}/legal-checks/latest``  — última execução cacheada.

DataJud é gratuito e rápido (cache em memória do service + cache da row no
Supabase). ONR é stub por ora — vira parte opcional do payload no futuro.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.agents.legal.service import run_legal_check
from app.core.logging import get_logger
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)

router = APIRouter(prefix="/properties", tags=["legal-check"])


class LegalCheckRequest(BaseModel):
    """Body opcional do POST /legal-checks.

    Quando o Scraper não conseguiu extrair o CPF/CNPJ do edital, o usuário
    pode informar manualmente aqui. O valor digitado é normalizado para
    apenas dígitos e tem PRIORIDADE sobre o que está em `properties`.
    Persistência não é alterada — a row em `properties` permanece como
    estava; o override vale só para esta verificação.
    """

    owner_cpf_cnpj: str | None = Field(
        default=None,
        description="CPF (11) ou CNPJ (14) — só dígitos ou com pontuação.",
    )


def _legal_result_to_payload(
    property_id: str, result: Any
) -> dict[str, Any]:
    """Converte ``LegalCheckResult`` no payload para o jsonb da row."""
    return {
        "property_id": property_id,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat()
        if result.completed_at
        else None,
        "duration_ms": result.duration_ms,
        "owner_processes": result.owner_processes.model_dump(mode="json"),
        "matricula_check": result.matricula_check.model_dump(mode="json"),
        "has_critical_findings": result.has_critical_findings,
        "critical_findings": result.critical_findings,
    }


@router.post(
    "/{property_id}/legal-checks",
    summary="Roda uma verificação jurídica (CNJ DataJud + ONR stub) e persiste o resultado.",
)
async def create_legal_check(
    property_id: UUID,
    payload_in: LegalCheckRequest = LegalCheckRequest(),
) -> dict[str, Any]:
    sb = get_supabase_service()

    try:
        prop = await run_in_threadpool(sb.get_property_by_id, str(property_id))
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not prop:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Property {property_id} não encontrado"
        )

    # Override do usuário: o CPF/CNPJ digitado no front é colocado no
    # property_row apenas para esta execução (não persiste em `properties`
    # — usuário decide quando promover). Normalização ficamos a cargo do
    # service via _normalize_cpf_cnpj idempotente.
    if payload_in.owner_cpf_cnpj:
        # Cópia rasa — não muta o dict original devolvido pelo Supabase.
        prop = {**prop, "owner_cpf_cnpj": payload_in.owner_cpf_cnpj}

    result = await run_in_threadpool(run_legal_check, property_row=prop)
    payload = _legal_result_to_payload(str(property_id), result)

    try:
        saved = await run_in_threadpool(sb.insert_legal_check, payload)
    except SupabaseError as exc:
        # Falha de persistência não inviabiliza o retorno — usuário vê o
        # resultado mas terá que disparar de novo para gravar.
        logger.warning("legal_check.persist_failed", error=str(exc))
        saved = {**payload, "id": None}

    return saved


@router.get(
    "/{property_id}/legal-checks/latest",
    summary="Última verificação jurídica persistida (ou null).",
)
async def get_latest_legal_check(property_id: UUID) -> dict[str, Any] | None:
    sb = get_supabase_service()
    try:
        row = await run_in_threadpool(
            sb.get_latest_legal_check, str(property_id)
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return row
