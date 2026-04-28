"""Rotas de leitura e remoção de imóveis."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)

router = APIRouter(prefix="/properties", tags=["properties"])


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
