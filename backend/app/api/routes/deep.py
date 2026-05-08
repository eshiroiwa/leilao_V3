"""Rotas do AGENTE 4 (Deep Analysis).

Endpoints:

* ``POST /properties/{id}/deep-analyses``           – dispara em background; 202.
* ``GET  /properties/{id}/deep-analyses``           – histórico.
* ``GET  /properties/{id}/deep-analyses/latest``    – mais recente (cache hint).
* ``GET  /deep-analyses/{aid}``                     – detalhe (polling do front).

Modelo de execução: o ``POST`` não bloqueia. Usa cache de 7 dias se não
solicitado ``force_refresh``; senão cria uma row ``status='pending'`` e
agenda a tarefa via FastAPI ``BackgroundTasks``. O frontend faz polling
em ``GET /deep-analyses/{id}`` até ``status`` virar ``completed`` ou
``failed``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.agents.deep.service import (
    enqueue_deep_analysis,
    get_or_create_deep_analysis,
    reap_stale_running,
)
from app.core.logging import get_logger
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)

router_property = APIRouter(prefix="/properties", tags=["deep-analysis"])
router_global = APIRouter(prefix="/deep-analyses", tags=["deep-analysis"])


class DeepAnalysisRequest(BaseModel):
    opportunity_analysis_id: str | None = None
    force_refresh: bool = False


# =============================================================================
# POST — dispara o agente
# =============================================================================
@router_property.post(
    "/{property_id}/deep-analyses",
    summary="Dispara uma análise aprofundada (assíncrona). Retorna a row pendente ou cacheada.",
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_deep_analysis(
    property_id: UUID,
    payload: DeepAnalysisRequest,
    background_tasks: BackgroundTasks,
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

    try:
        row, should_run = await run_in_threadpool(
            get_or_create_deep_analysis,
            supabase=sb,
            property_id=str(property_id),
            opportunity_analysis_id=payload.opportunity_analysis_id,
            force_refresh=payload.force_refresh,
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    if should_run:
        background_tasks.add_task(enqueue_deep_analysis, row["id"])

    return {
        "id": row["id"],
        "status": row.get("status", "pending"),
        "from_cache": not should_run,
        "row": row if not should_run else None,
    }


# =============================================================================
# GET (lista)
# =============================================================================
@router_property.get(
    "/{property_id}/deep-analyses",
    summary="Lista análises aprofundadas do imóvel",
)
async def list_deep_analyses(property_id: UUID) -> list[dict[str, Any]]:
    sb = get_supabase_service()
    try:
        # Limpa "running" presos (server crash) — operação leve.
        await run_in_threadpool(reap_stale_running, sb, str(property_id))
        return await run_in_threadpool(
            sb.list_deep_analyses, str(property_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router_property.get(
    "/{property_id}/deep-analyses/latest",
    summary="Última análise completada (ou null)",
)
async def latest_deep_analysis(property_id: UUID) -> dict[str, Any] | None:
    sb = get_supabase_service()
    try:
        return await run_in_threadpool(
            sb.get_latest_completed_deep_analysis, str(property_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


# =============================================================================
# GET (detalhe — usado pelo polling do frontend)
# =============================================================================
@router_global.get(
    "/{analysis_id}",
    summary="Detalhe de uma análise (frontend faz polling até completed/failed)",
)
async def get_deep_analysis(analysis_id: UUID) -> dict[str, Any]:
    sb = get_supabase_service()
    try:
        row = await run_in_threadpool(
            sb.get_deep_analysis, str(analysis_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if not row:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Deep analysis {analysis_id} não encontrada"
        )
    return row
