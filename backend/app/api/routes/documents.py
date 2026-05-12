"""Rotas do gerenciador de documentos da property.

Documentos sobem sem análise. O usuário visualiza via signed URL e,
quando quiser, dispara uma análise consolidada (`POST .../documents/analyze`)
que devolve um `DocumentAnalysisReport`.

Endpoints:

* ``POST   /properties/{id}/documents``                  — upload multipart.
* ``GET    /properties/{id}/documents``                  — lista da property.
* ``GET    /documents/{doc_id}/download``                — signed URL (1h).
* ``DELETE /documents/{doc_id}``                         — remove (row + obj).
* ``POST   /properties/{id}/documents/analyze``          — análise consolidada.
* ``GET    /properties/{id}/documents/analyses/latest``  — último report.
* ``GET    /documents/analyses/{analysis_id}``           — report por id.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.agents.documents.schemas import (
    DOC_TYPE_LABELS,
    DocumentAnalysisReport,
    DocumentType,
)
from app.core.logging import get_logger
from app.services.document_text_service import (
    extract_text_from_docx,
    extract_text_from_pdf,
    extract_text_from_txt,
    needs_vision_ocr,
    render_pdf_to_pngs,
)
from app.services.llm_documents_service import (
    ExtractedDoc,
    MAX_PAGES_TOTAL,
    get_documents_analysis_service,
)
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)

# Dois routers no mesmo arquivo: rotas sob /properties (escopo property) e
# rotas sob /documents (escopo doc individual e análise por id).
router_property = APIRouter(prefix="/properties", tags=["documents"])
router_document = APIRouter(prefix="/documents", tags=["documents"])


# -----------------------------------------------------------------------------
# Validações & limites
# -----------------------------------------------------------------------------

MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB por arquivo
MAX_PROPERTY_TOTAL_BYTES = 200 * 1024 * 1024  # 200 MB somatório por property

# Whitelist de content-types aceitos no upload.
ALLOWED_MIME: dict[str, tuple[str, ...]] = {
    "application/pdf": ("application/pdf", "application/x-pdf"),
    "image/jpeg": ("image/jpeg", "image/jpg"),
    "image/png": ("image/png",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "text/plain": ("text/plain",),
}
_ALLOWED_FLAT = {alias for aliases in ALLOWED_MIME.values() for alias in aliases}

# Magic numbers para sniff dos primeiros bytes (defesa contra renomeação).
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"PK\x03\x04", "application/zip"),  # DOCX é zip
]

DOC_TYPES_SET: set[str] = set(DOC_TYPE_LABELS.keys())


def _sniff_mime(content: bytes) -> str | None:
    """Retorna um MIME canônico baseado nos primeiros bytes, ou ``None``."""
    head = content[:16]
    for magic, mime in _MAGIC_SIGNATURES:
        if head.startswith(magic):
            return mime
    # TXT: sem assinatura — aceita se decode utf-8 ou latin-1 for limpo.
    try:
        content[: min(len(content), 4096)].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return None


def _canonical_mime(content_type: str | None, sniffed: str | None) -> str | None:
    """Concilia content-type declarado com sniff dos bytes.

    Regras:
      * Se sniff é PDF/imagem, ele manda (é mais confiável que o header).
      * Se sniff é zip e content-type é DOCX, aceita como DOCX.
      * Se sniff é text/plain e content-type é text/plain, aceita.
      * Caso contrário, rejeita.
    """
    declared = (content_type or "").split(";")[0].strip().lower()
    if sniffed in ("application/pdf", "image/jpeg", "image/png"):
        return sniffed
    if sniffed == "application/zip" and declared == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        return declared
    if sniffed == "text/plain" and declared == "text/plain":
        return "text/plain"
    return None


def _validate_upload(
    *, content: bytes, declared_type: str | None
) -> str:
    """Valida tamanho + MIME (whitelist + sniff). Retorna MIME canônico."""
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio.")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Arquivo acima do limite ({MAX_FILE_BYTES // (1024 * 1024)} MB).",
        )
    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared and declared not in _ALLOWED_FLAT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Content-type '{declared}' não suportado. Aceitos: PDF, JPG, PNG, DOCX, TXT.",
        )
    sniffed = _sniff_mime(content)
    canonical = _canonical_mime(declared, sniffed)
    if canonical is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Conteúdo do arquivo não bate com a extensão/declarado "
            "(sniff de assinatura falhou).",
        )
    return canonical


def _row_to_record(row: dict[str, Any], *, signed_url: str | None = None) -> dict[str, Any]:
    """Acrescenta ``signed_url`` (opcional) ao dict da row para o frontend."""
    return {**row, "signed_url": signed_url}


def _doc_label_from_row(row: dict[str, Any]) -> str:
    custom = row.get("custom_label")
    if custom:
        return custom
    return DOC_TYPE_LABELS.get(row.get("doc_type") or "", row.get("doc_type") or "doc")


# -----------------------------------------------------------------------------
# Upload
# -----------------------------------------------------------------------------


@router_property.post(
    "/{property_id}/documents",
    summary="Anexa um documento à property (sem disparar análise).",
)
async def upload_document(
    property_id: UUID,
    file: Annotated[UploadFile, File(...)],
    doc_type: Annotated[str, Form(...)],
    custom_label: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    if doc_type not in DOC_TYPES_SET:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"doc_type inválido. Aceitos: {sorted(DOC_TYPES_SET)}.",
        )
    label = (custom_label or "").strip() or None
    if doc_type == "outros" and not label:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "custom_label é obrigatório quando doc_type='outros'.",
        )
    if doc_type != "outros" and label:
        # Reforça invariante do CHECK constraint.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "custom_label só pode ser informado quando doc_type='outros'.",
        )

    content = await file.read()
    canonical_mime = _validate_upload(
        content=content, declared_type=file.content_type
    )

    sb = get_supabase_service()
    try:
        prop = await run_in_threadpool(sb.get_property_by_id, str(property_id))
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not prop:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Property {property_id} não encontrado."
        )

    # Cap soft de tamanho total por property.
    try:
        total = await run_in_threadpool(
            sb.get_property_documents_total_size, str(property_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if total + len(content) > MAX_PROPERTY_TOTAL_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            (
                f"Soma de documentos desta property excederia o limite "
                f"({MAX_PROPERTY_TOTAL_BYTES // (1024 * 1024)} MB)."
            ),
        )

    filename = file.filename or "documento"
    storage_path = await run_in_threadpool(
        sb.upload_legal_document,
        property_id=str(property_id),
        content=content,
        filename=filename,
        content_type=canonical_mime,
    )
    if not storage_path:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Falha ao enviar o arquivo ao Storage.",
        )

    payload = {
        "property_id": str(property_id),
        "doc_type": doc_type,
        "custom_label": label,
        "original_filename": filename,
        "storage_path": storage_path,
        "mime_type": canonical_mime,
        "size_bytes": len(content),
    }
    try:
        row = await run_in_threadpool(sb.insert_property_document, payload)
    except SupabaseError as exc:
        # Storage já recebeu o objeto; melhor tentar limpar para não deixar
        # órfão no bucket.
        await run_in_threadpool(sb.delete_legal_object, storage_path)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    signed_url = await run_in_threadpool(
        sb.get_legal_pdf_signed_url, path=storage_path
    )
    return _row_to_record(row, signed_url=signed_url)


# -----------------------------------------------------------------------------
# Listagem
# -----------------------------------------------------------------------------


@router_property.get(
    "/{property_id}/documents",
    summary="Lista os documentos anexados à property (com signed URLs).",
)
async def list_documents(property_id: UUID) -> list[dict[str, Any]]:
    sb = get_supabase_service()
    try:
        rows = await run_in_threadpool(
            sb.list_property_documents, str(property_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    out: list[dict[str, Any]] = []
    for row in rows:
        path = row.get("storage_path")
        signed_url: str | None = None
        if path:
            signed_url = await run_in_threadpool(
                sb.get_legal_pdf_signed_url, path=path
            )
        out.append(_row_to_record(row, signed_url=signed_url))
    return out


# -----------------------------------------------------------------------------
# Download (signed URL on-demand)
# -----------------------------------------------------------------------------


@router_document.get(
    "/{document_id}/download",
    summary="Devolve signed URL (1h) para visualização do documento.",
)
async def download_document(document_id: UUID) -> dict[str, Any]:
    sb = get_supabase_service()
    try:
        row = await run_in_threadpool(
            sb.get_property_document, str(document_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not row:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Documento {document_id} não encontrado."
        )
    path = row.get("storage_path")
    if not path:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "storage_path ausente no registro."
        )
    signed_url = await run_in_threadpool(
        sb.get_legal_pdf_signed_url, path=path
    )
    if not signed_url:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Falha ao gerar signed URL — tente novamente.",
        )
    return {"signed_url": signed_url}


# -----------------------------------------------------------------------------
# Delete
# -----------------------------------------------------------------------------


@router_document.delete(
    "/{document_id}",
    summary="Remove o documento (row + objeto no Storage).",
)
async def delete_document(document_id: UUID) -> dict[str, Any]:
    sb = get_supabase_service()
    try:
        deleted = await run_in_threadpool(
            sb.delete_property_document, str(document_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not deleted:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Documento {document_id} não encontrado."
        )
    path = deleted.get("storage_path")
    if path:
        # Best-effort. Falha no Storage não invalida a remoção da row.
        await run_in_threadpool(sb.delete_legal_object, path)
    return {"deleted": True, "id": str(document_id)}


# -----------------------------------------------------------------------------
# Análise consolidada
# -----------------------------------------------------------------------------


class AnalyzeDocumentsRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=20)


def _materialize_doc(row: dict[str, Any], content: bytes) -> ExtractedDoc:
    """Converte uma row + bytes em ``ExtractedDoc`` (texto e/ou imagens)."""
    doc_type: DocumentType = row["doc_type"]
    document_id = UUID(str(row["id"]))
    label = _doc_label_from_row(row)
    mime = (row.get("mime_type") or "").lower()

    if mime == "application/pdf":
        text, n_pages = extract_text_from_pdf(content)
        if needs_vision_ocr(text, n_pages):
            images = render_pdf_to_pngs(content)
            return ExtractedDoc(
                document_id=document_id,
                doc_type=doc_type,
                label=label,
                text="",
                images=images,
            )
        return ExtractedDoc(
            document_id=document_id,
            doc_type=doc_type,
            label=label,
            text=text,
            images=[],
        )
    if mime in ("image/jpeg", "image/png"):
        return ExtractedDoc(
            document_id=document_id,
            doc_type=doc_type,
            label=label,
            text="",
            images=[content],
        )
    if mime == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        return ExtractedDoc(
            document_id=document_id,
            doc_type=doc_type,
            label=label,
            text=extract_text_from_docx(content),
            images=[],
        )
    if mime == "text/plain":
        return ExtractedDoc(
            document_id=document_id,
            doc_type=doc_type,
            label=label,
            text=extract_text_from_txt(content),
            images=[],
        )
    # Mime desconhecido — entra como texto vazio para o LLM ao menos
    # registrar a presença do doc.
    return ExtractedDoc(
        document_id=document_id,
        doc_type=doc_type,
        label=label,
        text="",
        images=[],
    )


@router_property.post(
    "/{property_id}/documents/analyze",
    summary="Análise LLM consolidada dos documentos selecionados.",
)
async def analyze_documents(
    property_id: UUID,
    payload_in: AnalyzeDocumentsRequest,
) -> dict[str, Any]:
    sb = get_supabase_service()
    ids = [str(i) for i in payload_in.document_ids]

    try:
        rows = await run_in_threadpool(sb.get_property_documents_by_ids, ids)
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    # Filtra docs que realmente pertencem à property — defesa contra
    # passar UUIDs cruzados.
    rows = [r for r in rows if str(r.get("property_id")) == str(property_id)]
    if not rows:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Nenhum documento válido encontrado para esta property.",
        )

    # Preserva ordem solicitada (best-effort).
    rows.sort(key=lambda r: ids.index(str(r["id"])) if str(r["id"]) in ids else 0)

    docs: list[ExtractedDoc] = []
    for row in rows:
        path = row.get("storage_path")
        if not path:
            continue
        content = await run_in_threadpool(sb.download_legal_object, path)
        if content is None:
            logger.warning(
                "documents.analyze.download_failed",
                document_id=row.get("id"),
                path=path,
            )
            continue
        try:
            docs.append(
                await run_in_threadpool(_materialize_doc, row, content)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "documents.analyze.materialize_failed",
                document_id=row.get("id"),
                error=str(exc),
            )

    if not docs:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Nenhum documento pôde ser materializado para análise.",
        )

    service = get_documents_analysis_service()
    report = await run_in_threadpool(
        service.analyze, docs, max_pages_total=MAX_PAGES_TOTAL
    )
    if report is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Falha na análise LLM — tente novamente em alguns instantes.",
        )

    persist_payload = {
        "property_id": str(property_id),
        "document_ids": [str(d.document_id) for d in docs],
        "report": report.model_dump(mode="json"),
        "confidence": report.confidence,
        "has_critical_findings": report.critical_findings,
        "cost_usd": report.cost_usd,
        "model": report.model,
    }
    try:
        saved = await run_in_threadpool(
            sb.insert_document_analysis, persist_payload
        )
    except SupabaseError as exc:
        # Não invalida a resposta — devolve o report mesmo sem persistir.
        logger.warning("documents.analyze.persist_failed", error=str(exc))
        saved = {**persist_payload, "id": None}

    return saved


@router_property.get(
    "/{property_id}/documents/analyses/latest",
    summary="Última análise consolidada da property (ou null).",
)
async def get_latest_analysis(property_id: UUID) -> dict[str, Any] | None:
    sb = get_supabase_service()
    try:
        row = await run_in_threadpool(
            sb.get_latest_document_analysis, str(property_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return row


@router_document.get(
    "/analyses/{analysis_id}",
    summary="Busca uma análise consolidada por id.",
)
async def get_analysis_by_id(analysis_id: UUID) -> dict[str, Any]:
    sb = get_supabase_service()
    try:
        row = await run_in_threadpool(
            sb.get_document_analysis, str(analysis_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not row:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Análise {analysis_id} não encontrada."
        )
    return row


__all__ = [
    "AnalyzeDocumentsRequest",
    "DocumentAnalysisReport",
    "router_document",
    "router_property",
]
