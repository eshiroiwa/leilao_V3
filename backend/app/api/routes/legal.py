"""Rotas do Agente Legal.

Endpoints:

* ``POST /properties/{id}/legal-checks``         — dispara verificação (síncrono,
  ~1-3s consultando DataJud do TJ da UF). Persiste e devolve o resultado.
* ``GET  /properties/{id}/legal-checks/latest``  — última execução cacheada.

DataJud é gratuito e rápido (cache em memória do service + cache da row no
Supabase). ONR é stub por ora — vira parte opcional do payload no futuro.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
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

    ``scope`` e ``force_refresh`` controlam a busca DataJud:
      * ``scope="national"`` (default): consulta TODOS os 57 tribunais
        (26 TJs + 24 TRTs + 6 TRFs + STJ) em paralelo. Combina CPF e nome
        do proprietário no mesmo request.
      * ``scope="state"``: comportamento legado — só TJ + TRTs da UF.
      * ``force_refresh=True``: ignora o cache de 7 dias e força hit fresco
        em todos os tribunais (UI: botão "Reconsultar agora").
    """

    owner_name: str | None = Field(
        default=None,
        description=(
            "Nome completo do proprietário — usado nas queries Firecrawl "
            "(sinal real de descoberta). Sobrescreve `property.owner_name` "
            "apenas para esta consulta."
        ),
    )
    owner_cpf_cnpj: str | None = Field(
        default=None,
        description=(
            "CPF (11) ou CNPJ (14) — só dígitos ou com pontuação. "
            "Não é usado na busca (DataJud não indexa partes por LGPD); "
            "fica registrado para auditoria."
        ),
    )
    scope: Literal["national", "state"] = Field(
        default="national",
        description=(
            "national = todos os tribunais (default). state = só TJ+TRTs da UF."
        ),
    )
    force_refresh: bool = Field(
        default=False,
        description="True ignora cache de 7 dias e força hit fresco.",
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

    # Overrides do usuário: nome e CPF/CNPJ digitados no front são
    # aplicados ao property_row apenas para esta execução (não persistem
    # em `properties` — usuário decide quando promover). Cópia rasa para
    # não mutar o dict original devolvido pelo Supabase.
    if payload_in.owner_name and payload_in.owner_name.strip():
        prop = {**prop, "owner_name": payload_in.owner_name.strip()}
    if payload_in.owner_cpf_cnpj:
        prop = {**prop, "owner_cpf_cnpj": payload_in.owner_cpf_cnpj}

    result = await run_in_threadpool(
        run_legal_check,
        property_row=prop,
        scope=payload_in.scope,
        force_refresh=payload_in.force_refresh,
    )
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
    if not row:
        return row

    # Prioriza a matrícula mais recente em property_documents (modelo novo).
    # Cai para legal_checks.matricula_ocr.pdf_path se não houver.
    pdf_path: str | None = None
    try:
        docs = await run_in_threadpool(
            sb.list_property_documents, str(property_id)
        )
    except Exception:  # noqa: BLE001
        docs = []
    for doc in docs:
        if doc.get("doc_type") == "matricula" and doc.get("storage_path"):
            pdf_path = doc["storage_path"]
            break
    if not pdf_path and row.get("matricula_ocr"):
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
        "[DEPRECADO] Shim que anexa a matrícula como property_document sem"
        " disparar OCR. Use POST /properties/{id}/documents."
    ),
    deprecated=True,
)
async def upload_matricula(
    property_id: UUID,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Shim de retrocompat — encaminha para o gerenciador de documentos.

    Mantido para não quebrar clientes em produção que ainda chamam este
    endpoint. Sobe o PDF, cria uma row em ``property_documents`` com
    ``doc_type='matricula'`` e devolve ``matricula_ocr=null`` (a análise
    LLM agora é sob demanda via POST /properties/{id}/documents/analyze).
    """
    logger.warning(
        "legal.matricula.deprecated",
        property_id=str(property_id),
        filename=file.filename,
    )

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

    storage_path = await run_in_threadpool(
        sb.upload_legal_document,
        property_id=str(property_id),
        content=content,
        filename=file.filename or "matricula.pdf",
        content_type="application/pdf",
    )
    if not storage_path:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Falha ao enviar o arquivo ao Storage.",
        )

    payload = {
        "property_id": str(property_id),
        "doc_type": "matricula",
        "custom_label": None,
        "original_filename": file.filename or "matricula.pdf",
        "storage_path": storage_path,
        "mime_type": "application/pdf",
        "size_bytes": len(content),
    }
    try:
        row = await run_in_threadpool(sb.insert_property_document, payload)
    except SupabaseError as exc:
        await run_in_threadpool(sb.delete_legal_object, storage_path)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    signed_url = await run_in_threadpool(
        sb.get_legal_pdf_signed_url, path=storage_path
    )
    return {
        "matricula_ocr": None,
        "pdf_signed_url": signed_url,
        "document_id": row.get("id"),
        "migrated": True,
    }
