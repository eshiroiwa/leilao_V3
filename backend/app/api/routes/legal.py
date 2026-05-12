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

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.agents.legal.service import run_legal_check
from app.core.logging import get_logger
from app.services.matricula_ocr_service import (
    MatriculaOcrError,
    extract_matricula,
)
from app.services.supabase_service import SupabaseError, get_supabase_service
from app.services.vision_service import get_vision_service

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
        "web_findings": [f.model_dump(mode="json") for f in result.web_findings],
        "matricula_ocr": (
            result.matricula_ocr.model_dump(mode="json")
            if result.matricula_ocr is not None
            else None
        ),
        "processes_full": [
            p.model_dump(mode="json") for p in result.owner_processes.processes_full
        ],
    }


# Limite de tamanho do PDF de matrícula (10 MB). Matrículas digitalizadas
# costumam ter 1-5 MB; acima disso é provavelmente PDF não otimizado.
_MATRICULA_MAX_BYTES = 10 * 1024 * 1024


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
    if row and row.get("matricula_ocr"):
        # Anexa signed URL temporária do PDF para o frontend renderizar
        # o link "baixar PDF original".
        pdf_path = (row["matricula_ocr"] or {}).get("pdf_path")
        if pdf_path:
            signed = await run_in_threadpool(
                sb.get_legal_pdf_signed_url, path=pdf_path
            )
            row["matricula_pdf_signed_url"] = signed
    return row


@router.post(
    "/{property_id}/legal/matricula",
    summary=(
        "Sobe um PDF de matrícula, faz OCR estruturado via Vision e persiste"
        " no último legal_check (ou cria um novo)."
    ),
)
async def upload_matricula(
    property_id: UUID,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Esperado PDF, recebido content-type='{file.content_type}'.",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF vazio.")
    if len(content) > _MATRICULA_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"PDF acima do limite ({_MATRICULA_MAX_BYTES // (1024 * 1024)} MB).",
        )

    sb = get_supabase_service()
    try:
        prop = await run_in_threadpool(sb.get_property_by_id, str(property_id))
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not prop:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Property {property_id} não encontrado"
        )

    # 1. Upload do PDF no bucket privado (path, não URL pública).
    pdf_path = await run_in_threadpool(
        sb.upload_legal_pdf,
        property_id=str(property_id),
        content=content,
    )

    # 2. OCR via Vision (síncrono, joga em threadpool).
    vision = get_vision_service()
    try:
        ocr_result = await run_in_threadpool(
            extract_matricula,
            content,
            vision=vision,
            pdf_path=pdf_path,
        )
    except MatriculaOcrError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # 3. Persiste no último legal_check (UPDATE) ou cria placeholder mínimo.
    latest = await run_in_threadpool(
        sb.get_latest_legal_check, str(property_id)
    )
    matricula_ocr_json = ocr_result.model_dump(mode="json")
    if latest and latest.get("id"):
        try:
            await run_in_threadpool(
                sb.update_legal_check,
                latest["id"],
                {"matricula_ocr": matricula_ocr_json},
            )
        except SupabaseError as exc:
            logger.warning("legal.matricula.persist_failed", error=str(exc))
    else:
        # Não há legal_check ainda — cria um placeholder só com a matrícula.
        placeholder = {
            "property_id": str(property_id),
            "started_at": ocr_result.extracted_at.isoformat()
            if ocr_result.extracted_at
            else None,
            "completed_at": ocr_result.extracted_at.isoformat()
            if ocr_result.extracted_at
            else None,
            "duration_ms": 0,
            "owner_processes": None,
            "matricula_check": None,
            "has_critical_findings": False,
            "critical_findings": [],
            "matricula_ocr": matricula_ocr_json,
        }
        try:
            await run_in_threadpool(sb.insert_legal_check, placeholder)
        except SupabaseError as exc:
            logger.warning("legal.matricula.placeholder_failed", error=str(exc))

    # 4. Devolve OCR + signed URL para download imediato.
    signed_url: str | None = None
    if pdf_path:
        signed_url = await run_in_threadpool(
            sb.get_legal_pdf_signed_url, path=pdf_path
        )
    return {
        "matricula_ocr": matricula_ocr_json,
        "pdf_signed_url": signed_url,
    }
