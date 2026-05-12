"""Endpoints de taxas de mercado para uso no AGENTE 3 (Opportunity).

Hoje só `GET /market-rates/loan` — taxa média do financiamento imobiliário
PF SBPE (BACEN SGS 25497). Cacheado pelo próprio ``BacenService``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.services.bacen_service import get_bacen_service

logger = get_logger(__name__)

router = APIRouter(prefix="/market-rates", tags=["market-rates"])

# Fallback quando o BACEN está fora do ar. ~11,5% a.a. está alinhado com a
# média recente de financiamento imobiliário PF SBPE (2025-2026).
LOAN_RATE_FALLBACK: float = 0.115


@router.get(
    "/loan",
    summary="Taxa média de financiamento imobiliário PF (BACEN SGS 25497)",
)
async def get_market_loan_rate() -> dict[str, Any]:
    """Retorna ``{rate_annual_pct, source, asof}``.

    Em falha do BACEN, devolve o fallback (11,5% a.a.) com ``source='fallback'``.
    Nunca lança — o caller espera sempre um número usável.
    """
    bacen = get_bacen_service()
    rate = await run_in_threadpool(bacen.get_avg_real_estate_loan_annual)
    if rate is None or rate <= 0:
        return {
            "rate_annual_pct": LOAN_RATE_FALLBACK,
            "source": "fallback",
            "asof": datetime.utcnow().date().isoformat(),
        }
    return {
        "rate_annual_pct": round(rate, 4),
        "source": "BACEN SGS 25497",
        "asof": datetime.utcnow().date().isoformat(),
    }
