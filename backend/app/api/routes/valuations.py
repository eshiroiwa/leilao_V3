"""Rotas do AGENTE 2 (Comparáveis / CMA)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from app.agents.comparables.graph import run_comparables
from app.core.logging import get_logger
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)

router = APIRouter(prefix="/properties", tags=["valuations"])


@router.post(
    "/{property_id}/valuate",
    summary="Dispara o AGENTE 2 (CMA) para um imóvel",
    status_code=status.HTTP_201_CREATED,
)
async def valuate_property(property_id: UUID) -> dict[str, Any]:
    logger.info("api.valuate.start", property_id=str(property_id))
    try:
        final = await run_in_threadpool(run_comparables, str(property_id))
    except Exception as exc:
        logger.exception("api.valuate.exception")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha ao executar avaliação: {exc}",
        ) from exc

    if final.get("errors") and not final.get("valuation_id"):
        # Erros fatais antes da persistência: 422 (entrada inviável).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errors": final.get("errors"),
                "warnings": final.get("warnings"),
            },
        )

    return {
        "valuation_id": final.get("valuation_id"),
        "confidence": final.get("confidence"),
        "estimated_price": final.get("estimated_price"),
        "price_lower_bound": final.get("price_lower_bound"),
        "price_upper_bound": final.get("price_upper_bound"),
        "ppm2_estimated": final.get("ppm2_estimated"),
        "comparables_used": sum(
            1 for s in (final.get("scored_comparables") or []) if s.get("used")
        ),
        "search_strategy": final.get("search_strategy"),
        "search_radius_m": final.get("search_radius_m"),
        "firecrawl_calls": final.get("firecrawl_calls"),
        "llm_calls": final.get("llm_calls"),
        "cost_estimate_brl": final.get("cost_estimate_brl"),
        "warnings": final.get("warnings") or [],
    }


@router.get(
    "/{property_id}/valuations",
    summary="Lista o histórico de avaliações de um imóvel",
)
async def list_property_valuations(property_id: UUID) -> list[dict[str, Any]]:
    sb = get_supabase_service()
    try:
        return await run_in_threadpool(
            sb.list_valuations_by_property, str(property_id)
        )
    except SupabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get(
    "/{property_id}/valuations/{valuation_id}",
    summary="Detalhe de uma avaliação (com comparáveis usados)",
)
async def get_valuation_detail(property_id: UUID, valuation_id: UUID) -> dict[str, Any]:
    sb = get_supabase_service()
    try:
        val = await run_in_threadpool(
            sb.get_valuation_with_comparables, str(valuation_id)
        )
    except SupabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    if val is None or str(val.get("property_id")) != str(property_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valuation {valuation_id} não encontrada para o property {property_id}",
        )
    return val
