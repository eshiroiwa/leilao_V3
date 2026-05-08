"""Rotas do AGENTE 3 (Análise de Oportunidade).

Endpoints:

* ``POST /properties/{id}/opportunity-analyses/preview``  – calcula sem persistir.
* ``POST /properties/{id}/opportunity-analyses``          – calcula e persiste.
* ``GET  /properties/{id}/opportunity-analyses``          – lista análises.
* ``GET  /properties/{id}/opportunity-analyses/{aid}``    – detalhe.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from app.agents.opportunity import (
    AnalysisInput,
    AnalysisResult,
    analyse_and_save,
    run_analysis,
)
from app.core.logging import get_logger
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)

router = APIRouter(prefix="/properties", tags=["opportunity"])


# =============================================================================
# Preview (stateless) — usado quando o frontend quer um cálculo "fresco"
# vindo do servidor (mesma matemática que a UI roda client-side).
# =============================================================================
@router.post(
    "/{property_id}/opportunity-analyses/preview",
    summary="Calcula uma análise SEM persistir (preview)",
    response_model=AnalysisResult,
)
async def preview_opportunity(
    property_id: UUID, payload: AnalysisInput
) -> AnalysisResult:
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
        valuation = await run_in_threadpool(
            sb.get_latest_valuation_for_property, str(property_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return run_analysis(
        inp=payload,
        property_row=prop,
        valuation=valuation,
        auctioneer_slug=prop.get("auctioneer_slug"),
    )


# =============================================================================
# Persistir
# =============================================================================
@router.post(
    "/{property_id}/opportunity-analyses",
    summary="Calcula e persiste uma análise de oportunidade",
    status_code=status.HTTP_201_CREATED,
)
async def save_opportunity(
    property_id: UUID, payload: AnalysisInput
) -> dict[str, Any]:
    sb = get_supabase_service()
    try:
        result, row = await run_in_threadpool(
            analyse_and_save,
            supabase=sb,
            property_id=str(property_id),
            inp=payload,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return {
        "id": row.get("id"),
        "result": result.model_dump(),
    }


# =============================================================================
# Listar / Detalhar
# =============================================================================
@router.get(
    "/{property_id}/opportunity-analyses",
    summary="Lista o histórico de análises de oportunidade",
)
async def list_opportunity(property_id: UUID) -> list[dict[str, Any]]:
    sb = get_supabase_service()
    try:
        return await run_in_threadpool(
            sb.list_opportunity_analyses, str(property_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.get(
    "/{property_id}/opportunity-analyses/{analysis_id}",
    summary="Detalhe de uma análise persistida",
)
async def get_opportunity(
    property_id: UUID, analysis_id: UUID
) -> dict[str, Any]:
    sb = get_supabase_service()
    try:
        row = await run_in_threadpool(
            sb.get_opportunity_analysis, str(analysis_id)
        )
    except SupabaseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    if not row or str(row.get("property_id")) != str(property_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Análise {analysis_id} não encontrada para o property {property_id}",
        )
    return row
