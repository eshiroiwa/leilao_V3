"""Rotas de leitura, edição e remoção de imóveis."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)

router = APIRouter(prefix="/properties", tags=["properties"])


class PropertyPatch(BaseModel):
    """Whitelist do que o usuário pode editar manualmente.

    Mantemos uma whitelist explícita para não permitir, p.ex., trocar o
    ``source_url`` ou apagar o ``location`` por acidente via PATCH.
    Campos com valor ``None`` são ignorados (use string vazia para limpar).
    """

    condo_name: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Nome do prédio/condomínio. Quando preenchido, o AGENTE 2 "
            "prioriza listings do MESMO prédio nos comparáveis."
        ),
    )


@router.get(
    "",
    summary="Lista imóveis processados",
    response_model=list[dict[str, Any]],
)
async def list_properties(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
) -> list[dict[str, Any]]:
    sb = get_supabase_service()
    try:
        return await run_in_threadpool(
            sb.list_properties, limit=limit, offset=offset, status=status_filter
        )
    except SupabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{property_id}",
    summary="Atualiza campos editáveis de um imóvel (ex.: condo_name)",
    response_model=dict[str, Any],
)
async def patch_property(
    property_id: UUID, payload: PropertyPatch
) -> dict[str, Any]:
    """Patch parcial. Apenas campos definidos em ``PropertyPatch`` são aceitos.

    Tratamos string vazia como "limpar" (grava ``null``) para que o usuário
    possa apagar um valor pela UI. ``None`` (campo ausente) é ignorado.
    """
    sb = get_supabase_service()
    raw = payload.model_dump(exclude_unset=True)

    # Normaliza strings: trim + transforma "" em None (clear).
    patch: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            stripped = value.strip()
            patch[key] = stripped if stripped else None
        else:
            patch[key] = value

    if not patch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum campo válido fornecido.",
        )

    try:
        row = await run_in_threadpool(
            sb.update_property, str(property_id), patch
        )
    except SupabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Imóvel {property_id} não encontrado.",
        )
    return row


@router.delete(
    "/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um imóvel pelo UUID",
)
async def delete_property(property_id: UUID) -> None:
    sb = get_supabase_service()
    logger.info("api.properties.delete", id=str(property_id))
    try:
        deleted = await run_in_threadpool(sb.delete_property, str(property_id))
    except SupabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Imóvel {property_id} não encontrado.",
        )
    # 204 No Content — sem body
