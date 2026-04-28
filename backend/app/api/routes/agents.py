"""Rotas para disparar e monitorar agentes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, HttpUrl

from app.agents.scraper import run_scraper
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


# --------------------------------------------------------------------------- #
# Schemas HTTP
# --------------------------------------------------------------------------- #
class ScraperRunRequest(BaseModel):
    url: HttpUrl = Field(..., description="URL pública do lote em um leiloeiro brasileiro.")


class ScraperRunResponse(BaseModel):
    run_id: str | None
    status: str = Field(..., description="success | failed")
    duration_ms: int
    property_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    saved_property: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@router.post(
    "/scraper/run",
    response_model=ScraperRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Executa o Agente 1 (scraper + normalizador) para uma URL",
)
async def trigger_scraper(payload: ScraperRunRequest) -> ScraperRunResponse:
    logger.info("api.agents.scraper.run", url=str(payload.url))
    try:
        # ``run_scraper`` é síncrono (LangGraph + chamadas HTTP bloqueantes).
        # Usamos threadpool para não bloquear o event loop do FastAPI.
        result = await run_in_threadpool(run_scraper, str(payload.url))
    except Exception as exc:
        logger.exception("api.agents.scraper.failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha ao executar agente scraper: {exc}",
        ) from exc

    if result["status"] == "failed":
        # 200 mesmo em failed do agente — o cliente quer ver os erros estruturados.
        logger.warning("api.agents.scraper.run_failed", errors=result.get("errors"))

    return ScraperRunResponse(**result)
